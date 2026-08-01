"""Playbook 加载器 —— 从 nav-manager 仓库读取 54 个错误码 Playbook"""

import re, yaml
from pathlib import Path
from typing import Any

# Playbook 文档所在目录
PLAYBOOK_DIR = Path("/home/zhr/zhr_ws/src/mainbody/nav-manager/docs/jstate_error_codes/nav-navigation-errors")


def load_playbook(error_code: str) -> dict | None:
    """加载单个错误码的 Playbook YAML

    Args:
        error_code: 如 "614028"

    Returns:
        {"meta": {...}, "steps": [...]} 或 None
    """
    if not PLAYBOOK_DIR.exists():
        return None

    # 找文件名: 614028-*.md
    matches = list(PLAYBOOK_DIR.glob(f"{error_code}-*.md"))
    if not matches:
        return None

    content = matches[0].read_text(encoding="utf-8")

    # 提取 YAML playbook 段
    blocks = list(re.finditer(r'```yaml\s*\n(.*?)```', content, re.DOTALL))
    for m in blocks:
        text = m.group(1).strip()
        if text.startswith("playbook:"):
            try:
                return yaml.safe_load(text).get("playbook", {})
            except yaml.YAMLError:
                return None
    return None


def execute_playbook(error_code: str, log_text: str = "") -> dict:
    """执行 Playbook 的确定性检查

    Args:
        error_code: 错误码
        log_text: 日志内容（grep 提取的片段）

    Returns:
        {
            "matched": bool,
            "error_code": str,
            "error_name": str,
            "trigger_chain": str,
            "root_cause": str,
            "confidence": "high|medium|low",
        }
    """
    playbook = load_playbook(error_code)
    if not playbook:
        return {
            "matched": False,
            "error_code": error_code,
            "error_name": "unknown",
            "trigger_chain": "",
            "root_cause": "",
            "confidence": "low",
        }

    meta = playbook.get("meta", {})
    steps = playbook.get("steps", [])

    if not steps:
        return {
            "matched": True,
            "error_code": error_code,
            "error_name": meta.get("error_name", ""),
            "trigger_chain": "no_steps",
            "root_cause": "",
            "confidence": "low",
        }

    # Step 1: 区分触发链
    classify_step = next((s for s in steps if "classify" in s["id"]), steps[0])

    for check in classify_step.get("checks", []):
        check_type = check.get("type", "")

        if check_type == "grep_log" and log_text:
            pattern = check.get("pattern", "")
            if pattern and re.search(pattern, log_text, re.IGNORECASE):
                on_match = check.get("on_match", {})
                return {
                    "matched": True,
                    "error_code": error_code,
                    "error_name": meta.get("error_name", ""),
                    "trigger_chain": on_match.get("trigger_chain", ""),
                    "root_cause": on_match.get("root_cause", ""),
                    "confidence": "high",
                }

        elif check_type == "on_no_match":
            # 兜底：扩大时间窗
            return {
                "matched": True,
                "error_code": error_code,
                "error_name": meta.get("error_name", ""),
                "trigger_chain": "unclassified",
                "root_cause": "待 LLM fallback 判断",
                "confidence": "low",
            }

    # 没有匹配到任何检查
    return {
        "matched": True,
        "error_code": error_code,
        "error_name": meta.get("error_name", ""),
        "trigger_chain": "unknown",
        "root_cause": "",
        "confidence": "low",
    }


def list_available_codes() -> list[str]:
    """列出所有可用的错误码"""
    if not PLAYBOOK_DIR.exists():
        return []
    codes = []
    for path in PLAYBOOK_DIR.glob("*.md"):
        code = path.name.split("-")[0]
        if code.isdigit():
            codes.append(code)
    return sorted(codes)


def load_all_playbook_metas() -> dict[str, dict]:
    """加载所有 Playbook 的 meta 信息（轻量，不含完整 steps）"""
    metas = {}
    for code in list_available_codes():
        playbook = load_playbook(code)
        if playbook:
            meta = playbook.get("meta", {})
            step_count = len(playbook.get("steps", []))
            metas[code] = {
                "error_name": meta.get("error_name", ""),
                "module": meta.get("module", ""),
                "step_count": step_count,
            }
    return metas


# ── 模块加载时打印可用 Playbook ──
if __name__ == "__main__":
    codes = list_available_codes()
    print(f"可用 Playbook: {len(codes)} 个")
    for code in codes[:5]:
        p = load_playbook(code)
        if p:
            print(f"  {code}: {p['meta'].get('error_name', '?')} ({len(p.get('steps', []))} steps)")
