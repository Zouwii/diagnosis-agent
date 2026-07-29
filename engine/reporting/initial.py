"""Initial Case artifacts written before deterministic or AI analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.reporting.formatters import indent_block


def render_initial_report(template: str, context: dict[str, Any]) -> str:
    source = context["source_type"]
    robot = context["source"].get("robot_ip") or context["source"].get("site_robot_ip") or ""
    materials = "\n".join(f"- {item}" for item in context.get("artifacts", [])) or "-"
    knowledge = "\n".join(f"- {item}" for item in context.get("knowledge_sources", [])) or "-"
    code = "\n".join(f"- {item}" for item in context.get("code_sources", [])) or "-"
    replacements = {
        "- 来源：": f"- 来源：{source}",
        "- Case ID：": f"- Case ID：{context['case_id']}",
        "- 机器人：": f"- 机器人：{robot}",
        "- 问题时间：": f"- 问题时间：{context.get('time_window', '')}",
        "- 用户现象：": f"- 用户现象：{context.get('symptom', '')}",
        "- 输入材料：": f"- 输入材料：\n{materials}",
        "- AI 读取范围：": f"- AI 读取范围：\n  - 钉钉/历史问题：\n{indent_block(knowledge, 4)}\n  - 代码/GitLab：\n{indent_block(code, 4)}",
        "- 状态：confirmed / likely / need_human / insufficient_data": "- 状态：insufficient_data",
    }
    result = template
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def build_next_prompt(context: dict[str, Any]) -> str:
    return f"""# diagnosis-orchestrator 诊断提示

请使用 `/diagnosis-orchestrator` 继续处理以下 case。

```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```

要求：

1. 先确认输入来源和缺失信息。
2. 按 case 上下文调用对应采集 skill。
3. 使用 `robot-diagnosis` 和专项 skills 完成分析。
4. 需要已有经验时调用 `dingtalk-docs`，最多读取 5 篇正文。
5. 需要代码证据时调用 `gitlab-operator`。
6. 用 `report.md`、`human-handoff.md`、`knowledge-draft.md` 的模板更新输出。
"""


def write_initial_files(case_dir: Path, context: dict[str, Any], template_dir: Path | None = None) -> None:
    template_dir = template_dir or Path(__file__).resolve().parents[2] / "templates"
    report_template = (template_dir / "diagnosis-report.md").read_text(encoding="utf-8")
    handoff_template = (template_dir / "human-handoff.md").read_text(encoding="utf-8")
    knowledge_template = (template_dir / "knowledge-draft.md").read_text(encoding="utf-8")
    (case_dir / "report.md").write_text(render_initial_report(report_template, context), encoding="utf-8")
    (case_dir / "human-handoff.md").write_text(handoff_template, encoding="utf-8")
    (case_dir / "knowledge-draft.md").write_text(knowledge_template, encoding="utf-8")
    (case_dir / "next-prompt.md").write_text(build_next_prompt(context), encoding="utf-8")
