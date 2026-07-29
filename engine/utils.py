"""Stable Case persistence and context helpers.

This module intentionally has no knowledge of collection, analysis, report
templates, or CLI commands. Keeping Case state here lets a future agent runner
and the existing CLI use the same on-disk contract.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    """Return the timestamp format used in Case files and events."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_event(case_dir: Path, event: str, detail: dict[str, Any] | None = None) -> None:
    """Append an immutable Case event to the local audit trail."""
    events_path = case_dir / "events.jsonl"
    payload = {"time": now_iso(), "event": event, "detail": detail or {}}
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_multi(values: list[str] | None) -> list[str]:
    return [item.strip() for item in values or [] if item.strip()]


def merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*existing, *incoming]:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def read_case_context(case_dir: Path) -> dict[str, Any]:
    context_path = case_dir / "context.json"
    if not context_path.exists():
        raise FileNotFoundError(f"case context not found: {context_path}")
    context = read_json(context_path)
    if not isinstance(context, dict):
        raise ValueError(f"case context must be a JSON object: {context_path}")
    return context


def read_case_status(case_dir: Path) -> dict[str, Any]:
    status_path = case_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"case status not found: {status_path}")
    status = read_json(status_path)
    if not isinstance(status, dict):
        raise ValueError(f"case status must be a JSON object: {status_path}")
    return status


def _update_nonempty(mapping: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        mapping[key] = value


def apply_context_updates(existing: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Merge resume arguments into an existing Case without deleting evidence."""
    context = json.loads(json.dumps(existing))
    source = context.setdefault("source", {})

    _update_nonempty(context, "symptom", args.symptom)
    _update_nonempty(context, "time_window", args.time_window)

    _update_nonempty(source, "task_url", args.task_url)
    _update_nonempty(source, "task_id", args.task_id)
    _update_nonempty(source, "robot_ip", args.ip)
    _update_nonempty(source, "frp_port", args.frp_port)
    _update_nonempty(source, "site_robot_ip", args.robot_ip)
    _update_nonempty(source, "log_path", args.log_path)

    if args.ip not in (None, "", []):
        context.setdefault("robot_identity", {})["ip"] = args.ip
    if args.robot_ip not in (None, "", []):
        context.setdefault("robot_identity", {})["site_robot_ip"] = args.robot_ip

    existing_knowledge = normalize_multi(context.get("knowledge_sources"))
    existing_code = normalize_multi(context.get("code_sources"))
    existing_artifacts = normalize_multi(context.get("artifacts"))

    context["knowledge_sources"] = merge_unique(existing_knowledge, normalize_multi(args.knowledge_source))
    context["code_sources"] = merge_unique(existing_code, normalize_multi(args.code_source))
    context["artifacts"] = merge_unique(existing_artifacts, normalize_multi(args.artifact))

    if args.log_path:
        context["artifacts"] = merge_unique(context["artifacts"], [str(Path(args.log_path).expanduser())])

    context.setdefault("analysis_route", [])
    context.setdefault("conclusion_status", "insufficient_data")
    context["updated_at"] = now_iso()
    return context


def build_context(
    args: argparse.Namespace,
    source: str,
    case_id: str,
    case_dir: Path,
    source_material_dir: Path | None = None,
    teambition_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable, source-agnostic Case context document."""
    robot_identity: dict[str, Any] = {}
    if args.ip:
        robot_identity["ip"] = args.ip
    if args.robot_ip:
        robot_identity["site_robot_ip"] = args.robot_ip

    artifacts = normalize_multi(args.artifact)
    if args.log_path:
        artifacts.append(str(Path(args.log_path).expanduser()))

    context: dict[str, Any] = {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "created_at": now_iso(),
        "source_type": source,
        "source": {
            "task_id": args.task_id,
            "task_url": args.task_url,
            "robot_ip": args.ip,
            "frp_port": args.frp_port,
            "site_robot_ip": args.robot_ip,
            "log_path": args.log_path,
        },
        "symptom": args.symptom or "",
        "time_window": args.time_window or "",
        "robot_identity": robot_identity,
        "artifacts": artifacts,
        "knowledge_sources": normalize_multi(args.knowledge_source),
        "code_sources": normalize_multi(args.code_source),
        "analysis_route": [],
        "conclusion_status": "insufficient_data",
    }
    if source_material_dir:
        context["source_material_dir"] = str(source_material_dir)
    if teambition_bundle:
        context["teambition"] = {
            "task_json": str(source_material_dir.relative_to(case_dir) / "teambition-task.json") if source_material_dir else "raw/teambition-task.json",
            "activities_json": str(source_material_dir.relative_to(case_dir) / "teambition-activities.json") if source_material_dir else "raw/teambition-activities.json",
            "attachments_manifest": str(source_material_dir.relative_to(case_dir) / "teambition-attachments.json") if source_material_dir else "raw/teambition-attachments.json",
            "downloaded_count": len(teambition_bundle.get("downloaded_files", [])),
            "extracted_count": len(teambition_bundle.get("extracted_dirs", [])),
            "warning_count": len(teambition_bundle.get("warnings", [])),
            "warnings": teambition_bundle.get("warnings", []),
        }
    return context
