"""Report node — sets final state after engine analysis has written report files."""

from __future__ import annotations

from pathlib import Path

from agent.state import DiagnosisState


async def write_report_node(state: DiagnosisState) -> DiagnosisState:
    """Collect conclusion from engine analysis context. Report files already on disk."""
    case_dir = Path(str(state.get("case_dir") or ""))
    context = dict(state.get("context") or {})

    conclusion = str(context.get("conclusion_status") or "insufficient_data")

    return {
        "report_path": str(case_dir / "report.md"),
        "knowledge_draft_path": str(case_dir / "knowledge-draft.md"),
        "conclusion_status": conclusion,
    }
