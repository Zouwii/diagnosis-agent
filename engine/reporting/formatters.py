"""Shared Markdown formatters for diagnosis reports."""

from __future__ import annotations

from typing import Any

from engine.analysis.material_scan import short_line
from engine.utils import normalize_multi


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def bullet_lines(items: list[str], empty: str = "-") -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def numbered_findings(findings: list[dict[str, Any]], limit: int = 20) -> str:
    if not findings:
        return "未在本地材料中命中 ERROR/WARN/异常关键词或用户现象中的错误码。"
    lines = [f"{index}. `{item['file']}:{item['line']}` [{item['level']}] {item['text']}" for index, item in enumerate(findings[:limit], start=1)]
    if len(findings) > limit:
        lines.append(f"{limit + 1}. 其余 {len(findings) - limit} 条命中已省略，详见 context.json 的 analysis_summary。")
    return "\n".join(lines)


def format_window_evidence(records: list[dict[str, Any]]) -> str:
    if not records:
        return "未生成时间窗口证据文件；通常是缺少明确问题时间，或没有可路由的关键日志。"
    lines: list[str] = []
    for index, record in enumerate(records[:12], start=1):
        note = f"，{record.get('error')}" if record.get("error") else ""
        lines.append(f"{index}. `{record.get('window_file') or '-'}`：来源 `{record.get('source_file', '-')}`，窗口 {record.get('start', '-') or '-'} ~ {record.get('end', '-') or '-'}，匹配 {record.get('matched_lines', 0)} 行{note}")
    if len(records) > 12:
        lines.append(f"13. 其余 {len(records) - 12} 个窗口记录见 context.json。")
    return "\n".join(lines)


def format_analysis_trace(trace: dict[str, Any]) -> str:
    if not trace:
        return "- 本轮未生成结构化分析 trace。"
    coverage = trace.get("coverage", []) or []
    coverage_lines = [f"   - `{item.get('file', '-')}`：{item.get('mode', '-')}，命中 {item.get('findings', 0)} 条" + (f"，{item.get('note')}" if item.get("note") else "") for item in coverage[:10]]
    if len(coverage) > 10:
        coverage_lines.append(f"   - 其余 {len(coverage) - 10} 条覆盖记录见 context.json。")
    return (
        f"- 问题类型：{trace.get('problem_title', trace.get('problem_type', '通用问题'))}\n"
        f"- 问题日期：{trace.get('date_stamp') or '未识别'}\n"
        f"- 问题时间：{trace.get('target_time') or '未识别'}\n"
        f"- 主日志优先级：{', '.join(trace.get('route_primary_logs', []) or []) or '-'}\n"
        f"- 补充日志优先级：{', '.join(trace.get('route_support_logs', []) or []) or '-'}\n"
        f"- 时间窗口证据：\n{indent_block(format_window_evidence(trace.get('window_evidence', []) or []), 2)}\n"
        f"- 分析覆盖范围：\n" + ("\n".join(coverage_lines) if coverage_lines else "   - -")
    )


def format_similar_cases(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return "当前没有从本地 diagnosis-cases 中召回相似历史案例。"
    return "\n".join(f"{index}. `{item.get('case_id', '-')}` score={item.get('score', 0)} status={item.get('conclusion_status', '-')}\n   - 现象：{short_line(str(item.get('symptom', '')), 160)}\n   - 报告：`{item.get('report', '-')}`" for index, item in enumerate(cases, start=1))


def has_robot_collection(context: dict[str, Any]) -> bool:
    return any("/raw/robot/" in item or "\\raw\\robot\\" in item or "/raw/remote-hand/" in item or "\\raw\\remote-hand\\" in item for item in normalize_multi(context.get("artifacts")))


def summarize_primary_evidence(findings: list[dict[str, Any]]) -> str:
    return "；".join(f"`{item['file']}:{item['line']}` {item['text']}" for item in findings[:3])


def format_deep_insights(insights: list[dict[str, Any]]) -> str:
    if not insights:
        return "本轮未形成模块级归因，只能保留通用日志证据。"
    blocks = []
    for index, insight in enumerate(insights, start=1):
        evidence = "\n".join(f"   - {item}" for item in (insight.get("evidence", []) or [])[:8]) or "   - -"
        blocks.append(f"{index}. [{insight.get('severity', 'P3')}] {insight.get('title', '归因')}\n   - 判断：{insight.get('conclusion', '')}\n   - 证据：\n{evidence}\n   - 下一步：{insight.get('action', '')}")
    return "\n".join(blocks)


def format_gitlab_evidence(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return "当前未自动读取到 GitLab 代码 / MR / Issue 证据；如需要定位实现或历史修复，补充 `code_sources` 或检查 GitLab 凭据。"
    blocks = []
    for index, project in enumerate(projects, start=1):
        matches = project.get("matches", []) or []
        lines = []
        for match in matches[:5]:
            location = str(match.get("path", "") or "-")
            if match.get("startline") not in ("", None):
                location = f"{location}:{match['startline']}"
            lines.append(f"   - `{location}` 命中 `{match.get('keyword', '') or ''}`：{match.get('data', '') or '-'}")
        if not lines:
            lines.append("   - 已确认项目可访问，但未命中当前关键词。")
        blocks.append(f"{index}. {project.get('path_with_namespace', project.get('source', 'GitLab 项目'))}\n   - 项目：{project.get('web_url', '-')}\n   - 默认分支：{project.get('default_branch', '-')}\n" + "\n".join(lines))
    return "\n".join(blocks)


def format_dingtalk_evidence(docs: list[dict[str, Any]], codes: list[str]) -> str:
    prefix = f"发现错误码：{', '.join(codes)}。" if codes else "未从现象或材料中提取到明确错误码。"
    if not docs:
        return f"{prefix} 当前未自动读取到钉钉知识库正文证据；如需要 SOP 证据，补充 `knowledge_sources` 或检查钉钉授权。"
    blocks = [prefix]
    for index, doc in enumerate(docs, start=1):
        snippets = "\n".join(f"   - {item}" for item in (doc.get("snippets", []) or [])[:5]) or "   - 已找到文档，但未提取到相关段落。"
        blocks.append(f"{index}. {doc.get('title', '钉钉文档')}\n   - 链接：{doc.get('url', '-')}\n   - 搜索词：{doc.get('keyword', '-')}\n   - 相关摘录：\n{snippets}")
    return "\n".join(blocks)


def format_specialty_findings(items: list[dict[str, Any]]) -> str:
    if not items:
        return "本轮未形成专项 skill 的可落地命中证据。"
    blocks = []
    for index, item in enumerate(items, start=1):
        evidence = "\n".join(f"   - {line}" for line in (item.get("evidence", []) or [])[:8]) or "   - -"
        blocks.append(f"{index}. {item.get('title', '专项命中')}：`{item.get('skill', '-')}`\n   - 证据：\n{evidence}\n   - 下一步：{item.get('action', '')}")
    return "\n".join(blocks)


def summarize_deep_root(insights: list[dict[str, Any]], findings: list[dict[str, Any]]) -> str:
    if insights:
        return insights[0].get("conclusion", "") if len(insights) == 1 else f"{insights[0].get('conclusion', '')} 同时，{insights[1].get('conclusion', '')}"
    if findings:
        return f"本地材料中存在异常/告警/错误码相关证据。主要证据：{summarize_primary_evidence(findings)}。仍需结合错误码 SOP 或专项日志确认最终根因。"
    return ""
