"""Create a Case, collect source material, and optionally analyze it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.collectors import CollectionDestination, CollectionRequest, CollectionResult, collect
from engine.utils import append_event, merge_unique, normalize_multi, now_iso, write_json
from engine.reporting.initial import write_initial_files
from engine.teambition_client import TeambitionClientError
from engine.workflows.analyze_case import ExternalEnricher, analyze_case
from engine.workflows.models import RunCaseRequest, RunCaseResult


def _tb_title(payload: dict[str, Any]) -> str:
    result = payload.get("task_response", {}).get("result", [])
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return str(result[0].get("content", "")).strip()
    return ""


def _collect(request: RunCaseRequest, raw_dir: Path, extracted_dir: Path) -> CollectionResult:
    collector_request = CollectionRequest(
        source_type=request.source_type,
        destination=CollectionDestination(raw_dir, extracted_dir),
        task_id=request.task_id,
        robot_ip=request.robot_ip,
        frp_port=request.frp_port,
        site_robot_ip=request.site_robot_ip,
        log_path=request.log_path,
        collect_remote=request.collect_remote,
        allow_large_downloads=request.allow_large_downloads,
        allow_all_attachments=request.allow_all_attachments,
    )
    try:
        return collect(collector_request)
    except TeambitionClientError as exc:
        error_path = raw_dir / "teambition-error.txt"
        error_path.write_text(f"task_url: {request.task_url}\ntask_id: {request.task_id}\nerror: {exc}\n", encoding="utf-8")
        return CollectionResult(
            artifacts=[str(raw_dir / "teambition-task.json"), str(raw_dir / "teambition-activities.json"), str(raw_dir / "teambition-attachments.json"), str(error_path)],
            warnings=[str(exc)],
            payload={"downloaded_files": [], "extracted_dirs": [], "warnings": [str(exc)], "manifest_path": "", "error_path": str(error_path)},
        )


def run_case(request: RunCaseRequest, *, external_enricher: ExternalEnricher | None = None) -> RunCaseResult:
    case_dir = request.case_dir
    raw_dir = case_dir / "raw"
    extracted_dir = case_dir / "extracted"
    for directory in (raw_dir, extracted_dir, case_dir / "tmp"):
        directory.mkdir(parents=True, exist_ok=True)

    collection = _collect(request, raw_dir, extracted_dir)
    artifacts = merge_unique(normalize_multi(request.artifacts), collection.artifacts)
    if request.log_path:
        artifacts = merge_unique(artifacts, [str(Path(request.log_path).expanduser())])
    context: dict[str, Any] = {
        "case_id": request.case_id,
        "case_dir": str(case_dir),
        "created_at": now_iso(),
        "source_type": request.source_type,
        "source": {"task_id": request.task_id or None, "task_url": request.task_url or None, "robot_ip": request.robot_ip or None, "frp_port": request.frp_port or None, "site_robot_ip": request.site_robot_ip or None, "log_path": request.log_path or None},
        "symptom": request.symptom,
        "time_window": request.time_window,
        "robot_identity": {key: value for key, value in {"ip": request.robot_ip, "site_robot_ip": request.site_robot_ip}.items() if value},
        "artifacts": artifacts,
        "knowledge_sources": normalize_multi(request.knowledge_sources),
        "code_sources": normalize_multi(request.code_sources),
        "analysis_route": [],
        "conclusion_status": "insufficient_data",
        "source_material_dir": str(raw_dir),
    }
    if request.source_type == "tb_task":
        payload = collection.payload
        context["teambition"] = {
            "task_json": "raw/teambition-task.json",
            "activities_json": "raw/teambition-activities.json",
            "attachments_manifest": "raw/teambition-attachments.json",
            "downloaded_count": len(payload.get("downloaded_files", [])),
            "extracted_count": len(payload.get("extracted_dirs", [])),
            "warning_count": len(collection.warnings),
            "warnings": collection.warnings,
        }
        title = _tb_title(payload)
        if title:
            context["task_title"] = title

    write_json(case_dir / "context.json", context)
    write_json(case_dir / "status.json", {"case_id": request.case_id, "status": "created", "created_at": context["created_at"], "updated_at": now_iso(), "next_action": "Run /diagnosis-orchestrator with next-prompt.md"})
    write_initial_files(case_dir, context)
    append_event(case_dir, "case_created", {"source_type": request.source_type})
    if request.analyze:
        context = analyze_case(case_dir, context, external_enricher=external_enricher if request.external_evidence else None)
    return RunCaseResult(context=context, collection=collection)
