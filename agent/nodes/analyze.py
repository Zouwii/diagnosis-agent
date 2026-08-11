"""Diagnosis engine analysis node — deterministic log scan, playbook, timeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.state import DiagnosisState
from engine.workflows.analyze_case import analyze_case
from engine.analysis.external_providers import enrich_with_external_evidence


async def analyze_engine(state: DiagnosisState) -> DiagnosisState:
    """Run engine deterministic analysis on collected materials."""
    case_dir = Path(str(state.get("case_dir") or ""))
    context = dict(state.get("context") or {})

    extra_params = state.get("extra_params", {})
    enricher = enrich_with_external_evidence if extra_params.get("external_evidence", True) else None
    context = analyze_case(case_dir, context, external_enricher=enricher)

    summary = dict(context.get("analysis_summary") or {})
    specialty = summary.get("specialty_findings", []) or []

    return {
        "context": context,
        "analysis_summary": summary,
        "findings": list(summary.get("findings") or []),
        "error_codes": list(summary.get("error_codes") or []),
        "problem_type": str((summary.get("analysis_trace") or {}).get("problem_type") or "general"),
        "deep_insights": list(summary.get("deep_insights") or []),
        "specialty_hits": [str(item.get("skill") or item.get("title") or "") for item in specialty],
        "analysis_route": list(summary.get("analysis_route") or []),
    }
