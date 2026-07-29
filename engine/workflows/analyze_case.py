"""Analyze an existing Case and persist all derived artifacts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from engine.analysis.deterministic import DeterministicAnalyzer
from engine.utils import append_event, now_iso, write_json
from engine.reporting.reporter import render_case_reports


class Analyzer(Protocol):
    def analyze(self, case_dir: Path, context: dict[str, Any]) -> dict[str, Any]: ...


ExternalEnricher = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def analyze_case(
    case_dir: Path,
    context: dict[str, Any],
    *,
    analyzer: Analyzer | None = None,
    external_enricher: ExternalEnricher | None = None,
) -> dict[str, Any]:
    """Run analysis, render reports, and update Case state and audit trail."""
    summary = (analyzer or DeterministicAnalyzer()).analyze(case_dir, context)
    if external_enricher:
        summary = external_enricher(context, summary)

    updated_context = {**context}
    updated_context["analysis_route"] = summary["analysis_route"]
    updated_context["conclusion_status"] = summary["conclusion_status"]
    updated_context["analysis_summary"] = summary
    updated_context["updated_at"] = now_iso()
    write_json(case_dir / "context.json", updated_context)

    reports = render_case_reports(updated_context, summary)
    (case_dir / "report.md").write_text(reports.diagnosis_report, encoding="utf-8")
    (case_dir / "human-handoff.md").write_text(reports.human_handoff, encoding="utf-8")
    (case_dir / "knowledge-draft.md").write_text(reports.knowledge_draft, encoding="utf-8")

    status_value = "analyzed" if summary["conclusion_status"] in {"likely", "need_human"} else "needs_more_data"
    external = summary.get("external_evidence", {}) or {}
    trace = summary.get("analysis_trace", {}) or {}
    analysis_status = {
        "conclusion_status": summary["conclusion_status"],
        "scanned_files": summary["scanned_files"],
        "finding_count": len(summary["findings"]),
        "deep_insight_count": len(summary.get("deep_insights", [])),
        "specialty_finding_count": len(summary.get("specialty_findings", [])),
        "dingtalk_doc_count": len(external.get("dingtalk_docs", [])),
        "gitlab_project_count": len(external.get("gitlab_projects", [])),
        "problem_type": trace.get("problem_type", ""),
        "window_evidence_count": len(trace.get("window_evidence", [])),
        "analysis_route": summary["analysis_route"],
    }
    write_json(case_dir / "status.json", {
        "case_id": updated_context.get("case_id", case_dir.name),
        "status": status_value,
        "created_at": updated_context.get("created_at", ""),
        "updated_at": now_iso(),
        "next_action": "Review report.md and collect missing evidence listed in human-handoff.md",
        "analysis": analysis_status,
    })
    append_event(case_dir, "case_analyzed", {
        "conclusion_status": summary["conclusion_status"],
        "scanned_files": summary["scanned_files"],
        "finding_count": len(summary["findings"]),
        "deep_insight_count": len(summary.get("deep_insights", [])),
        "specialty_finding_count": len(summary.get("specialty_findings", [])),
        "problem_type": trace.get("problem_type", ""),
        "window_evidence_count": len(trace.get("window_evidence", [])),
        "external_evidence": {
            "dingtalk_doc_count": len(external.get("dingtalk_docs", [])),
            "gitlab_project_count": len(external.get("gitlab_projects", [])),
            "warning_count": len(external.get("warnings", [])),
        },
    })
    return updated_context
