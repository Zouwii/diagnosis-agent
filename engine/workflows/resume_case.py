"""Update an existing Case, append source material, and optionally re-analyze."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from engine.collectors import CollectionDestination, CollectionRequest, collect
from engine.utils import append_event, merge_unique, normalize_multi, now_iso, read_case_context, read_case_status, write_json
from engine.reporting.initial import write_initial_files
from engine.workflows.analyze_case import ExternalEnricher, analyze_case


@dataclass(frozen=True)
class ResumeCaseRequest:
    case_dir: Path
    symptom: str = ""
    time_window: str = ""
    task_id: str = ""
    task_url: str = ""
    robot_ip: str = ""
    frp_port: str = ""
    site_robot_ip: str = ""
    log_path: str = ""
    artifacts: list[str] = field(default_factory=list)
    knowledge_sources: list[str] = field(default_factory=list)
    code_sources: list[str] = field(default_factory=list)
    collect_remote: bool = True
    analyze: bool = True
    external_evidence: bool = True


def _set_nonempty(mapping: dict, key: str, value: str) -> None:
    if value:
        mapping[key] = value


def resume_case(request: ResumeCaseRequest, *, external_enricher: ExternalEnricher | None = None) -> dict:
    case_dir = request.case_dir
    context = read_case_context(case_dir)
    status = read_case_status(case_dir)
    source = context.setdefault("source", {})
    _set_nonempty(context, "symptom", request.symptom)
    _set_nonempty(context, "time_window", request.time_window)
    for key, value in (("task_id", request.task_id), ("task_url", request.task_url), ("robot_ip", request.robot_ip), ("frp_port", request.frp_port), ("site_robot_ip", request.site_robot_ip), ("log_path", request.log_path)):
        _set_nonempty(source, key, value)
    if request.robot_ip:
        context.setdefault("robot_identity", {})["ip"] = request.robot_ip
    if request.site_robot_ip:
        context.setdefault("robot_identity", {})["site_robot_ip"] = request.site_robot_ip
    context["knowledge_sources"] = merge_unique(normalize_multi(context.get("knowledge_sources")), normalize_multi(request.knowledge_sources))
    context["code_sources"] = merge_unique(normalize_multi(context.get("code_sources")), normalize_multi(request.code_sources))
    context["artifacts"] = merge_unique(normalize_multi(context.get("artifacts")), normalize_multi(request.artifacts))

    raw_dir = case_dir / "raw"
    extracted_dir = case_dir / "extracted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    context["source_material_dir"] = str(raw_dir)
    source_type = str(context.get("source_type", ""))
    should_collect = source_type == "local_logs" or (source_type in {"internal_robot", "remote_site"} and request.collect_remote)
    if should_collect:
        result = collect(CollectionRequest(
            source_type=source_type,
            destination=CollectionDestination(raw_dir, extracted_dir),
            robot_ip=str(source.get("robot_ip") or ""),
            frp_port=str(source.get("frp_port") or ""),
            site_robot_ip=str(source.get("site_robot_ip") or ""),
            log_path=str(source.get("log_path") or ""),
            collect_remote=request.collect_remote,
        ))
        context["artifacts"] = merge_unique(normalize_multi(context.get("artifacts")), result.artifacts)

    context.setdefault("analysis_route", [])
    context.setdefault("conclusion_status", "insufficient_data")
    context["updated_at"] = now_iso()
    write_json(case_dir / "context.json", context)
    write_json(case_dir / "status.json", {**status, "updated_at": now_iso(), "next_action": "Run /diagnosis-orchestrator with next-prompt.md"})
    write_initial_files(case_dir, context)
    append_event(case_dir, "case_resumed", {"case_id": context.get("case_id", case_dir.name)})
    if request.analyze:
        context = analyze_case(case_dir, context, external_enricher=external_enricher if request.external_evidence else None)
    return context
