"""Platform-neutral preparation and filtering for external evidence."""

from __future__ import annotations

import re
from typing import Any

from engine.analysis.material_scan import short_line
from engine.utils import merge_unique, normalize_multi


def evidence_keywords(context: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    candidates = list(normalize_multi(summary.get("error_codes")))
    for text in (str(context.get("symptom", "")), str(context.get("time_window", "")), " ".join(normalize_multi(summary.get("analysis_route")))):
        candidates.extend(word for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text) if word.lower() not in {"the", "and", "with", "error", "warn", "robot", "diagnosis"})
    candidates.extend(str(item.get("title", "")) for item in summary.get("deep_insights", []) or [])
    route_text = " ".join(normalize_multi(summary.get("analysis_route"))).lower()
    source_text = " ".join(normalize_multi(context.get("code_sources"))).lower()
    if "nav" in route_text or "nav" in source_text or re.search(r"导航|到点|路线|定位", str(context.get("symptom", ""))):
        candidates.extend(["导航", "nav-manager", "NavChecker", "diff_cur"])
    return merge_unique([], [item for item in candidates if item and len(item) <= 80])[:12]


def extract_block_texts(payload: dict[str, Any] | list[Any]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    blocks = payload.get("result", {}).get("data", [])
    if not isinstance(blocks, list):
        return []
    keys = {"heading": "heading", "paragraph": "paragraph", "unorderedList": "unorderedList", "orderedList": "orderedList", "blockquote": "blockquote"}
    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("blockType") not in keys:
            continue
        text = str(block.get(keys[block["blockType"]], {}).get("text", ""))
        if text.strip():
            texts.append(short_line(text, 260))
    return texts


def select_relevant_snippets(texts: list[str], keywords: list[str], limit: int = 5) -> list[str]:
    lowered = [item.lower() for item in keywords if item]
    selected = [text for text in texts if not lowered or any(keyword in text.lower() for keyword in lowered)]
    return selected[:limit] or texts[:limit]
