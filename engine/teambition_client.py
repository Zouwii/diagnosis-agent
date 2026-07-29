#!/usr/bin/env python3
"""Teambition fetch-and-download helpers for diagnosis cases."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TB_APP_ID = os.environ.get("TB_APP_ID", "69d8b5ef0cf0d7f4d5091988")
TB_SECRET_KEY = os.environ.get("TB_SECRET_KEY", "JNkWgTBGDCINEAKHvchnCtim7snOQ8lM")
TB_TENANT_ID = os.environ.get("TB_TENANT_ID", "613f0dacd4147ebbe9283b8f")
TB_TENANT_TYPE = os.environ.get("TB_TENANT_TYPE", "organization")
TB_API_BASE = os.environ.get("TB_API_BASE", "https://open.teambition.com/api/v3")
TB_MAX_AUTO_DOWNLOAD_GB = 5
TB_MAX_AUTO_DOWNLOAD_BYTES = TB_MAX_AUTO_DOWNLOAD_GB * 1024 * 1024 * 1024
TB_MAX_FULL_EXTRACT_GB = 10
TB_MAX_FULL_EXTRACT_BYTES = TB_MAX_FULL_EXTRACT_GB * 1024 * 1024 * 1024
DATE_STAMP_RE = re.compile(r"(20\d{6})")

# ── 附件过滤：跳过对诊断无价值的二进制文件 ──────────────────────
_SKIP_EXTENSIONS: set[str] = {
    ".bag", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv",
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".svg",
}
_BINARY_SKIP_EXTENSIONS: set[str] = {
    ".exe", ".dll", ".vhd", ".vmdk", ".img", ".iso",
}
_SKIP_ALL = _SKIP_EXTENSIONS | _BINARY_SKIP_EXTENSIONS
_MAX_ATTACHMENT_SIZE = 500 * 1024**2  # 超过 500MB 且非日志/tar/配置文件的跳过

_SAFE_EXTENSIONS: set[str] = {
    ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar", ".zip",
    ".log", ".txt", ".yaml", ".yml", ".json", ".xml", ".csv",
    ".conf", ".cfg", ".ini", ".toml",
}


def should_skip_attachment(file_name: str, file_size: int | None, *, allow_all: bool = False) -> tuple[bool, str | None]:
    """判断附件是否应该跳过下载。

    Returns:
        (skip, reason) — skip=True 且 reason 非空时说明被过滤。
    """
    if allow_all:
        return False, None
    stem = file_name.lower()
    # 检查后缀
    for ext in _SKIP_ALL:
        if stem.endswith(ext):
            return True, f"binary file type ({ext})"
    # 检查大文件
    if file_size is not None and file_size > _MAX_ATTACHMENT_SIZE:
        for safe in _SAFE_EXTENSIONS:
            if stem.endswith(safe):
                return False, None
        return True, f"large file without safe extension ({_format_bytes(file_size)})"
    return False, None


@dataclass(slots=True)
class AttachmentRecord:
    resource_id: str
    source: str
    file_name: str
    file_size: int | None
    mime_type: str | None
    download_url: str | None
    skipped_reason: str | None = None
    downloaded_path: str | None = None
    extracted_path: str | None = None


class TeambitionClientError(RuntimeError):
    pass


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def build_jwt_token() -> str:
    if not TB_APP_ID or not TB_SECRET_KEY:
        raise TeambitionClientError("missing TB_APP_ID or TB_SECRET_KEY")
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    now = _now_ts()
    payload = _b64url(
        json.dumps({"_appId": TB_APP_ID, "iat": now, "exp": now + 3600}, separators=(",", ":")).encode("utf-8")
    )
    sign_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(TB_SECRET_KEY.encode("utf-8"), sign_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def _request_json(method: str, url: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {build_jwt_token()}",
        "X-Tenant-Id": TB_TENANT_ID,
        "X-Tenant-Type": TB_TENANT_TYPE,
    }
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise TeambitionClientError(f"Teambition API HTTP {exc.code}: {err_body[:1000]}") from exc
    except OSError as exc:
        raise TeambitionClientError(f"Teambition API request failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TeambitionClientError(f"invalid JSON from Teambition API: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise TeambitionClientError("Teambition API response must be a JSON object")
    return parsed


def _task_query(task_id: str) -> dict[str, Any]:
    url = f"{TB_API_BASE}/task/query?{urllib.parse.urlencode({'taskId': task_id})}"
    return _request_json("GET", url)


def _task_activities(task_id: str, page_size: int = 100) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(20):
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        url = f"{TB_API_BASE}/task/{task_id}/activity/list?{urllib.parse.urlencode(params)}"
        payload = _request_json("GET", url)
        result = payload.get("result") or payload.get("data") or []
        if isinstance(result, list):
            activities.extend(item for item in result if isinstance(item, dict))
        next_token = payload.get("nextPageToken") or payload.get("pageToken") or payload.get("nextToken")
        if not next_token or next_token == page_token:
            break
        page_token = str(next_token)
    return activities


def _task_items(task_response: dict[str, Any]) -> list[dict[str, Any]]:
    result = task_response.get("result") or []
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
    return {}


def _attachment_name_from_meta(meta: dict[str, Any], fallback: str) -> str:
    for key in ("title", "fileName", "name", "filename"):
        value = meta.get(key)
        if value:
            return str(value)
    return fallback


def _make_candidates(task_id: str, task_items: list[dict[str, Any]], activities: list[dict[str, Any]]) -> list[AttachmentRecord]:
    candidates: list[AttachmentRecord] = []

    for task_item in task_items:
        for field in task_item.get("customfields") or []:
            if not isinstance(field, dict):
                continue
            if field.get("type") not in ("work", "file"):
                continue
            fallback_cf = str(field.get("id") or field.get("fieldId") or "cf")
            for value in field.get("value") or []:
                if not isinstance(value, dict):
                    continue
                meta = _jsonish(value.get("metaString"))
                if not isinstance(meta, dict):
                    continue
                resource_id = meta.get("resourceId")
                if not resource_id:
                    continue
                candidates.append(
                    AttachmentRecord(
                        resource_id=str(resource_id),
                        source="detail",
                        file_name=_attachment_name_from_meta(meta, fallback_cf),
                        file_size=None,
                        mime_type=None,
                        download_url=None,
                    )
                )

    for activity in activities:
        if activity.get("action") != "comment":
            continue
        activity_id = activity.get("id")
        if not activity_id:
            continue
        content = _jsonish(activity.get("content"))
        files = content.get("files") if isinstance(content, dict) else []
        if not isinstance(files, list):
            continue
        for file_item in files:
            if isinstance(file_item, dict):
                file_id = file_item.get("id") or file_item.get("fileId") or file_item.get("resourceId")
            else:
                file_id = file_item
            if not file_id:
                continue
            candidates.append(
                AttachmentRecord(
                    resource_id=f"task:{task_id}/activity:{activity_id}/file:{file_id}",
                    source="comment",
                    file_name=f"file-{file_id}",
                    file_size=None,
                    mime_type=None,
                    download_url=None,
                )
            )

    deduped: list[AttachmentRecord] = []
    seen: set[str] = set()
    for item in candidates:
        if item.resource_id in seen:
            continue
        seen.add(item.resource_id)
        deduped.append(item)
    return deduped


def _format_bytes(num: int | None) -> str:
    if num is None:
        return "-"
    if num < 1024:
        return f"{num} B"
    kib = num / 1024
    if kib < 1024:
        return f"{kib:.2f} KB"
    mib = kib / 1024
    if mib < 1024:
        return f"{mib:.2f} MB"
    gib = mib / 1024
    return f"{gib:.2f} GB"


def _safe_filename(name: str) -> str:
    text = Path(name).name.strip() or "attachment"
    text = re.sub(r"[^\w.\-()+\[\]@#=, ]+", "_", text)
    text = text.strip(" .")
    return text or "attachment"


def _unique_path(base_dir: Path, file_name: str) -> Path:
    candidate = base_dir / _safe_filename(file_name)
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = "".join(candidate.suffixes)
    for idx in range(2, 9999):
        alt = base_dir / f"{stem}-{idx}{suffix}"
        if not alt.exists():
            return alt
    raise TeambitionClientError(f"unable to allocate filename for {file_name}")


def _download_file(url: str, dest: Path) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=60) as resp, dest.open("wb") as out:
            shutil.copyfileobj(resp, out, length=1024 * 1024)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise TeambitionClientError(f"download failed HTTP {exc.code}: {err_body[:1000]}") from exc
    except OSError as exc:
        raise TeambitionClientError(f"download failed: {exc}") from exc


def _safe_extract_tar(archive: Path, target_dir: Path) -> None:
    with tarfile.open(archive, "r:*") as tf:
        members = tf.getmembers()
        for member in members:
            resolved = (target_dir / member.name).resolve()
            if not resolved.is_relative_to(target_dir.resolve()):
                raise TeambitionClientError(f"unsafe archive entry: {member.name}")
        tf.extractall(target_dir)


def _safe_extract_zip(archive: Path, target_dir: Path, members: list[zipfile.ZipInfo] | None = None) -> None:
    with zipfile.ZipFile(archive) as zf:
        entries = members if members is not None else zf.infolist()
        for item in entries:
            name = item.filename
            resolved = (target_dir / name).resolve()
            if not resolved.is_relative_to(target_dir.resolve()):
                raise TeambitionClientError(f"unsafe archive entry: {name}")
        for item in entries:
            zf.extract(item, target_dir)


def _dated_zip_members(archive: Path) -> tuple[str | None, list[zipfile.ZipInfo], int]:
    with zipfile.ZipFile(archive) as zf:
        entries = [item for item in zf.infolist() if not item.is_dir()]
    total_size = sum(item.file_size for item in entries)
    by_date: dict[str, list[zipfile.ZipInfo]] = {}
    for item in entries:
        match = DATE_STAMP_RE.search(Path(item.filename).name)
        if not match:
            continue
        by_date.setdefault(match.group(1), []).append(item)
    if not by_date:
        return None, entries, total_size
    selected_date = max(by_date, key=lambda value: (len(by_date[value]), value))
    return selected_date, by_date[selected_date], total_size


def _extract_nested_archives(target_dir: Path) -> list[str]:
    extracted: list[str] = []
    for archive in sorted(target_dir.rglob("*")):
        if not archive.is_file() or not zipfile.is_zipfile(archive):
            continue
        date_stamp, members, total_size = _dated_zip_members(archive)
        stem_dir = archive.with_suffix("")
        if date_stamp and total_size > TB_MAX_FULL_EXTRACT_BYTES:
            nested_dir = stem_dir.parent / f"{stem_dir.name}-{date_stamp}"
            nested_dir.mkdir(parents=True, exist_ok=True)
            _safe_extract_zip(archive, nested_dir, members)
        else:
            nested_dir = stem_dir
            nested_dir.mkdir(parents=True, exist_ok=True)
            _safe_extract_zip(archive, nested_dir)
        extracted.append(str(nested_dir))
    return extracted


def _extract_if_archive(file_path: Path, extracted_root: Path) -> list[str]:
    extracted_root.mkdir(parents=True, exist_ok=True)
    stem = file_path.name
    for suffix in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".zip", ".tar"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if not stem:
        stem = file_path.stem
    target_dir = extracted_root / _safe_filename(stem)
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted = False
    if tarfile.is_tarfile(file_path):
        _safe_extract_tar(file_path, target_dir)
        extracted = True
    elif zipfile.is_zipfile(file_path):
        _safe_extract_zip(file_path, target_dir)
        extracted = True

    if not extracted:
        return []
    return [str(target_dir), *_extract_nested_archives(target_dir)]


def _query_file_metadata(resource_ids: list[str], need_sign: bool) -> list[dict[str, Any]]:
    if not resource_ids:
        return []
    payload = _request_json(
        "POST",
        f"{TB_API_BASE}/file/query/by-resource-ids",
        body={"resourceIds": resource_ids, "needSign": need_sign},
    )
    result = payload.get("result") or []
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def download_deferred_attachments(
    deferred: list[dict[str, Any]],
    dest_dir: Path,
    extracted_dir: Path | None = None,
) -> dict[str, Any]:
    """下载延后附件到 dest_dir。

    Args:
        deferred: 延后附件列表（含 resource_id, file_name, download_url）
        dest_dir: 下载目标目录
        extracted_dir: 可选，解压目录

    Returns:
        {"downloaded": [...], "failed": [...], "extracted_dirs": [...]}
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    extracted_dirs: list[str] = []

    for item in deferred:
        url = item.get("download_url")
        if not url:
            failed.append({"resource_id": item["resource_id"], "file_name": item["file_name"], "reason": "missing download_url"})
            continue
        file_name = item.get("file_name", item["resource_id"])
        target = _unique_path(dest_dir, file_name)
        try:
            _download_file(url, target)
        except TeambitionClientError as exc:
            failed.append({"resource_id": item["resource_id"], "file_name": file_name, "reason": str(exc)})
            continue
        entry = {
            "resource_id": item["resource_id"],
            "file_name": file_name,
            "downloaded_path": str(target),
        }
        if extracted_dir:
            extracted_paths = _extract_if_archive(target, extracted_dir)
            if extracted_paths:
                entry["extracted_path"] = extracted_paths[0]
                extracted_dirs.extend(extracted_paths)
        downloaded.append(entry)

    return {"downloaded": downloaded, "failed": failed, "extracted_dirs": extracted_dirs}


def fetch_and_download_task_materials(
    *,
    task_id: str,
    raw_dir: Path,
    extracted_dir: Path,
    allow_large_downloads: bool = False,
    allow_all_attachments: bool = False,
) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    task_response = _task_query(task_id)
    activities = _task_activities(task_id)
    task_items = _task_items(task_response)

    (raw_dir / "teambition-task.json").write_text(json.dumps(task_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (raw_dir / "teambition-activities.json").write_text(json.dumps({"result": activities}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidates = _make_candidates(task_id, task_items, activities)
    resource_ids = [item.resource_id for item in candidates]
    metadata = _query_file_metadata(resource_ids, need_sign=False)
    meta_by_resource = {str(item.get("resourceId") or item.get("resourceID") or item.get("resource_id")): item for item in metadata}

    merged: list[AttachmentRecord] = []
    for candidate in candidates:
        meta = meta_by_resource.get(candidate.resource_id, {})
        file_name = _attachment_name_from_meta(meta, candidate.file_name)
        size_value = meta.get("fileSize")
        try:
            size_int = int(size_value) if size_value not in (None, "") else None
        except (TypeError, ValueError):
            size_int = None
        merged.append(
            AttachmentRecord(
                resource_id=candidate.resource_id,
                source=candidate.source,
                file_name=file_name,
                file_size=size_int,
                mime_type=str(meta.get("mimeType") or "") or None,
                download_url=None,
            )
        )

    downloadable_ids = []
    deferred_ids: list[str] = []
    skipped_large: list[dict[str, Any]] = []
    for item in merged:
        skip, reason = should_skip_attachment(
            item.file_name, item.file_size, allow_all=allow_all_attachments
        )
        if skip and reason:
            item.skipped_reason = reason
            deferred_ids.append(item.resource_id)
            continue
        if item.file_size is not None and item.file_size > TB_MAX_AUTO_DOWNLOAD_BYTES and not allow_large_downloads:
            item.skipped_reason = f"file exceeds {TB_MAX_AUTO_DOWNLOAD_GB}GB threshold: {_format_bytes(item.file_size)}"
            skipped_large.append(
                {
                    "resource_id": item.resource_id,
                    "file_name": item.file_name,
                    "file_size": item.file_size,
                    "reason": item.skipped_reason,
                }
            )
            continue
        downloadable_ids.append(item.resource_id)

    # 为所有待处理文件（可下载 + 延后）获取签名 URL
    all_ids = downloadable_ids + deferred_ids
    signed = _query_file_metadata(all_ids, need_sign=True)
    signed_by_resource = {str(item.get("resourceId") or item.get("resourceID") or item.get("resource_id")): item for item in signed}

    # 构建 merged item 查找表
    merged_by_id = {item.resource_id: item for item in merged}

    # 提取延后附件的元数据（有 URL 但不下载）
    deferred_attachments: list[dict[str, Any]] = []
    for rid in deferred_ids:
        item = merged_by_id.get(rid)
        if item is None:
            continue
        signed_meta = signed_by_resource.get(rid)
        download_url = str(signed_meta.get("downloadUrl")) if signed_meta and signed_meta.get("downloadUrl") else None
        deferred_attachments.append(
            {
                "resource_id": rid,
                "file_name": item.file_name,
                "file_size": item.file_size,
                "file_size_text": _format_bytes(item.file_size),
                "download_url": download_url,
                "reason": item.skipped_reason,
            }
        )

    downloaded: list[AttachmentRecord] = []
    failed: list[dict[str, Any]] = []
    extracted_dirs: list[str] = []
    downloaded_root = raw_dir / "teambition"
    downloaded_root.mkdir(parents=True, exist_ok=True)

    for item in merged:
        if item.skipped_reason:
            continue
        signed_meta = signed_by_resource.get(item.resource_id)
        if not signed_meta or not signed_meta.get("downloadUrl"):
            failed.append(
                {
                    "resource_id": item.resource_id,
                    "file_name": item.file_name,
                    "reason": "missing downloadUrl from Teambition",
                }
            )
            continue
        item.download_url = str(signed_meta.get("downloadUrl"))
        file_name = _attachment_name_from_meta(signed_meta, item.file_name)
        target = _unique_path(downloaded_root, file_name)
        _download_file(item.download_url, target)
        item.downloaded_path = str(target)
        extracted_paths = _extract_if_archive(target, extracted_dir)
        if extracted_paths:
            item.extracted_path = extracted_paths[0]
            extracted_dirs.extend(extracted_paths)
        downloaded.append(item)

    manifest = {
        "task_id": task_id,
        "task_count": len(task_items),
        "activity_count": len(activities),
        "candidate_count": len(candidates),
        "downloaded_count": len(downloaded),
        "deferred_count": len(deferred_attachments),
        "skipped_large_count": len(skipped_large),
        "failed_count": len(failed),
        "attachments": [
            {
                "resource_id": item.resource_id,
                "source": item.source,
                "file_name": item.file_name,
                "file_size": item.file_size,
                "file_size_text": _format_bytes(item.file_size),
                "mime_type": item.mime_type,
                "download_url": item.download_url,
                "downloaded_path": item.downloaded_path,
                "extracted_path": item.extracted_path,
                "skipped_reason": item.skipped_reason,
            }
            for item in merged
        ],
        "skipped_large": skipped_large,
        "deferred_attachments": deferred_attachments,
        "failed": failed,
    }
    manifest_path = raw_dir / "teambition-attachments.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    warnings: list[str] = [
        *[f"deferred {entry['file_name']}: {entry['reason']} (use download-deferred to fetch later)" for entry in deferred_attachments],
    ]
    if skipped_large:
        warnings.append(
            f"skipped {len(skipped_large)} file(s) over {TB_MAX_AUTO_DOWNLOAD_GB}GB without explicit confirmation"
        )
    warnings.extend(
        [f"failed to download {entry['file_name']}: {entry['reason']}" for entry in failed]
    )
    return {
        "task_response": task_response,
        "activities": activities,
        "attachments": manifest["attachments"],
        "downloaded_files": [item.downloaded_path for item in downloaded if item.downloaded_path],
        "extracted_dirs": extracted_dirs,
        "warnings": warnings,
        "manifest_path": str(manifest_path),
    }
