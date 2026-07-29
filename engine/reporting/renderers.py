"""Render diagnosis, handoff, and knowledge Markdown from structured data."""

from __future__ import annotations

from typing import Any

from engine.utils import normalize_multi
from engine.reporting.formatters import (
    bullet_lines,
    format_analysis_trace,
    format_deep_insights,
    format_dingtalk_evidence,
    format_gitlab_evidence,
    format_similar_cases,
    format_specialty_findings,
    format_window_evidence,
    has_robot_collection,
    indent_block,
    numbered_findings,
    summarize_deep_root,
)


def render_diagnosis_report(context: dict[str, Any], summary: dict[str, Any]) -> str:
    source = context.get("source_type", "")
    robot = context.get("source", {}).get("robot_ip") or context.get("source", {}).get("site_robot_ip") or ""
    artifacts = normalize_multi(context.get("artifacts"))
    knowledge = normalize_multi(context.get("knowledge_sources"))
    code = normalize_multi(context.get("code_sources"))
    findings = summary.get("findings", [])
    primary = summary.get("primary_findings", []) or []
    supporting = summary.get("supporting_findings", []) or []
    deep = summary.get("deep_insights", [])
    specialty = summary.get("specialty_findings", []) or []
    routes = normalize_multi(summary.get("analysis_route"))
    status = summary.get("conclusion_status", "insufficient_data")
    codes = normalize_multi(summary.get("error_codes"))
    trace = summary.get("analysis_trace", {}) or {}
    similar = summary.get("similar_cases", []) or []
    external = summary.get("external_evidence", {}) or {}
    docs = external.get("dingtalk_docs", []) or []
    projects = external.get("gitlab_projects", []) or []
    warnings = normalize_multi(external.get("warnings"))

    if deep:
        root_cause = summarize_deep_root(deep, findings)
        action = str(deep[0].get("action", "")) or "优先按深层归因中的最高优先级链路继续排查。"
    elif findings:
        root_cause = summarize_deep_root([], findings)
        action = "优先按证据链中的日志文件和时间点复核；如涉及错误码，查钉钉 SOP；如涉及任务/传感器/机型，按分析路由转专项排查。"
    elif summary.get("scanned_files", 0):
        root_cause = "已读取本地材料，但未命中明确异常关键词或现象错误码；当前不能仅凭材料定根因。"
        action = "补充准确发生时间、关键服务日志上下文，或由现场/机器人只读采集当前状态后再分析。"
    else:
        root_cause = "当前 case 没有可分析的本地日志/任务材料；只能根据现象生成排查路线。"
        action = "先采集机器人状态、版本、错误码详情和问题发生时间附近日志，再重新运行 analyze。"

    external_note = "\n- 外部证据采集告警：\n" + indent_block(bullet_lines(warnings), 2) if warnings else ""
    robot_evidence = f"已通过 SSH 只读采集机器人材料，扫描 {summary.get('scanned_files', 0)} 个本地采集文件。" if has_robot_collection(context) else "当前本地分析未直接连接机器人；如来源为 internal_robot/remote_site，需要补充只读采集结果。"

    return f"""# 问题诊断报告

## 1. 基本信息

- 来源：{source}
- Case ID：{context.get('case_id', '')}
- 机器人：{robot}
- 车型/版本：
- 问题时间：{context.get('time_window', '')}
- 用户现象：{context.get('symptom', '')}
- 输入材料：
{bullet_lines(artifacts)}
- AI 读取范围：
  - 钉钉/历史问题：
{indent_block(bullet_lines(knowledge), 4)}
  - 代码/GitLab：
{indent_block(bullet_lines(code), 4)}

## 2. 结论

- 状态：{status}
- 根因：{root_cause}
- 影响范围：待结合机器人版本、现场复现范围和具体模块确认。
- 建议动作：{action}

## 3. 证据链

### 3.1 深层归因

{format_deep_insights(deep)}

### 3.2 原始证据

1. 主链路日志证据：
{indent_block(numbered_findings(primary or findings[:5]), 3)}
2. 补充日志证据：
{indent_block(numbered_findings(supporting), 3)}
3. 时间窗口证据文件：
{indent_block(format_window_evidence(trace.get('window_evidence', []) or []), 3)}
4. 机器人状态或版本证据：{robot_evidence}
5. 专项 skill 自动命中：
{indent_block(format_specialty_findings(specialty), 3)}
6. 代码 / MR / Issue 证据：
{indent_block(format_gitlab_evidence(projects), 3)}
7. 钉钉知识库文档或历史问题证据：
{indent_block(format_dingtalk_evidence(docs, codes), 3)}
8. 本地历史相似案例：
{indent_block(format_similar_cases(similar), 3)}

## 4. 分析过程

- 使用过的 skills：{', '.join(routes) if routes else 'robot-diagnosis'}
- 关键分流判断：根据来源类型、文件名、日志关键词、用户现象和错误码提取结果自动生成路由。
- 结构化分析 trace：
{indent_block(format_analysis_trace(trace), 2)}
- 排除项：本轮未执行机器人写操作、未重启服务；GitLab/钉钉只做只读检索。
- 仍不确定的信息：准确发生时间、现场复现步骤、机器人版本/车型、错误码 SOP、关键日志前后文。
{external_note}

## 5. 后续动作

- 技术支持工程师：补充发生时间和现场动作；复核证据链中列出的日志片段。
- 研发：按分析路由查看对应模块日志和代码；必要时补充 GitLab 历史修复证据。
- 现场：只做只读验证；涉及重启、改配置、发版前需单独确认。

## 6. 是否需要沉淀到钉钉知识库

- 需要/不需要：{'需要' if findings or codes else '待定'}
- 建议标题：{context.get('symptom', '问题诊断')} 排查记录
- 建议钉钉知识库归档位置：技术支持 / 机器人诊断 / 按错误码或模块归档
- 沉淀原因：当前 case 已形成可复用的材料入口、证据链和后续排查路线。
"""


def render_human_handoff(context: dict[str, Any], summary: dict[str, Any]) -> str:
    findings = summary.get("findings", [])
    codes = normalize_multi(summary.get("error_codes"))
    missing_logs = "无可读本地日志材料" if not summary.get("scanned_files") else "需要问题时间点前后更完整日志上下文"
    routes = ", ".join(normalize_multi(summary.get("analysis_route")))
    return f"""# 人工介入清单

## 1. 需要补充的信息

- 问题准确发生时间：{context.get('time_window', '') or '待补充'}
- 现场操作步骤：待补充
- 缺失日志或附件：{missing_logs}
- 需要补充的机器人信息：车型、版本、当前错误码详情、关键服务状态
- 需要补充的 TB / 钉钉 / GitLab 链接：错误码 SOP、历史问题、相关 MR/Issue

## 2. 建议现场验证

1. 验证动作：根据 report.md 证据链复核异常时间点；如无证据，先采集当前机器人状态和错误码详情。
2. 预期结果：能确认错误码 {', '.join(codes) if codes else '或异常日志'} 与现场现象、发生时间一致。
3. 如果不符合预期，下一步：补充日志包或由研发按 `{routes}` 路由继续排查。

## 3. 风险提示

- 是否涉及生产环境：待现场确认
- 是否需要停机窗口：本轮分析不需要；后续如重启/改配置需要单独确认
- 是否需要研发/硬件/实施共同参与：{'需要' if findings else '视补充材料而定'}
- 是否存在写操作风险：本轮没有写机器人操作
"""


def render_knowledge_draft(context: dict[str, Any], summary: dict[str, Any]) -> str:
    primary = summary.get("primary_findings", []) or summary.get("findings", [])[:8]
    trace = summary.get("analysis_trace", {}) or {}
    root = summarize_deep_root(summary.get("deep_insights", []) or [], summary.get("findings", [])) or "当前仅形成排查证据，根因需人工复核。"
    return f"""# {context.get('symptom', '问题诊断')} 排查知识草稿

## 1. 适用场景

- 问题类型：{trace.get('problem_title', trace.get('problem_type', '通用问题'))}
- 适用入口：Teambition 任务、离线日志包、机器人现场日志。
- 典型现象：{context.get('symptom', '')}

## 2. 典型现象

- 问题时间：{context.get('time_window', '')}
- 关键模块：{', '.join(trace.get('route_primary_logs', []) or []) or '待确认'}
- 补充模块：{', '.join(trace.get('route_support_logs', []) or []) or '待确认'}

## 3. 快速判断

1. 先确认问题日期和问题时间。
2. 按问题类型选择主日志，本案例类型优先看 `{(trace.get('route_primary_logs') or ['待确认'])[0]}`。
3. 对大日志只截取问题时间前后 5 分钟。
4. 主链路证据不足时，再扩大到前后 10 分钟或查看补充模块。

## 4. 证据模板

{numbered_findings(primary, limit=8)}

## 5. 当前结论

{root}

## 6. 排查步骤

1. 下载 Teambition 关键附件，确认日志包已进入当前 case 的 `raw/teambition/`。
2. 递归解压压缩包，直到得到真实 `*.log` 或 `*.log.*` 业务日志。
3. 只解压或优先分析问题当天日志。
4. 根据问题类型路由到主日志和补充日志。
5. 生成 `extracted/log-windows/` 时间窗口证据。
6. 结合报告中的主链路证据、补充证据和历史相似案例做人工复核。

## 7. 需要升级 / 转交的情况

- 时间窗口内没有主链路证据。
- 主链路证据与用户现象不一致。
- 涉及定位跳动、物理打滑、安全限速、任务链路多个模块，需要研发联合判断。
- 需要修改配置、重启服务或发版验证。

## 8. 参考案例

- Case ID：{context.get('case_id', '')}
- 报告：`report.md`
- 时间窗口证据：{format_window_evidence(trace.get('window_evidence', []) or [])}
"""
