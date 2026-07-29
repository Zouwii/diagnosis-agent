"""Read-only DingTalk and GitLab provider adapters."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from engine.analysis.evidence_selection import evidence_keywords, extract_block_texts, select_relevant_snippets
from engine.analysis.external_evidence import enrich_summary_with_external_evidence
from engine.analysis.material_scan import short_line
from engine.utils import merge_unique, normalize_multi, now_iso, read_json


HTTP_TIMEOUT = 20
MAX_EXTERNAL_DOCS = 5
MAX_GITLAB_RESULTS = 5


def http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: Any | None = None, timeout: int = HTTP_TIMEOUT) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.read(500).decode('utf-8', errors='replace')}"
    except (URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not raw.strip():
        return {}, None
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, f"non-json response: {raw[:200]}"


def dingtalk_credentials() -> tuple[str, str, str | None]:
    config_dir = Path.home() / ".config" / "jz-dingtalk"
    token_path, user_path = config_dir / "proxy-token", config_dir / "user.json"
    if not token_path.exists() or not user_path.exists():
        return "", "", "missing ~/.config/jz-dingtalk/proxy-token or user.json"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
        union_id = str(read_json(user_path).get("unionId", "")).strip()
    except (OSError, json.JSONDecodeError) as exc:
        return "", "", f"failed to read DingTalk credentials: {exc}"
    return (token, union_id, None) if token and union_id else ("", "", "empty DingTalk proxyToken or unionId")


def dingtalk_proxy_request(target_url: str, *, method: str = "GET", body: Any | None = None) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    token, union_id, error = dingtalk_credentials()
    if error:
        return None, error
    payload: dict[str, Any] = {"url": target_url, "method": method, "headers": {"Content-Type": "application/json"}}
    if body is not None:
        payload["body"] = body
    return http_json(os.environ.get("DINGTALK_PROXY_URL", "http://claude.server22.jz/api/dingtalk/proxy"), method="POST", headers={"Content-Type": "application/json", "X-Proxy-Token": token, "X-User-Id": union_id}, body=payload)


def _workspace_id(source: str) -> str:
    parts = [part for part in urlparse(source).path.split("/") if part]
    for marker in ("spaces", "team"):
        if marker in parts and parts.index(marker) + 1 < len(parts):
            return parts[parts.index(marker) + 1]
    return ""


def collect_dingtalk_evidence(context: dict[str, Any], summary: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    sources = normalize_multi(context.get("knowledge_sources"))
    keywords = evidence_keywords(context, summary)
    if not sources and "dingtalk-docs" not in normalize_multi(summary.get("analysis_route")):
        return [], []
    keywords = keywords or ["导航", "错误码", "排查"]
    _, union_id, error = dingtalk_credentials()
    if error:
        return [], [error]
    workspace_ids = merge_unique([], [_workspace_id(source) for source in sources if _workspace_id(source)])
    docs: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for keyword in keywords[:5]:
        if len(docs) >= MAX_EXTERNAL_DOCS:
            break
        search_urls = [f"https://api.dingtalk.com/v1.0/doc/docs?operatorId={quote(union_id)}&workspaceId={quote(workspace_id)}&keyword={quote(keyword)}&maxResults=5" for workspace_id in workspace_ids]
        if not search_urls:
            payload, request_error = dingtalk_proxy_request(f"https://api.dingtalk.com/v2.0/storage/dentries/search?operatorId={quote(union_id)}", method="POST", body={"keyword": keyword})
            if request_error:
                warnings.append(f"DingTalk global search '{keyword}' failed: {request_error}")
                continue
            for item in payload.get("items", []) if isinstance(payload, dict) else []:
                dentry = str(item.get("dentryUuid", ""))
                if dentry and dentry not in seen:
                    seen.add(dentry)
                    docs.append({"title": str(item.get("name", "")), "url": "", "node_id": "", "dentry_uuid": dentry, "keyword": keyword})
        for search_url in search_urls:
            payload, request_error = dingtalk_proxy_request(search_url)
            if request_error:
                warnings.append(f"DingTalk search '{keyword}' failed: {request_error}")
                continue
            for item in payload.get("docs", []) if isinstance(payload, dict) else []:
                node = item.get("nodeBO", {}) if isinstance(item, dict) else {}
                node_id = str(node.get("nodeId", ""))
                if node_id and node_id not in seen:
                    seen.add(node_id)
                    docs.append({"title": re.sub(r"</?red>", "", str(node.get("originName") or node.get("name") or "")), "url": str(node.get("url", "")), "node_id": node_id, "keyword": keyword})
                if len(docs) >= MAX_EXTERNAL_DOCS:
                    break
    for doc in docs:
        dentry = str(doc.get("dentry_uuid", ""))
        if not dentry:
            payload, request_error = dingtalk_proxy_request(f"https://api.dingtalk.com/v2.0/storage/dentries/search?operatorId={quote(union_id)}", method="POST", body={"keyword": doc["title"]})
            if request_error:
                warnings.append(f"DingTalk dentry lookup '{doc['title']}' failed: {request_error}")
                continue
            items = payload.get("items", []) if isinstance(payload, dict) else []
            exact = next((item for item in items if str(item.get("name", "")).strip() == doc["title"]), items[0] if items else {})
            dentry = str(exact.get("dentryUuid", ""))
        if not dentry:
            warnings.append(f"DingTalk dentry lookup '{doc['title']}' returned no dentryUuid")
            continue
        doc["dentry_uuid"] = dentry
        payload, request_error = dingtalk_proxy_request(f"https://api.dingtalk.com/v1.0/doc/suites/documents/{quote(dentry)}/blocks?operatorId={quote(union_id)}")
        if request_error:
            warnings.append(f"DingTalk blocks '{doc['title']}' failed: {request_error}")
            continue
        doc["snippets"] = select_relevant_snippets(extract_block_texts(payload or {}), keywords)
    return docs[:MAX_EXTERNAL_DOCS], warnings


def gitlab_config() -> tuple[str, str, str | None]:
    path = Path.home() / ".config" / "jz-gitlab" / "pat.json"
    if path.exists():
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            return "", "", f"failed to read GitLab credentials: {exc}"
    else:
        data = {}
    token = str(os.environ.get("GITLAB_API_TOKEN") or data.get("token", "")).strip()
    base = str(os.environ.get("GITLAB_BASE_URL") or data.get("base_url", "")).strip().rstrip("/")
    if not token or not base:
        return "", "", "missing ~/.config/jz-gitlab/pat.json or GITLAB_API_TOKEN/GITLAB_BASE_URL"
    return token, base, None


def _gitlab_project(source: str, default_base: str) -> tuple[str, str]:
    parsed = urlparse(source)
    if parsed.scheme and parsed.netloc:
        cleaned = []
        for part in [part for part in parsed.path.split("/") if part]:
            if part in {"-", "tree", "blob", "merge_requests", "issues"}:
                break
            cleaned.append(part.removesuffix(".git"))
        return f"{parsed.scheme}://{parsed.netloc}", "/".join(cleaned)
    return default_base, source.strip().removesuffix(".git")


def _gitlab_request(base: str, token: str, endpoint: str):
    return http_json(f"{base.rstrip('/')}{endpoint}", headers={"PRIVATE-TOKEN": token})


def collect_gitlab_evidence(context: dict[str, Any], summary: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    sources = normalize_multi(context.get("code_sources"))
    if not sources:
        return [], []
    token, configured_base, error = gitlab_config()
    if error:
        return [], [error]
    keywords = evidence_keywords(context, summary) or ["nav", "error", "README"]
    projects, warnings = [], []
    for source in sources[:6]:
        base, project_path = _gitlab_project(source, configured_base)
        if not base or not project_path or Path(source).exists():
            continue
        project, request_error = _gitlab_request(base, token, f"/api/v4/projects/{quote(project_path, safe='')}")
        if request_error or not isinstance(project, dict):
            warnings.append(f"GitLab project '{project_path}' failed: {request_error}")
            continue
        evidence = {"source": source, "project_id": project.get("id"), "path_with_namespace": project.get("path_with_namespace", project_path), "default_branch": str(project.get("default_branch") or "master"), "web_url": project.get("web_url", source), "matches": []}
        for keyword in keywords[:5]:
            matches, search_error = _gitlab_request(base, token, f"/api/v4/projects/{project.get('id')}/search?scope=blobs&search={quote(keyword)}")
            if search_error:
                warnings.append(f"GitLab search '{project_path}' '{keyword}' failed: {search_error}")
                continue
            for item in matches[:MAX_GITLAB_RESULTS] if isinstance(matches, list) else []:
                evidence["matches"].append({"keyword": keyword, "path": item.get("path") or item.get("filename") or "", "ref": item.get("ref") or evidence["default_branch"], "startline": item.get("startline", ""), "data": short_line(str(item.get("data", "")), 220)})
                if len(evidence["matches"]) >= MAX_GITLAB_RESULTS:
                    break
            if len(evidence["matches"]) >= MAX_GITLAB_RESULTS:
                break
        projects.append(evidence)
    return projects, warnings


def enrich_with_external_evidence(context: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return enrich_summary_with_external_evidence(context, summary, collect_dingtalk=collect_dingtalk_evidence, collect_gitlab=collect_gitlab_evidence, now=now_iso)
