"""LangGraph StateGraph - 诊断 Agent 编排引擎"""

import os
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import DiagnosisState
from agent.logger import log


# ────────────────────────────────────────────────────────────
# 条件路由
# ────────────────────────────────────────────────────────────

def route_by_error_code(state: DiagnosisState) -> Literal["error_code_worker", "multi_agent_fanout"]:
    """有错误码 → 融合路径；无错误码 → 多 Agent 路径"""
    codes = state.get("error_codes", [])
    print(f"[graph] route_by_error_code: codes={codes}")
    if codes:
        return "error_code_worker"
    return "multi_agent_fanout"


def check_conflict(state: DiagnosisState) -> Literal["arbitrate", "render_report"]:
    """两个 Agent 结论是否冲突"""
    doc = state.get("doc_agent_result", {})
    field = state.get("field_agent_result", {})
    if doc.get("root_cause") != field.get("root_cause"):
        return "arbitrate"
    return "render_report"


# ────────────────────────────────────────────────────────────
# 节点（带 print 的占位实现，方便调试）
# ────────────────────────────────────────────────────────────

async def identify_source(state: DiagnosisState) -> DiagnosisState:
    """四路来源识别。先确定性路由，失败则 LLM 追问"""
    from agent.logger import log
    from models.router import route, AllModelsExhausted

    params = state.get("extra_params", {})
    user_input = state.get("user_input", "")

    # ── 确定性路由 ──
    if params.get("task_url"):
        state["source_type"] = "tb_task"
        log("identify_source", "确定性路由", source_type="tb_task",
            task_url=params["task_url"][:40])
        return state

    if params.get("robot_ip", "").startswith("172."):
        state["source_type"] = "internal_robot"
        log("identify_source", "确定性路由", source_type="internal_robot",
            ip=params["robot_ip"])
        return state

    if params.get("frp_port"):
        state["source_type"] = "remote_site"
        log("identify_source", "确定性路由", source_type="remote_site",
            port=params["frp_port"])
        return state

    if params.get("log_path"):
        state["source_type"] = "local_logs"
        log("identify_source", "确定性路由", source_type="local_logs",
            path=params["log_path"][:50])
        return state

    # ── LLM 识别 ──
    log("identify_source", "LLM识别", input=user_input[:80])

    try:
        result = await route("identify_source", [{
            "role": "user",
            "content": (
                f"用户输入: {user_input}\n"
                "判断问题来源，只回答以下之一: "
                "internal_robot / tb_task / remote_site / local_logs / insufficient_data\n"
            )
        }])
        answer = result["content"].strip().lower()
        log("identify_source", "LLM结果", answer=answer, model=result["model"])

        # 映射 LLM 回答到 source_type
        source_map = {
            "internal_robot": "internal_robot",
            "tb_task": "tb_task",
            "remote_site": "remote_site",
            "local_logs": "local_logs",
        }
        for key, val in source_map.items():
            if key in answer:
                state["source_type"] = val
                return state

        state["source_type"] = "insufficient_data"
    except AllModelsExhausted:
        state["source_type"] = "insufficient_data"
        log("identify_source", "模型不可用", error="all_models_exhausted")

    return state



async def collect_data(state: DiagnosisState) -> DiagnosisState:
    log("collect_data", "采集开始", source_type=state.get("source_type", "?"))
    state["materials"] = {"collected": True, "source": state.get("source_type")}
    log("collect_data", "采集完成（mock）", source=state.get("source_type", "?"))
    return state


async def classify_and_scan(state: DiagnosisState) -> DiagnosisState:
    """使用 engine.analysis.routing.classify_problem_type 做问题分类"""
    from engine.analysis.routing import classify_problem_type, route_spec_for
    from engine.analysis.material_scan import extract_error_codes

    symptom = state.get("symptom", state.get("user_input", ""))
    ptype = classify_problem_type(symptom, state.get("time_window", ""), state.get("source_type", "auto"))
    state["problem_type"] = ptype

    # 同时提取用户输入里可能提到的错误码
    codes = extract_error_codes(state.get("user_input", ""))
    if codes:
        existing = state.get("error_codes", [])
        state["error_codes"] = list(set(existing + codes))

    log("classify_and_scan", "分类完成", problem_type=ptype, error_codes=state.get("error_codes", []))
    return state


async def deep_insight_and_route(state: DiagnosisState) -> DiagnosisState:
    """使用 engine 的 build_deep_insights + build_specialty_findings"""
    # 这些函数需要 case_dir 和文件——如果 materials 里没有路径，跳过
    materials = state.get("materials", {})
    case_dir = materials.get("case_dir", "")

    if case_dir:
        from pathlib import Path
        from engine.analysis.deep_rules import build_deep_insights
        from engine.analysis.insights import build_specialty_findings

        insights = build_deep_insights(Path(case_dir), {}, state.get("findings", []))
        specialty = build_specialty_findings(Path(case_dir), {}, state.get("findings", []))

        state["deep_insights"] = insights
        state["specialty_hits"] = [s.get("title", "") for s in specialty]
    else:
        state["deep_insights"] = []
        state["specialty_hits"] = []

    log("deep_insight_and_route", "归因完成", error_codes=state.get("error_codes", []),
          insights_count=len(state.get("deep_insights", [])),
          specialty=state.get("specialty_hits", []))
    return state


async def error_code_worker(state: DiagnosisState) -> DiagnosisState:
    """使用 knowledge.playbook_loader 执行 Playbook"""
    from knowledge.playbook_loader import execute_playbook

    codes = state.get("error_codes", [])
    if not codes:
        state["playbook_matched"] = False
        return state

    # 取第一个错误码（错误码关联图排序后，上游优先）
    code = codes[0]

    # 收集可用日志文本
    log_text = ""
    findings = state.get("findings", [])
    if findings:
        log_text = "\n".join(f.get("text", "") for f in findings[:20])
    elif state.get("user_input"):
        log_text = state.get("user_input", "")

    result = execute_playbook(code, log_text)

    state["playbook_matched"] = result["matched"]
    state["playbook_error_code"] = code
    state["playbook_trigger_chain"] = result.get("trigger_chain", "")
    state["playbook_root_cause"] = result.get("root_cause", "")
    state["playbook_confidence"] = result.get("confidence", "low")

    log("error_code_worker", "Playbook执行", code=code, matched=result["matched"],
        trigger_chain=result.get("trigger_chain", "?"), confidence=result.get("confidence", "?"))
    return state


async def topk_doc_worker(state: DiagnosisState) -> DiagnosisState:
    """使用导航 TopK 问题文档做文档匹配"""
    from agent.logger import log
    from knowledge.topk_loader import match_problem_doc

    code = state.get("playbook_error_code", "")
    problem_type = state.get("problem_type", "general")

    result = match_problem_doc(code, problem_type, state.get("symptom", ""))

    state["topk_doc_result"] = result
    log("topk_doc_worker", "文档匹配完成",
        code=code, problem_type=problem_type,
        matched=result.get("matched", False),
        relevance=result.get("relevance", "none"))

    return state


async def fuse_simple(state: DiagnosisState) -> DiagnosisState:
    """融合 Playbook 结论和 TopK 文档结论 —— 一次 LLM 调用"""
    from agent.logger import log
    from models.router import route, AllModelsExhausted

    playbook_cause = state.get("playbook_root_cause", "")
    playbook_chain = state.get("playbook_trigger_chain", "")
    topk_section = state.get("topk_doc_result", {}).get("section", "")
    topk_directions = state.get("topk_doc_result", {}).get("directions", [])
    symptom = state.get("symptom", state.get("user_input", ""))

    if not playbook_cause and not topk_section:
        state["fusion_result"] = {"status": "insufficient", "root_cause": "", "confidence": "low"}
        state["fused_root_cause"] = ""
        state["fused_confidence"] = "low"
        log("fuse_simple", "无可用结论，跳过融合")
        return state

    prompt = f"""你是诊断融合器。两个分析路径给出了各自的结论，判断它们是否一致。

现象: {symptom}

路径A (代码分析):
  触发链: {playbook_chain}
  根因: {playbook_cause}

路径B (文档匹配):
  问题分类: {topk_section}
  排查方向: {', '.join(topk_directions) if topk_directions else '无'}

请输出 JSON:
{{"relation": "一致|上下游|矛盾|互补", "fused_cause": "融合后的根因描述", "confidence": "high|medium|low"}}"""

    try:
        result = await route("fuse_simple", [{"role": "user", "content": prompt}])
        import json, re
        json_match = re.search(r'\{.*\}', result["content"], re.DOTALL)
        if json_match:
            fusion = json.loads(json_match.group(0))
        else:
            fusion = {"relation": "未知", "fused_cause": result["content"][:200], "confidence": "low"}

        state["fusion_result"] = {
            "status": fusion.get("relation", "未知"),
            "root_cause": fusion.get("fused_cause", ""),
            "confidence": fusion.get("confidence", "low"),
        }
        state["fused_root_cause"] = fusion.get("fused_cause", "")
        state["fused_confidence"] = fusion.get("confidence", "low")

        log("fuse_simple", "融合完成",
            relation=fusion.get("relation", "?"),
            confidence=fusion.get("confidence", "?"),
            model=result["model"])

    except AllModelsExhausted:
        state["fusion_result"] = {"status": "error", "root_cause": playbook_cause or topk_section, "confidence": "low"}
        state["fused_root_cause"] = playbook_cause or topk_section
        state["fused_confidence"] = "low"
        log("fuse_simple", "模型不可用，使用原始结论")

    return state


async def doc_agent(state: DiagnosisState) -> DiagnosisState:
    log("doc_agent", "开始分析（mock）")
    return {"doc_agent_result": {"root_cause": "mock_doc_cause", "confidence": "medium"}}


async def field_agent(state: DiagnosisState) -> DiagnosisState:
    log("field_agent", "开始分析（mock）")
    return {"field_agent_result": {"root_cause": "mock_field_cause", "confidence": "medium"}}


async def arbitrate(state: DiagnosisState) -> DiagnosisState:
    log("arbitrate", "开始仲裁（mock）")
    return {"arbitration_result": {
        "conflict_type": "real",
        "primary_conclusion": state.get("field_agent_result", {}).get("root_cause", ""),
        "reasoning": "mock arbitration",
    }, "fusion_result": {
        "conflict_type": "real",
        "primary_conclusion": state.get("field_agent_result", {}).get("root_cause", ""),
    }}


async def render_report(state: DiagnosisState) -> DiagnosisState:
    log("render_report", "报告生成完成（mock）")
    return {"conclusion_status": "likely", "report_path": "data/cases/mock/report.md"}


# ────────────────────────────────────────────────────────────
# 图构建
# ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(DiagnosisState)

    # 主路径
    graph.add_node("identify_source", identify_source)
    graph.add_node("collect_data", collect_data)
    graph.add_node("classify_and_scan", classify_and_scan)
    graph.add_node("deep_insight_and_route", deep_insight_and_route)

    # 入口
    graph.add_edge(START, "identify_source")

    graph.add_edge("identify_source", "collect_data")
    graph.add_edge("collect_data", "classify_and_scan")
    graph.add_edge("classify_and_scan", "deep_insight_and_route")

    # ★ 条件分叉
    graph.add_conditional_edges(
        "deep_insight_and_route",
        route_by_error_code,
        {"error_code_worker": "error_code_worker", "multi_agent_fanout": "multi_agent_fanout"}
    )

    # 融合路径
    graph.add_node("error_code_worker", error_code_worker)
    graph.add_node("topk_doc_worker", topk_doc_worker)
    graph.add_node("fuse_simple", fuse_simple)
    graph.add_edge("error_code_worker", "fuse_simple")
    graph.add_edge("topk_doc_worker", "fuse_simple")
    graph.add_edge("fuse_simple", "render_report")

    # 多 Agent 路径：扇出节点，同时启动 doc_agent 和 field_agent
    graph.add_node("multi_agent_fanout", lambda s: s)
    graph.add_node("doc_agent", doc_agent)
    graph.add_node("field_agent", field_agent)
    graph.add_node("arbitrate", arbitrate)

    graph.add_edge("multi_agent_fanout", "doc_agent")
    graph.add_edge("multi_agent_fanout", "field_agent")
    graph.add_conditional_edges(
        "field_agent", check_conflict,
        {"arbitrate": "arbitrate", "render_report": "render_report"}
    )
    graph.add_edge("doc_agent", "arbitrate")
    graph.add_edge("arbitrate", "render_report")

    # 终点
    graph.add_node("render_report", render_report)
    graph.add_edge("render_report", END)

    return graph


# ────────────────────────────────────────────────────────────
# 编译
# ────────────────────────────────────────────────────────────

def _build_checkpointer():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from langgraph.checkpoint.postgres import PostgresSaver
        return PostgresSaver.from_conn_string(db_url)
    return MemorySaver()


graph = build_graph()
checkpointer = _build_checkpointer()
app = graph.compile(checkpointer=checkpointer)
