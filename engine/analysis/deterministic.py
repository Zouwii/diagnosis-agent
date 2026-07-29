"""Complete deterministic analysis pipeline for a prepared diagnosis Case."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from engine.analysis.deep_rules import build_deep_insights
from engine.analysis.insights import build_specialty_findings, recall_similar_cases
from engine.analysis.material_scan import (
    classify_line,
    extract_error_codes,
    iter_analysis_files,
    iter_large_analysis_files,
    read_text_lossy,
    short_line,
)
from engine.analysis.routing import (
    classify_problem_type,
    log_priority_rank,
    prioritize_analysis_files,
    prioritize_large_logs,
    route_for_text,
    route_spec_for,
)
from engine.analysis.timeline import extract_date_stamp, extract_time_prefixes, parse_target_time, sort_findings, time_distance_seconds
from engine.analysis.windowing import build_window_evidence, safe_relative_text
from engine.utils import merge_unique, now_iso


MAX_FINDINGS = 80
MAX_FINDINGS_PER_FILE = 8
MAX_LARGE_LOG_FINDINGS_PER_FILE = 12
LARGE_LOG_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bS_ROTATE\b", r"\bREACH_ROTATE\b", r"\bLongRevolve\b",
        r"\bNavChecker\b.*\bspeed_limit\b", r"\bspeed_confined\b",
        r"\breset move_base\b", r"\bfeedback not align\b", r"\bunsame task\b",
        r"\bmovebase_finished false\b", r"\bFailed to parse HTTP response as JSON\b",
        r"\bPerception Is Paused\b", r"\btop_state\b", r"\bTURN_(LEFT|RIGHT)\b",
        r"\bLOCALIZED_NAVIGATION\b",
    )
]


class DeterministicAnalyzer:
    """Run the existing rules pipeline and return a structured summary."""

    def analyze(self, case_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
        return analyze_case_materials(case_dir, context)


def analyze_case_materials(case_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
    files = iter_analysis_files(case_dir)
    large_files = iter_large_analysis_files(case_dir)
    symptom = str(context.get("symptom", ""))
    time_window = str(context.get("time_window", ""))
    source_type = str(context.get("source_type", ""))
    problem_type = classify_problem_type(symptom, time_window, source_type)
    route_spec = route_spec_for(problem_type)
    date_stamp = extract_date_stamp(time_window, symptom, *[path.name for path in [*files, *large_files]])
    target_time = parse_target_time(time_window) or parse_target_time(symptom)
    files = prioritize_analysis_files(files, route_spec)
    large_files = prioritize_large_logs(large_files, symptom, time_window, source_type)
    route_text_parts = [symptom, time_window]
    findings: list[dict[str, Any]] = []
    scanned_files = skipped_files = 0
    trace: dict[str, Any] = {
        "problem_type": problem_type,
        "problem_title": route_spec.get("title", "通用问题"),
        "date_stamp": date_stamp,
        "target_time": target_time.strftime("%H:%M:%S") if target_time else "",
        "route_primary_logs": route_spec.get("primary_logs", []),
        "route_support_logs": route_spec.get("support_logs", []),
        "small_file_candidates": [safe_relative_text(path, case_dir) for path in files[:30]],
        "large_file_candidates": [safe_relative_text(path, case_dir) for path in large_files[:30]],
        "window_evidence": [],
        "coverage": [],
    }

    symptom_codes = extract_error_codes(symptom)
    code_patterns = [re.compile(rf"(?<![\d.]){re.escape(code)}(?![\d.])") for code in symptom_codes]
    route_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in route_spec.get("keywords", [])]

    for path in files:
        try:
            text = read_text_lossy(path)
        except OSError:
            skipped_files += 1
            continue
        if not text:
            skipped_files += 1
            continue
        scanned_files += 1
        route_text_parts.extend([path.name, text[:2000]])
        per_file = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            level = classify_line(line)
            code_hit = any(pattern.search(line) for pattern in code_patterns)
            if not level and not code_hit:
                continue
            findings.append({"level": level or "code", "file": str(path.relative_to(case_dir)), "line": line_no, "text": short_line(line)})
            per_file += 1
            if len(findings) >= MAX_FINDINGS or per_file >= MAX_FINDINGS_PER_FILE:
                break
        trace["coverage"].append({"file": safe_relative_text(path, case_dir), "mode": "small_full_scan", "findings": per_file})
        if len(findings) >= MAX_FINDINGS:
            break

    window_records = build_window_evidence(case_dir=case_dir, files=[*files, *large_files], target_time=target_time, date_stamp=date_stamp, route_spec=route_spec, minutes=5)
    trace["window_evidence"] = window_records
    if window_records and not any(record.get("matched_lines") for record in window_records) and target_time:
        window_records = build_window_evidence(case_dir=case_dir, files=[*files, *large_files], target_time=target_time, date_stamp=date_stamp, route_spec=route_spec, minutes=10)
        trace["expanded_window_evidence"] = window_records
        trace["window_evidence"] = window_records

    for record in window_records:
        window_file = record.get("window_file")
        if not window_file or not record.get("matched_lines"):
            trace["coverage"].append({"file": record.get("source_file", ""), "mode": "time_window", "findings": 0, "note": record.get("error") or "window has no matching lines"})
            continue
        path = case_dir / str(window_file)
        priority_candidates: list[dict[str, Any]] = []
        generic_candidates: list[dict[str, Any]] = []
        scanned_this_file = False
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_no, line in enumerate(handle, start=1):
                    level = classify_line(line)
                    code_hit = any(pattern.search(line) for pattern in code_patterns)
                    context_hit = any(pattern.search(line) for pattern in LARGE_LOG_CONTEXT_PATTERNS)
                    route_hit = any(pattern.search(line) for pattern in route_patterns)
                    if not level and not code_hit and not context_hit and not route_hit:
                        continue
                    if not scanned_this_file:
                        scanned_files += 1
                        route_text_parts.append(str(record.get("source_file", "")))
                        scanned_this_file = True
                    item = {"level": level or ("code" if code_hit else "context"), "file": str(window_file), "line": line_no, "text": short_line(line), "source_file": record.get("source_file", ""), "evidence_type": "time_window", "distance_seconds": time_distance_seconds(line, target_time), "route_hit": route_hit or context_hit or code_hit}
                    if item["route_hit"]:
                        priority_candidates.append(item)
                    elif len(generic_candidates) < 300:
                        generic_candidates.append(item)
        except OSError:
            skipped_files += 1
            trace["coverage"].append({"file": str(window_file), "mode": "time_window_scan", "findings": 0, "note": "failed to read window file"})
            continue
        selected = sorted(priority_candidates, key=lambda item: (int(item.get("distance_seconds", 999999)), str(item.get("level", "")) != "context", int(item.get("line", 0))))
        if len(selected) < MAX_LARGE_LOG_FINDINGS_PER_FILE:
            selected.extend(sorted(generic_candidates, key=lambda item: (int(item.get("distance_seconds", 999999)), int(item.get("line", 0))))[:MAX_LARGE_LOG_FINDINGS_PER_FILE - len(selected)])
        selected = selected[:MAX_LARGE_LOG_FINDINGS_PER_FILE]
        findings.extend(selected)
        trace["coverage"].append({"file": str(window_file), "source_file": record.get("source_file", ""), "mode": "time_window_scan", "findings": len(selected), "priority_candidates": len(priority_candidates)})

    if not window_records:
        prefixes = extract_time_prefixes(time_window)
        if prefixes:
            for path in large_files:
                per_file = 0
                scanned_this_file = False
                try:
                    with path.open("r", encoding="utf-8", errors="replace") as handle:
                        for line_no, line in enumerate(handle, start=1):
                            if not any(prefix in line for prefix in prefixes):
                                continue
                            level = classify_line(line)
                            code_hit = any(pattern.search(line) for pattern in code_patterns)
                            context_hit = any(pattern.search(line) for pattern in LARGE_LOG_CONTEXT_PATTERNS)
                            if not level and not code_hit and not context_hit:
                                continue
                            if not scanned_this_file:
                                scanned_files += 1
                                route_text_parts.append(path.name)
                                scanned_this_file = True
                            findings.append({"level": level or ("code" if code_hit else "context"), "file": str(path.relative_to(case_dir)), "line": line_no, "text": short_line(line), "evidence_type": "time_prefix"})
                            per_file += 1
                            if per_file >= MAX_LARGE_LOG_FINDINGS_PER_FILE:
                                break
                except OSError:
                    skipped_files += 1
                    continue
                trace["coverage"].append({"file": safe_relative_text(path, case_dir), "mode": "large_time_prefix_scan", "findings": per_file})

    route_text = "\n".join(route_text_parts)
    routes = merge_unique(route_for_text(route_text, source_type), [str(item) for item in route_spec.get("skills", [])])
    findings = sort_findings(findings, time_window)
    primary = [item for item in findings if log_priority_rank(Path(str(item.get("source_file") or item.get("file", ""))), route_spec)[0] == 0]
    supporting = [item for item in findings if item not in primary]
    deep = build_deep_insights(case_dir, context, findings)
    specialty = build_specialty_findings(case_dir, context, findings)
    similar = recall_similar_cases(case_dir, problem_type, symptom)
    conclusion_status = "likely" if deep or findings else ("need_human" if scanned_files else "insufficient_data")
    return {
        "analyzed_at": now_iso(), "scanned_files": scanned_files, "skipped_files": skipped_files,
        "findings": findings, "primary_findings": primary, "supporting_findings": supporting,
        "deep_insights": deep, "specialty_findings": specialty,
        "error_codes": extract_error_codes(symptom, route_text),
        "analysis_route": merge_unique(routes, [item["skill"] for item in specialty]),
        "analysis_trace": trace, "similar_cases": similar, "conclusion_status": conclusion_status,
    }
