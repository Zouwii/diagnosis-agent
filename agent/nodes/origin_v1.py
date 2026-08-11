"""origin-v1 compatibility node.

origin-v1 is deliberately a single LangGraph node: it executes the migrated
diagnosis_cli workflow once, preserving the original orchestrator's complete
collection, analysis, evidence, and reporting behavior.
"""

from __future__ import annotations

from agent.logger import log
from agent.nodes.run_cli import _request_from_state
from agent.state import DiagnosisState
from engine.analysis.external_providers import enrich_with_external_evidence
from engine.utils import now_iso, write_json
from engine.workflows import run_case


def _result_state(state: DiagnosisState, request, result) -> DiagnosisState:
    context = result.context
    summary = dict(context.get("analysis_summary") or {})
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

    specialty = summary.get("specialty_findings", []) or []
    return {
        "materials": materials,
        "collected_at": str(context.get("created_at") or now_iso()),
        "context": context,
        "analysis_summary": summary,
        "findings": list(summary.get("findings") or []),
        "error_codes": list(summary.get("error_codes") or []),
        "problem_type": str((summary.get("analysis_trace") or {}).get("problem_type") or "general"),
        "deep_insights": list(summary.get("deep_insights") or []),
        "specialty_hits": [str(item.get("skill") or item.get("title") or "") for item in specialty],
        "analysis_route": list(summary.get("analysis_route") or []),
        "conclusion_status": str(context.get("conclusion_status") or "insufficient_data"),
        "report_path": str(case_dir / "report.md"),
        "knowledge_draft_path": str(case_dir / "knowledge-draft.md"),
    }


async def run_origin_v1(state: DiagnosisState) -> DiagnosisState:
    """Run the complete migrated diagnosis_cli flow exactly once."""
    request = _request_from_state(state)
    log("origin-v1", "完整 diagnosis_cli 开始", source_type=request.source_type, case_id=request.case_id)

    # RunCaseRequest defaults to analyze=True. Keep that flag intact: origin-v1
    # is the compatibility path and must not degrade into collection-only work.
    result = run_case(
        request,
        external_enricher=(
            enrich_with_external_evidence if request.external_evidence else None
        ),
    )
    update = _result_state(state, request, result)
    log(
        "origin-v1",
        "完整 diagnosis_cli 完成",
        case_id=request.case_id,
        findings=len(update["findings"]),
        conclusion=update["conclusion_status"],
    )
    return update
