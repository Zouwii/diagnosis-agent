"""Material collection node shared by all four diagnosis entry paths."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from agent.logger import log
from agent.state import DiagnosisState
from engine.collectors import CollectionDestination, CollectionRequest, collect
from engine.utils import append_event, now_iso, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_SOURCES = {"tb_task", "internal_robot", "remote_site", "local_logs"}
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _cases_root() -> Path:
    configured = os.environ.get("DIAGNOSIS_CASES_DIR", "").strip()
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "data" / "cases"


def _resolve_case_id(state: DiagnosisState) -> str:
    case_id = str(state.get("case_id") or "").strip()
    if not case_id:
        return f"case-{uuid.uuid4().hex[:12]}"
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("case_id may only contain letters, numbers, '.', '_' and '-'")
    return case_id


def _resolve_case_dir(state: DiagnosisState, case_id: str) -> Path:
    assigned = str(state.get("case_dir") or "").strip()
    if not assigned:
        return _cases_root() / case_id
    case_dir = Path(assigned).expanduser().resolve()
    if case_dir.name != case_id:
        raise ValueError("assigned case_dir does not match case_id")
    return case_dir


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
        value = query.get(key, [])
        if value and value[0].strip():
            return value[0].strip()

    segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment.strip()]
    if "task" in segments:
        index = len(segments) - 1 - segments[::-1].index("task")
        if index + 1 < len(segments):
            return segments[index + 1]
    return segments[-1] if segments else ""


def _collection_request(
    source_type: str,
    params: dict[str, Any],
    raw_dir: Path,
    extracted_dir: Path,
    input_roots: list[str] | None = None,
) -> CollectionRequest:
    log_path = str(params.get("log_path") or "").strip()
    if source_type == "local_logs" and log_path and input_roots:
        resolved_log = Path(log_path).expanduser().resolve()
        resolved_roots = [Path(root).expanduser().resolve() for root in input_roots if str(root).strip()]
        if not any(resolved_log.is_relative_to(root) for root in resolved_roots):
            raise ValueError("local log path is outside the tenant's allowed input directories")
        log_path = str(resolved_log)
    return CollectionRequest(
        source_type=source_type,
        destination=CollectionDestination(raw_dir=raw_dir, extracted_dir=extracted_dir),
        task_id=_task_id(params),
        robot_ip=str(params.get("robot_ip") or "").strip(),
        frp_port=str(params.get("frp_port") or "").strip(),
        site_robot_ip=str(params.get("site_robot_ip") or "").strip(),
        log_path=log_path,
        collect_remote=params.get("collect_remote") is not False,
        allow_large_downloads=params.get("allow_large_downloads") is True,
        allow_all_attachments=params.get("allow_all_attachments") is True,
    )


async def collect_data(state: DiagnosisState) -> DiagnosisState:
    """Dispatch collection and expose one stable material contract downstream."""
    source_type = str(state.get("source_type") or "")
    selected_skill = str(state.get("selected_skill") or "")
    collected_at = now_iso()
    case_id = ""
    case_dir: Path | None = None
    log("collect_data", "采集开始", source_type=source_type or "?")

    try:
        if source_type not in SUPPORTED_SOURCES:
            raise ValueError(f"unsupported or unresolved source_type: {source_type or 'empty'}")

        case_id = _resolve_case_id(state)
        case_dir = _resolve_case_dir(state, case_id)
        raw_dir = case_dir / "raw"
        extracted_dir = case_dir / "extracted"
        raw_dir.mkdir(parents=True, exist_ok=True)
        extracted_dir.mkdir(parents=True, exist_ok=True)

        params = dict(state.get("extra_params") or {})
        input_roots = list(state.get("input_roots") or [])
        legacy_input_root = str(state.get("input_root") or "").strip()
        if legacy_input_root and legacy_input_root not in input_roots:
            input_roots.append(legacy_input_root)
        request = _collection_request(
            source_type,
            params,
            raw_dir,
            extracted_dir,
            input_roots=input_roots,
        )
        result = await asyncio.to_thread(collect, request)

        materials: dict[str, Any] = {
            "collected": True,
            "source": source_type,
            "case_id": case_id,
            "case_dir": str(case_dir),
            "raw_dir": str(raw_dir),
            "extracted_dir": str(extracted_dir),
            "artifacts": result.artifacts,
            "warnings": result.warnings,
            "metadata": {**result.metadata, "collection_skill": selected_skill},
        }
        write_json(case_dir / "collection.json", {**materials, "collected_at": collected_at})
        append_event(
            case_dir,
            "materials_collected",
            {
                "source_type": source_type,
                "collection_skill": selected_skill,
                "artifact_count": len(result.artifacts),
                "warning_count": len(result.warnings),
            },
        )
        log(
            "collect_data",
            "采集完成",
            source=source_type,
            case_id=case_id,
            artifacts=len(result.artifacts),
            warnings=len(result.warnings),
        )
        return {"case_id": case_id, "materials": materials, "collected_at": collected_at}
    except Exception as exc:
        message = f"{source_type or 'unknown'} collection failed: {exc}"
        materials: dict[str, Any] = {
            "collected": False,
            "source": source_type,
            "artifacts": [],
            "warnings": [],
            "metadata": {},
            "error": str(exc),
        }
        if case_dir is not None:
            materials.update(
                {
                    "case_id": case_id,
                    "case_dir": str(case_dir),
                    "raw_dir": str(case_dir / "raw"),
                    "extracted_dir": str(case_dir / "extracted"),
                }
            )
            try:
                write_json(case_dir / "collection.json", {**materials, "collected_at": collected_at})
                append_event(case_dir, "materials_collection_failed", {"source_type": source_type, "error": str(exc)})
            except OSError as persist_error:
                log("collect_data", "失败状态持久化失败", error=str(persist_error))
        log("collect_data", "采集失败", source=source_type or "?", error=str(exc))
        update: DiagnosisState = {
            "materials": materials,
            "collected_at": collected_at,
            "errors": [message],
        }
        if case_id:
            update["case_id"] = case_id
        return update
