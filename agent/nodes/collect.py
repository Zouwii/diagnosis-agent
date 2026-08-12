"""graph-v1 collection node and Engine request adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from agent.logger import log
from agent.state import DiagnosisState
from engine.utils import now_iso, write_json
from engine.workflows import RunCaseRequest, run_case


SUPPORTED_SOURCES = {"tb_task", "internal_robot", "remote_site", "local_logs"}


def _task_id(params: dict[str, Any]) -> str:
    explicit = str(params.get("task_id") or "").strip()
    if explicit:
        return explicit
    task_url = str(params.get("task_url") or "").strip()
    if not task_url:
        return ""
    parsed = urlparse(task_url)
    query = parse_qs(parsed.query)
    for key in ("taskId", "task_id", "id"):
        values = query.get(key, [])
        if values and values[0].strip():
            return values[0].strip()
    segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment.strip()]
    if "task" in segments:
        index = len(segments) - 1 - segments[::-1].index("task")
        if index + 1 < len(segments):
            return segments[index + 1]
    return segments[-1] if segments else ""


def _validate_local_path(state: DiagnosisState, params: dict[str, Any]) -> None:
    if state.get("source_type") != "local_logs":
        return
    log_path = str(params.get("log_path") or "").strip()
    roots = [str(root).strip() for root in state.get("input_roots", []) if str(root).strip()]
    legacy_root = str(state.get("input_root") or "").strip()
    if legacy_root and legacy_root not in roots:
        roots.append(legacy_root)
    if not log_path or not roots:
        return
    resolved = Path(log_path).expanduser().resolve()
    allowed = [Path(root).expanduser().resolve() for root in roots]
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError("local log path is outside the tenant's allowed input directories")


def _request_from_state(state: DiagnosisState) -> RunCaseRequest:
    source_type = str(state.get("source_type") or "").strip()
    if source_type not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported source_type: {source_type or 'empty'}")
    case_id = str(state.get("case_id") or "").strip()
    case_dir = Path(str(state.get("case_dir") or "")).expanduser().resolve()
    if not case_id or not str(state.get("case_dir") or "").strip():
        raise ValueError("case_id and case_dir are required")
    if case_dir.name != case_id:
        raise ValueError("assigned case_dir does not match case_id")

    params = dict(state.get("extra_params") or {})
    _validate_local_path(state, params)
    return RunCaseRequest(
        case_id=case_id,
        case_dir=case_dir,
        source_type=source_type,
        symptom=str(state.get("symptom") or state.get("user_input") or "").replace("None", ""),
        time_window=str(state.get("time_window") or ""),
        task_id=_task_id(params),
        task_url=str(params.get("task_url") or ""),
        robot_ip=str(params.get("robot_ip") or ""),
        frp_port=str(params.get("frp_port") or ""),
        site_robot_ip=str(params.get("site_robot_ip") or ""),
        log_path=str(params.get("log_path") or ""),
        artifacts=[str(item) for item in params.get("artifacts", [])],
        knowledge_sources=[str(item) for item in params.get("knowledge_sources", [])],
        code_sources=[str(item) for item in params.get("code_sources", [])],
        collect_remote=params.get("collect_remote") is not False,
        allow_large_downloads=params.get("allow_large_downloads") is True,
        allow_all_attachments=params.get("allow_all_attachments") is True,
        analyze=True,
        external_evidence=params.get("external_evidence") is not False,
    )


async def collect_materials(state: DiagnosisState) -> DiagnosisState:
    """Collect materials only — LLM analysis happens in the next node."""
    request = _request_from_state(state)
    # graph-v1 uses this node for collection only. RunCaseRequest is frozen,
    # so derive a modified request instead of mutating it in place.
    request = replace(request, analyze=False, external_evidence=False)

    log("collect", "开始采集", source_type=request.source_type, case_id=request.case_id)

    result = run_case(request, external_enricher=None)

    context = result.context
    collection = result.collection
    case_dir = request.case_dir
    materials = {
        "collected": True,
        "source": request.source_type,
        "case_id": request.case_id,
        "case_dir": str(case_dir),
        "raw_dir": str(case_dir / "raw"),
        "extracted_dir": str(case_dir / "extracted"),
        "artifacts": list(collection.artifacts),
        "warnings": list(collection.warnings),
        "metadata": {
            **collection.metadata,
            "collection_skill": str(state.get("selected_skill") or ""),
        },
    }
    write_json(case_dir / "collection.json", {**materials, "collected_at": now_iso()})

    update: DiagnosisState = {
        "materials": materials,
        "collected_at": str(context.get("created_at") or now_iso()),
        "context": context,
        "findings": [],
        "error_codes": [],
    }
    log("collect", "采集完成", case_id=request.case_id, artifacts=len(collection.artifacts))
    return update
