"""Platform-independent orchestration of read-only external evidence."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import datetime
from typing import Any

from engine.utils import merge_unique, normalize_multi


EvidenceCollector = Callable[[dict[str, Any], dict[str, Any]], tuple[list[dict[str, Any]], list[str]]]


def enrich_summary_with_external_evidence(
    context: dict[str, Any],
    summary: dict[str, Any],
    *,
    collect_dingtalk: EvidenceCollector,
    collect_gitlab: EvidenceCollector,
    now: Callable[[], str],
) -> dict[str, Any]:
    """Add provider results without allowing providers to alter local findings."""
    enriched = copy.deepcopy(summary)
    dingtalk_docs, dingtalk_warnings = collect_dingtalk(context, enriched)
    gitlab_projects, gitlab_warnings = collect_gitlab(context, enriched)
    enriched["external_evidence"] = {
        "collected_at": now(),
        "dingtalk_docs": dingtalk_docs,
        "gitlab_projects": gitlab_projects,
        "warnings": [*dingtalk_warnings, *gitlab_warnings],
    }
    routes = normalize_multi(enriched.get("analysis_route"))
    if dingtalk_docs:
        routes.append("dingtalk-docs")
    if gitlab_projects:
        routes.append("gitlab-operator")
    enriched["analysis_route"] = merge_unique([], routes)
    return enriched
