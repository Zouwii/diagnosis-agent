"""Unified Reporter entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.reporting.renderers import render_diagnosis_report, render_human_handoff, render_knowledge_draft


@dataclass(frozen=True)
class ReportArtifacts:
    diagnosis_report: str
    human_handoff: str
    knowledge_draft: str


def render_case_reports(context: dict[str, Any], summary: dict[str, Any]) -> ReportArtifacts:
    return ReportArtifacts(
        diagnosis_report=render_diagnosis_report(context, summary),
        human_handoff=render_human_handoff(context, summary),
        knowledge_draft=render_knowledge_draft(context, summary),
    )
