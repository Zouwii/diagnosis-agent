"""Deterministic deep-insight rules for prepared Case evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from engine.analysis.deep_insights import count_pattern, parse_emma_errors, parse_stopped_watchers, parse_version_mismatches
from engine.analysis.material_scan import read_text_lossy, short_line


def _read(case_dir: Path, relative_path: str) -> str:
    try:
        return read_text_lossy(case_dir / relative_path)
    except OSError:
        return ""


def _matches(text: str, patterns: list[str], limit: int = 5) -> list[str]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    return [short_line(line) for line in text.replace("\x00", "").splitlines() if any(pattern.search(line) for pattern in compiled)][:limit]


def build_deep_insights(case_dir: Path, context: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the existing jstate, localisation, version, process, and navigation insights."""
    del context
    insights: list[dict[str, Any]] = []
    emma = _read(case_dir, "raw/robot/emma-status.txt")
    recent = _read(case_dir, "raw/robot/recent-errors.log")
    version = _read(case_dir, "raw/robot/version.txt")
    processes = _read(case_dir, "raw/robot/processes.txt")
    agent = _read(case_dir, "raw/robot/agent3-tail.log")

    for item in parse_emma_errors(emma):
        if item.get("trigger", "").lower() != "true":
            continue
        level = item.get("level", "")
        insights.append({
            "severity": "P1" if level.upper() in {"ERROR", "FATAL"} else "P2",
            "title": "当前活跃 jstate 告警",
            "conclusion": f"{item.get('name', 'jstate error')} 当前仍处于触发状态，details={item.get('details') or '-'}，level={level or '-'}，timestamp={item.get('timestamp') or '-'}。",
            "evidence": ["raw/robot/emma-status.txt: emma_errors", *_matches(emma, [re.escape(item.get("name", "")), "details:", "level:", "trigger:"], 4)],
            "action": "优先按该 jstate 对应模块排查；如果用户现象是错误码告警，需要用钉钉错误码 SOP 将 sub_id/错误码与该 jstate 做映射确认。",
        })

    odom = count_pattern(recent, r"target_frame does not exist|base2odom_stamped")
    matching = count_pattern(recent, r"Matching failed")
    localisation = count_pattern(recent, r"Locali[sz]ation failed")
    if odom or matching or localisation:
        evidence = _matches(recent, [r"target_frame does not exist", r"Matching failed", r"Locali[sz]ation failed"], 6)
        insights.append({
            "severity": "P1" if localisation or matching else "P2",
            "title": "定位/TF 链路异常",
            "conclusion": f"近期日志中 TF/定位链路异常明显：base2odom/odom 缺失 {odom} 次，scan matching 失败 {matching} 次，localisation failed {localisation} 次。这更接近 AGV 行走异常、摆动或定位类错误的直接技术链路。",
            "evidence": [f"raw/robot/recent-errors.log: {line}" for line in evidence],
            "action": "继续检查 odom 发布源、localiser/cartographer 输入点云、当前地图与传感器外参；必要时按 device-log-analyzer 查看 jrosth/jzhw 与点云数据质量。",
        })

    title, mismatches = parse_version_mismatches(version)
    important = [item for item in mismatches if re.search(r"carly-web|cartographer|vtr-iplus|map-manager|nav-manager|jcar3-params|jrosth|jzhw|emma-safe", item, re.IGNORECASE)]
    if important:
        insights.append({"severity": "P2", "title": "导航/定位相关包版本不一致", "conclusion": f"{title or 'jz_total_display'} 显示多项导航/定位相关包与目标分布版本不一致，这会放大定位、地图、传感器链路问题的排查风险，不能只按单个错误码处理。", "evidence": important[:8], "action": "确认该车是否允许处于当前混装版本；若不是预期状态，先对齐 jz-total 分布版本或查对应 MR/发版说明。"})

    stopped = parse_stopped_watchers(processes)
    if stopped:
        insights.append({"severity": "P2", "title": "关键进程未运行", "conclusion": f"circusctl status 中存在非白名单 stopped watcher：{', '.join(stopped)}。", "evidence": [f"raw/robot/processes.txt: {name}: stopped" for name in stopped], "action": "确认这些 watcher 是否对当前车型/任务必需；如果必需，查看 circus.log 和对应程序日志定位退出原因。"})

    faults = _matches(agent, [r"fault_default"], 8)
    if faults:
        insights.append({"severity": "P2", "title": "近期多次进入 fault_default", "conclusion": "agent3 尾部记录显示近几天多次进入 fault_default，说明不是一次性的瞬时异常。", "evidence": [f"raw/robot/agent3-tail.log: {line}" for line in faults], "action": "按 fault_default 出现时间回溯 agent3/circus/localiser/nav-manager 日志，确认故障首次触发点。"})

    nav = [item for item in findings if re.search(r"S_ROTATE|REACH_ROTATE|LongRevolve|revolve_slipped|speed_confined|NavChecker.*speed_limit|movebase_finished false|feedback not align", str(item.get("text", "")), re.IGNORECASE) or ("nav-manager" in str(item.get("source_file") or item.get("file", "")).lower() and item.get("evidence_type") == "time_window")]
    if nav:
        insights.append({"severity": "P2", "title": "导航旋转主链路命中", "conclusion": "问题时间窗口内 `nav-manager` 已命中旋转、到点、限速或 movebase 状态相关证据，当前应优先按导航旋转控制链路排查，而不是按全局 ERROR/WARN 定根因。", "evidence": [f"{item['file']}:{item['line']} {item['text']}" for item in nav[:8]], "action": "围绕 `nav-manager` 时间窗口继续对齐 `agent3` 上层状态、`localiser` 定位状态和 `nav-checker` 限速/安全状态；确认是否为旋转阶段侧移、定位跳动或限速策略导致。"})

    if not insights and findings:
        insights.append({"severity": "P3", "title": "仅有通用异常关键词", "conclusion": "本轮只命中通用 ERROR/WARN，尚未形成可解释用户现象的模块级链路。", "evidence": [f"{item['file']}:{item['line']} {item['text']}" for item in findings[:5]], "action": "补充更精确的问题时间点，扩大该时间点前后关键服务日志采集范围。"})
    return insights
