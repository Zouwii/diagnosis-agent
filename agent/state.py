"""DiagnosisState - LangGraph 共享状态定义"""

from typing import TypedDict, Literal, Annotated
import operator


class DiagnosisState(TypedDict, total=False):
    """一次诊断的完整状态，贯穿 StateGraph 所有节点"""

    # ── 输入 ──
    case_id: str
    case_dir: str
    owner_safe: str
    input_root: str
    input_roots: list[str]
    user_input: str
    symptom: str
    time_window: str
    source_type: Literal["auto", "internal_robot", "tb_task", "remote_site", "local_logs", "insufficient_data"]
    selected_skill: str
    analysis_skill: str
    extra_params: dict  # IP / TB链接 / 端口 / 日志路径

    # ── 采集产物 ──
    materials: dict  # SSH 采集结果 / TB 下载路径 / 本地日志路径
    collected_at: str

    # ── 分析中间产物 ──
    findings: Annotated[list[dict], operator.add]  # 日志扫描发现
    error_codes: list[str]  # 提取出的错误码
    problem_type: str  # navigation_rotate / safety / task_chain / device_sensor / general
    deep_insights: list[dict]  # 6 项深层归因命中结果
    specialty_hits: list[str]  # 命中的专项 skill 名
    analysis_route: list[str]
    analysis_summary: dict
    context: dict

    # ── 后续两个 Agent 的稳定边界 ──
    analysis_agent_result: dict
    external_evidence: dict
    fusion_result: dict

    # ── 结论 ──
    conclusion_status: Literal["confirmed", "likely", "need_human", "insufficient_data"]
    report_path: str

    # ── 控制流 ──
    errors: Annotated[list[str], operator.add]
    fallback_triggered: Annotated[list[str], operator.add]
    knowledge_draft_path: str
