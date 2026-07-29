"""Deterministic problem classification and evidence routing rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from engine.analysis.material_scan import extract_error_codes
from engine.utils import merge_unique


MAX_LARGE_LOG_FILES = 8
NAVIGATION_LOG_PRIORITY = ["nav-manager", "localagent", "agent3", "web-service", "localiser", "tag_localiser", "servo-action", "safe_policy"]

PROBLEM_LOG_ROUTES = {
    "navigation_rotate": {"title": "导航旋转问题", "skills": ["teambition", "robot-diagnosis", "tb-navigation-ticket-triage"], "primary_logs": ["nav-manager", "localiser", "agent3"], "support_logs": ["localagent", "tag_localiser", "servo-action", "nav-checker", "safe_policy"], "keywords": [r"\bS_ROTATE\b", r"\bREACH_ROTATE\b", r"\bLongRevolve\b", r"\brevolve_slipped\b", r"\bspeed_confined\b", r"\bNavChecker\b.*\bspeed_limit\b", r"\bfeedback not align\b", r"\bmovebase_finished false\b"]},
    "navigation": {"title": "导航问题", "skills": ["teambition", "robot-diagnosis", "tb-navigation-ticket-triage"], "primary_logs": ["nav-manager", "localagent", "agent3"], "support_logs": ["localiser", "tag_localiser", "servo-action", "nav-checker", "safe_policy", "web-service"], "keywords": [r"\bnav\b", r"\bmove_base\b", r"\bS_[A-Z_]+\b", r"\bREACH_[A-Z_]+\b", r"\bLOCALIZED_NAVIGATION\b", r"\bTURN_(LEFT|RIGHT)\b"]},
    "safety": {"title": "安全问题", "skills": ["robot-diagnosis", "device-log-analyzer"], "primary_logs": ["nav-checker", "safe_policy_puber", "safe_policy"], "support_logs": ["nav-manager", "localiser", "servo-action"], "keywords": [r"\bNavChecker\b", r"\bspeed_limit\b", r"\bsafe\b", r"\bstop\b", r"安全"]},
    "task_chain": {"title": "任务链路问题", "skills": ["teambition", "robot-diagnosis", "task-engine-troubleshoot"], "primary_logs": ["localagent", "web-service", "agent3", "async-service"], "support_logs": ["carly-web", "jmother"], "keywords": [r"\bTask", r"\bmission\b", r"\bstep\b", r"\baction\b", r"任务|下发|取消|抢占"]},
    "device_sensor": {"title": "设备或传感器问题", "skills": ["robot-diagnosis", "device-log-analyzer"], "primary_logs": ["jzhw_node", "iosys_iobox", "iosys_camera", "carly_iplus_perception_node"], "support_logs": ["servo-action", "localiser"], "keywords": [r"laser|lidar|camera|pointcloud|sensor", r"激光|相机|点云|传感器"]},
}

ROUTE_KEYWORDS = {
    "device-log-analyzer": ["laser", "lidar", "camera", "jrosth", "jzhw", "iosys", "pointcloud", "point cloud", "激光", "相机", "点云", "传感器"],
    "task-engine-troubleshoot": ["agent", "async-service", "behavior", "behavior tree", "bt", "task", "web-service", "任务", "行为树", "下发", "卡住"],
    "robot-model-config": ["robot.yaml", "model", "车型", "机型", "参数", "/j3/"],
    "dingtalk-docs": ["error code", "error_code", "错误码"],
}


def is_navigation_problem(*texts: str) -> bool:
    combined = "\n".join(texts).lower()
    return any(keyword in combined for keyword in ["导航", "nav", "rotate", "revolve", "旋转", "打滑", "侧移", "定位", "locali", "move_base", "slip"])


def classify_problem_type(*texts: str) -> str:
    combined = "\n".join(texts).lower()
    if re.search(r"revolve|rotate|旋转|打滑|侧移|revolve_slipped|longrevolve", combined):
        return "navigation_rotate"
    if re.search(r"nav-checker|navchecker|safe[_ -]?policy|安全|急停|避障|限速", combined):
        return "safety"
    if re.search(r"任务|下发|取消|抢占|mission|task|localagent|web-service|async-service", combined):
        return "task_chain"
    if re.search(r"传感器|激光|相机|点云|jzhw|iosys|camera|lidar|laser|pointcloud", combined):
        return "device_sensor"
    return "navigation" if is_navigation_problem(*texts) else "general"


def route_spec_for(problem_type: str) -> dict[str, Any]:
    return PROBLEM_LOG_ROUTES.get(problem_type, {"title": "通用问题", "skills": ["robot-diagnosis"], "primary_logs": [], "support_logs": [], "keywords": []})


def normalize_log_name(path: Path) -> str:
    name = path.name
    name = re.sub(r"\.log(?:[.-]20\d{6})?(?:\.\d+)?$", ".log", name)
    return re.sub(r"\.log\.-20\d{6}$", ".log", name)


def log_priority_rank(path: Path, route_spec: dict[str, Any]) -> tuple[int, int, str]:
    name = normalize_log_name(path).lower()
    for index, keyword in enumerate(item.lower() for item in route_spec.get("primary_logs", [])):
        if keyword in name:
            return 0, index, name
    for index, keyword in enumerate(item.lower() for item in route_spec.get("support_logs", [])):
        if keyword in name:
            return 1, index, name
    return 2, 999, name


def prioritize_large_logs(files: list[Path], *texts: str) -> list[Path]:
    route_spec = route_spec_for(classify_problem_type(*texts))
    ranked = [(log_priority_rank(path, route_spec), path) for path in files]
    selected = [path for rank, path in sorted(ranked, key=lambda item: item[0]) if rank[0] < 2]
    if selected:
        return selected[:MAX_LARGE_LOG_FILES]
    if is_navigation_problem(*texts):
        ranked_nav: list[tuple[int, str, Path]] = []
        for path in files:
            name = path.name.lower()
            priority = next((index for index, keyword in enumerate(NAVIGATION_LOG_PRIORITY) if keyword in name), len(NAVIGATION_LOG_PRIORITY))
            if priority < len(NAVIGATION_LOG_PRIORITY):
                ranked_nav.append((priority, name, path))
        return [item[2] for item in sorted(ranked_nav)[:MAX_LARGE_LOG_FILES]]
    return files[:MAX_LARGE_LOG_FILES]


def prioritize_analysis_files(files: list[Path], route_spec: dict[str, Any]) -> list[Path]:
    return [path for _, path in sorted((log_priority_rank(path, route_spec), path) for path in files)]


def route_for_text(text: str, source_type: str) -> list[str]:
    lowered = text.lower()
    routes: list[str] = []
    if source_type == "internal_robot":
        routes.append("robot-peek")
    elif source_type == "remote_site":
        routes.extend(["remote-hand", "robot-peek"])
    elif source_type == "tb_task":
        routes.append("teambition")
    elif source_type == "local_logs":
        routes.append("robot-diagnosis")
    routes.append("robot-diagnosis")
    for skill, keywords in ROUTE_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            routes.append(skill)
    if extract_error_codes(text):
        routes.append("dingtalk-docs")
    return merge_unique([], routes)
