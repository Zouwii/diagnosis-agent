#!/usr/bin/env python3
"""Add loadable, read-only Playbooks to legacy B/C Agent documents."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
AGENT_DIR = ROOT / "agent"
BLOCK_RE = re.compile(r"```yaml\s*\n(?P<body>\s*playbook:\s*\n.*?)```", re.DOTALL)
PATTERN_RE = re.compile(r'pattern:\s*["\']([^"\']+)["\']')


def valid_playbook(content: str) -> bool:
    for match in BLOCK_RE.finditer(content):
        try:
            data = yaml.safe_load(match.group("body"))
        except yaml.YAMLError:
            continue
        playbook = data.get("playbook") if isinstance(data, dict) else None
        if isinstance(playbook, dict) and playbook.get("steps"):
            return True
    return False


def metadata(path: Path) -> tuple[str, str, str]:
    code, slug = path.stem.split("-", 1)
    name = re.sub(r"^error_(nav-net|carrier-rotater|speed-manager)_", "", slug)
    module = next(
        (item for item in ("nav-net", "carrier-rotater", "speed-manager") if item in slug),
        "nav-manager",
    )
    return code, name, module


def patterns(content: str, code: str, name: str) -> list[str]:
    found: list[str] = []
    for value in PATTERN_RE.findall(content):
        value = value.strip().replace(";", "")
        if value and value not in found:
            found.append(value)
    return (found or [f"{code}|{name}"])[:2]


def diagnosis_section(code: str, module: str, pattern: str) -> str:
    return f'''## 3 结合日志选择排查方向

最小证据范围为错误发生前后 60 秒的 `{module}` 日志。只读检索：

```bash
grep -E '{pattern}' /opt/jz/log/{module}.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 原始错误上报 | 同一时间窗命中 `{code}` 或直接触发日志 | 无匹配 | 扩大时间窗并核对进程、版本；标记 `证据不足` |
| 2 | 直接触发字段 | 日志字段与第 1 章源码条件一致 | 字段缺失或条件不一致 | 不推断现场根因，保留同期原始日志 |
| 3 | 上游关联日志 | 能找到触发前最早异常 | 只有结果码 | 输出 `待确认`，交由人工补充上游日志 |

停止规则：没有同期直接触发日志时，Agent 只能说明代码触发条件，不得把可能原因写成已确认根因。'''


def evidence_section(code: str, name: str, module: str) -> str:
    return f'''## 5 修复验证与证据索引

Agent 最少输出错误时间窗、模块版本、原始错误行、直接触发字段、关联日志和缺失证据。验证仅检查同场景复测中错误是否再次出现，不执行配置修改、服务重启或车辆控制。

```yaml
error_code: "{code}"
error_name: "{name}"
analysis_status: 待确认
applicable_version:
  primary_module: "{module}"
confirmed_facts: []
most_likely_cause:
  cause: ""
  confidence: low
  evidence: []
missing_evidence: []
next_action: []
verification:
  result: not_started
  evidence: []
```'''


def playbook_section(code: str, name: str, module: str, pats: list[str]) -> str:
    trigger, upstream = pats[0], pats[-1]
    check = lambda pattern, yes, no, goto_yes, goto_no: {
        "type": "grep_log", "module": module, "pattern": pattern,
        "on_match": {"conclusion": yes, "priority": "P1", "goto": goto_yes},
        "on_no_match": {"conclusion": no, "goto": goto_no},
    }
    data = {"playbook": {"meta": {
        "error_code": code, "error_name": name, "module": module,
        "time_window": 60, "read_only": True,
    }, "steps": [
        {"id": "classify_trigger", "description": "确认直接触发日志", "checks": [
            check(trigger, "已找到直接触发证据", "当前日志不足以确认触发链", "diagnose_upstream", "insufficient_data")
        ]},
        {"id": "diagnose_upstream", "description": "检索上游字段与关联日志", "checks": [
            check(upstream, "存在可供人工复核的上游证据", "只有结果码，不能确认现场根因", "verify", "insufficient_data")
        ]},
        {"id": "insufficient_data", "description": "证据不足时停止归因", "checks": [
            check(f"{code}|{name}", "保留错误证据，根因待确认", "insufficient_data", "verify", "verify")
        ]},
        {"id": "verify", "description": "只读观察同场景复测", "checks": [{
            "type": "verify_fix", "grep_pattern": trigger, "watch_duration_sec": 60,
            "on_match": {"status": "still_present"},
            "on_no_match": {"status": "not_observed"},
        }]},
    ]}}
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return f"## 6 Agent 自动排查 Playbook\n\n```yaml\n{body}```"


def repair(path: Path) -> bool:
    content = path.read_text(encoding="utf-8-sig")
    if valid_playbook(content):
        return False
    code, name, module = metadata(path)
    pats = patterns(content, code, name)
    content = BLOCK_RE.sub("", content).rstrip()
    additions: list[str] = []
    if not re.search(r"(?m)^##\s+3\s+", content):
        additions.append(diagnosis_section(code, module, pats[0]))
    if not re.search(r"(?m)^##\s+5\s+修复验证", content):
        additions.append(evidence_section(code, name, module))
    additions.append(playbook_section(code, name, module, pats))
    path.write_text(content + "\n\n" + "\n\n".join(additions) + "\n", encoding="utf-8")
    return True


def main() -> int:
    repaired = [path.name for path in sorted(AGENT_DIR.glob("*.md")) if repair(path)]
    print(f"repaired_count={len(repaired)}")
    print("\n".join(repaired))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
