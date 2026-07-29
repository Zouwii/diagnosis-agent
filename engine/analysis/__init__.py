"""Diagnosis Analyzer package.

This package turns material already stored in a diagnosis Case into a
structured ``analysis_summary``. It does not create Cases, collect source
material, or render user-facing reports.

Files and responsibilities
--------------------------

``case_analyzer.py``
    Defines the public ``CaseAnalyzer`` protocol. A rules analyzer, an AI
    analyzer, or a future multimodal analyzer should expose the same
    ``analyze(case_dir, context)`` method.

``deterministic.py``
    Entry point and coordinator for the current rules-based analyzer. During
    migration it still accepts the legacy implementation through dependency
    injection so existing Case output remains compatible.

``material_scan.py``
    Discovers readable files under ``raw/`` and ``extracted/``, separates
    small and large logs, reads text safely, classifies fatal/error/warn lines,
    and extracts error codes.

``routing.py``
    Classifies the problem domain, ranks primary/supporting logs, and selects
    relevant specialist Skills from symptoms and evidence.

``timeline.py``
    Parses dates and times, measures evidence distance from the incident time,
    checks time windows, and sorts findings chronologically.

``insights.py``
    Builds specialist evidence for task, device, and model/config analysis,
    and recalls similar historical Cases.

``deep_insights.py``
    Contains reusable parsers for Emma/jstate output, package-version
    mismatches, stopped watchers, and repeated log patterns.

``deep_rules.py``
    Applies deeper rules to parsed robot evidence: active jstate alarms,
    TF/localisation failures, version drift, stopped processes, fault history,
    and navigation-rotation chains.

``evidence_selection.py``
    Produces external-search keywords, extracts DingTalk document blocks, and
    selects snippets relevant to the current Case.

``external_evidence.py``
    Merges read-only DingTalk and GitLab evidence into ``analysis_summary``,
    preserves provider warnings, and updates evidence-backed routes. Provider
    authentication and HTTP adapters are still being migrated from the CLI.

Execution order
---------------

The intended deterministic flow is::

    CaseAnalyzer
      -> DeterministicAnalyzer
      -> material_scan
      -> routing
      -> timeline
      -> insights + deep_insights/deep_rules
      -> evidence_selection + external_evidence (optional)
      -> analysis_summary

The AI analyzer will reuse these evidence-producing modules and the structured
output contract. It should add hypotheses and cross-source reasoning rather
than duplicate Case collection or report rendering.
"""
