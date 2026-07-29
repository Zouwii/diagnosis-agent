"""Specialty evidence and historical Case recall for deterministic analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.analysis.material_scan import iter_analysis_files, read_text_lossy, short_line
from engine.utils import merge_unique


def build_specialty_findings(case_dir: Path, context: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    del context
    specialty: list[dict[str, Any]] = []
    route_specs = [
        ("task-engine-troubleshoot", "任务链路专项命中", [r"TaskNaviService", r"TaskActionService", r"BehaviorTree|behaviou?r tree|\bBT\b", r"route/(error|webservice)", r"preempt|cancel|blackboard|endpointDis|trigger_distance", r"任务|行为树|下发|抢占|取消"], "按 `task-engine-troubleshoot` 继续定界 carly-web / web-service / async-service / agent；先确认是否真的涉及 BT。"),
        ("device-log-analyzer", "设备/传感器专项命中", [r"jrosth|jzhw|iosys", r"laser|lidar|camera|pointcloud", r"disconnect|Connection activation failed|Failed to register publisher|check device cost", r"激光|相机|点云|传感器|驱动"], "按 `device-log-analyzer` 检查 jrosth/jzhw/iosys 日志、设备连接、点云或相机数据链路。"),
        ("robot-model-config", "机型/参数专项命中", [r"robot\.ya?ml|j3/", r"jz_total_display|-->|version mismatch", r"model|车型|机型|参数"], "按 `robot-model-config` 核对 robot.yaml、j3 参数、车型配置和版本分布一致性。"),
    ]
    files = iter_analysis_files(case_dir)
    for skill, title, patterns, action in route_specs:
        evidence: list[str] = []
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for path in files:
            try:
                text = read_text_lossy(path)
            except OSError:
                continue
            for line_no, raw in enumerate(text.splitlines(), start=1):
                line = short_line(raw)
                if any(pattern.search(line) for pattern in compiled):
                    evidence.append(f"{path.relative_to(case_dir)}:{line_no} {line}")
                    break
            if len(evidence) >= 5:
                break
        hits = [f"{item['file']}:{item['line']} {item['text']}" for item in findings if any(pattern.search(str(item.get("text", ""))) for pattern in compiled)]
        evidence = merge_unique(evidence, hits[:5])
        if evidence:
            specialty.append({"skill": skill, "title": title, "evidence": evidence[:8], "action": action})
    return specialty


def recall_similar_cases(case_dir: Path, problem_type: str, symptom: str) -> list[dict[str, Any]]:
    root = case_dir.parent
    if not root.exists():
        return []
    tokens = set(re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", symptom.lower()))
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for context_path in root.glob("*/context.json"):
        if context_path.parent == case_dir:
            continue
        try:
            data = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = data.get("analysis_summary", {}) or {}
        other_type = str((summary.get("analysis_trace", {}) or {}).get("problem_type", ""))
        other_tokens = set(re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", str(data.get("symptom", "")).lower()))
        score = (5 if other_type and other_type == problem_type else 0) + len(tokens & other_tokens)
        if score:
            candidates.append((score, str(data.get("updated_at") or data.get("created_at") or ""), {"case_id": data.get("case_id", context_path.parent.name), "case_dir": str(context_path.parent), "problem_type": other_type, "symptom": data.get("symptom", ""), "conclusion_status": summary.get("conclusion_status", data.get("conclusion_status", "")), "report": str(context_path.parent / "report.md"), "score": score}))
    return [item[2] for item in sorted(candidates, key=lambda item: (-item[0], item[1]))[:5]]
