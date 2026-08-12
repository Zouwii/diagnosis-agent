"""Framework-neutral Case lifecycle runner for the compiled diagnosis graph."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _graph_app(version: str = "graph-v1"):
    """Get the compiled graph for the given version."""
    from agent.graph import GRAPHS
    return GRAPHS.get(version, GRAPHS["graph-v1"])


def graph_input(case_id: str, case: dict[str, Any], request: Any) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_dir": str(case.get("case_dir") or ""),
        "owner_safe": str(case.get("owner_safe") or ""),
        "input_root": str(case.get("input_root") or ""),
        "input_roots": list(case.get("input_roots") or []),
        "user_input": request.symptom,
        "symptom": request.symptom,
        "time_window": request.time_window or "",
        "source_type": request.mode,
        "selected_skill": str(case.get("selected_skill") or ""),
        "analysis_skill": str(case.get("analysis_skill") or "robot-diagnosis"),
        "extra_params": {
            "robot_ip": request.robot_ip,
            "task_url": request.task_url,
            "frp_port": request.frp_port,
            "site_robot_ip": request.site_robot_ip,
            "log_path": request.log_path,
            "knowledge_sources": request.knowledge_sources,
            "code_sources": request.code_sources,
            "external_evidence": getattr(request, "external_evidence", True) is not False,
        },
        "findings": [],
        "error_codes": [],
        "errors": [],
        "fallback_triggered": [],
    }


def available_report_path(result: dict[str, Any]) -> str | None:
    raw_path = str(result.get("report_path") or "").strip()
    case_dir = str(result.get("materials", {}).get("case_dir") or "").strip()
    if not raw_path or not case_dir:
        return None

    report_path = Path(raw_path).expanduser()
    if not report_path.is_absolute():
        report_path = Path.cwd() / report_path
    resolved_report = report_path.resolve()
    resolved_case = Path(case_dir).expanduser().resolve()
    if not resolved_report.is_relative_to(resolved_case) or not resolved_report.is_file():
        return None
    return str(resolved_report)


async def run_diagnosis(
    case_id: str,
    case: dict[str, Any],
    request: Any,
    version: str = "graph-v1",
    persist: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Execute LangGraph and update the mutable API Case record in place."""
    if version == "claude-origin-v1":
        await _run_claude_origin(case_id, case, request, persist=persist)
        return
    try:
        update_status(case, "collecting", f"开始诊断 [{version}]: {request.symptom}")
        add_progress(case, "graph", f"LangGraph 工作流已启动 (version={version})", event="node_start")
        if persist:
            persist(case)
        config = {"configurable": {"thread_id": case_id}}
        result = await _graph_app(version).ainvoke(graph_input(case_id, case, request), config)

        case["source_type"] = result.get("source_type", case["source_type"])
        case["conclusion_status"] = result.get("conclusion_status")
        case["materials"] = result.get("materials", {})
        case["errors"] = result.get("errors", [])
        add_progress(case, "graph", "LangGraph 工作流执行完成")
        if persist:
            persist(case)

        materials = case["materials"]
        if not materials.get("collected", False):
            error = materials.get("error") or "; ".join(case["errors"]) or "材料采集未完成"
            raise RuntimeError(error)

        report_path = available_report_path(result)
        if report_path:
            case["report_path"] = report_path
            case["report_url"] = f"/api/cases/{case_id}/report"

        final_status = "closed" if case["conclusion_status"] in {"confirmed", "likely"} else "awaiting_human"
        message = "诊断完成，等待人工处理" if final_status == "awaiting_human" else "诊断完成"
        update_status(case, final_status, message)
        if persist:
            persist(case)
    except Exception as exc:
        update_status(case, "failed", str(exc))
        case["error"] = str(exc)
        if persist:
            persist(case)


async def _run_claude_origin(
    case_id: str,
    case: dict[str, Any],
    request: Any,
    *,
    persist: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Run the stable Claude path without changing legacy graph semantics."""
    try:
        update_status(case, "collecting", f"开始诊断 [claude-origin-v1]: {request.symptom}")
        if persist:
            persist(case)

        from server.claude_origin import ClaudeOriginRunner

        runner = ClaudeOriginRunner(
            case_id,
            case,
            request,
            persist=persist,
            progress=lambda node, message, event: add_progress(case, node, message, event=event),
        )
        result = await asyncio.to_thread(runner.run)
        case["runtime"] = {
            "name": "claude-origin-v1",
            "session_id": result.session_id,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        }
        if result.collection:
            artifacts = list(result.collection.get("artifacts") or [])
            case["materials"] = {
                "collected": bool(artifacts),
                "source": result.collection.get("source") or request.mode,
                "case_id": case_id,
                "case_dir": str(case.get("case_dir") or ""),
                "raw_dir": str(Path(str(case.get("case_dir") or "")) / "raw"),
                "artifacts": artifacts,
                "warnings": list(result.collection.get("warnings") or []),
            }
        if not result.ok:
            raise RuntimeError(result.error or "Claude 原版诊断失败")
        case["conclusion_status"] = "need_human"
        case["report_path"] = result.report_path
        case["report_url"] = f"/api/cases/{case_id}/report"
        update_status(case, "awaiting_human", "诊断完成，等待人工确认")
        if persist:
            persist(case)
    except Exception as exc:
        update_status(case, "failed", str(exc))
        case["error"] = str(exc)
        if persist:
            persist(case)


def update_status(case: dict[str, Any], status: str, message: str = "") -> None:
    case["status"] = status
    case["updated_at"] = datetime.now(timezone.utc).isoformat()
    if message:
        add_progress(case, status, message)


def add_progress(case: dict[str, Any], node: str, message: str, event: str = "node_complete") -> None:
    case["progress_events"].append(
        {
            "event": event,
            "node": node,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
