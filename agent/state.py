"""DiagnosisState - LangGraph 共享状态定义"""

from typing import TypedDict, Literal, Annotated
import operator


class DiagnosisState(TypedDict, total=False):
    """一次诊断的完整状态，贯穿 StateGraph 所有节点"""

    # ── 输入 ──
    user_input: str
    source_type: Literal["internal_robot", "tb_task", "remote_site", "local_logs"]
    extra_params: dict  # IP / TB链接 / 端口 / 日志路径

    # ── 采集产物 ──
    materials: dict  # SSH 采集结果 / TB 下载路径 / 本地日志路径
    collected_at: str

    # ── 分析中间产物 ──
    findings: Annotated[list[dict], operator.add]  # 日志扫描发现
    error_codes: list[str]  # 提取出的错误码
    problem_type: str  # navigation_rotate / safety / task_chain / device_sensor / general
    diagnosis_queue: list[dict]  # 错误码关联图排序后的排查队列
    deep_insights: list[dict]  # 6 项深层归因命中结果
    specialty_hits: list[str]  # 命中的专项 skill 名

    # ── Playbook 执行产物 ──
    playbook_matched: bool
    playbook_error_code: str
    playbook_trigger_chain: str
    playbook_root_cause: str
    playbook_confidence: Literal["high", "medium", "low"]

    # ── 证据收集产物 ──
    dingtalk_evidence: list[dict]
    gitlab_evidence: list[dict]
    history_cases: list[dict]

    # ── 多 Agent 产物 ──
    doc_agent_result: dict  # 代码文档 Agent 结论
    field_agent_result: dict  # 现场 Agent 结论
    has_conflict: bool  # 两个 Agent 结论是否冲突
    arbitration_result: dict  # 仲裁 Agent 结论

    # ── 融合产物 ──
    fusion_result: dict  # 或仲裁结果
    fused_root_cause: str
    fused_confidence: Literal["high", "medium", "low"]

    # ── 结论 ──
    conclusion_status: Literal["confirmed", "likely", "need_human", "insufficient_data"]
    report_path: str

    # ── 控制流 ──
    errors: Annotated[list[str], operator.add]
    retry_counts: dict
    fallback_triggered: Annotated[list[str], operator.add]
    knowledge_draft_path: str
