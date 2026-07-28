"""LangGraph StateGraph - 诊断 Agent 编排引擎"""

import os
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import DiagnosisState


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
    print(f"[node] identify_source: input='{state.get('user_input', '')[:50]}'")
    params = state.get("extra_params", {})
    if params.get("task_url"):
        state["source_type"] = "tb_task"
    elif params.get("robot_ip", "").startswith("172."):
        state["source_type"] = "internal_robot"
    elif params.get("frp_port"):
        state["source_type"] = "remote_site"
    elif params.get("log_path"):
        state["source_type"] = "local_logs"
    else:
        state["source_type"] = "insufficient_data"
    print(f"[node] identify_source: source_type={state['source_type']}")
    return state


async def collect_data(state: DiagnosisState) -> DiagnosisState:
    print(f"[node] collect_data: source_type={state.get('source_type')}")
    state["materials"] = {"collected": True, "source": state.get("source_type")}
    return state


async def classify_and_scan(state: DiagnosisState) -> DiagnosisState:
    import re
    symptom = state.get("symptom", state.get("user_input", ""))
    for ptype, pattern in [
        ("navigation_rotate", r"revolve|rotate|旋转"),
        ("safety", r"安全|急停|避障"),
        ("task_chain", r"任务|mission|task"),
    ]:
        if re.search(pattern, symptom, re.IGNORECASE):
            state["problem_type"] = ptype
            break
    else:
        state["problem_type"] = "general"
    print(f"[node] classify_and_scan: problem_type={state['problem_type']}")
    return state


async def deep_insight_and_route(state: DiagnosisState) -> DiagnosisState:
    # 模拟提取错误码（从 user_input 中找 6 开头的 6 位数字）
    import re
    codes = re.findall(r"(?<!\d)(6\d{5})(?!\d)", state.get("user_input", ""))
    state["error_codes"] = codes
    state["deep_insights"] = [{"rule": "mock", "hit": len(codes) > 0}]
    print(f"[node] deep_insight_and_route: error_codes={codes}")
    return state


async def error_code_worker(state: DiagnosisState) -> DiagnosisState:
    codes = state.get("error_codes", [])
    state["playbook_matched"] = len(codes) > 0
    state["playbook_error_code"] = codes[0] if codes else ""
    state["playbook_root_cause"] = f"mock root cause for {codes[0]}" if codes else ""
    state["playbook_confidence"] = "medium"
    print(f"[node] error_code_worker: matched={state['playbook_matched']}")
    return state


async def history_worker_fusion(state: DiagnosisState) -> DiagnosisState:
    state["history_cases"] = [{"case_id": "mock-001", "score": 5, "conclusion": "mock"}]
    print(f"[node] history_worker_fusion: found {len(state['history_cases'])} cases")
    return state


async def fuse_simple(state: DiagnosisState) -> DiagnosisState:
    state["fusion_result"] = {
        "status": "consistent",
        "root_cause": state.get("playbook_root_cause", ""),
        "confidence": "medium",
    }
    state["fused_root_cause"] = state.get("playbook_root_cause", "")
    state["fused_confidence"] = "medium"
    print(f"[node] fuse_simple: {state['fusion_result']['status']}")
    return state


async def doc_agent(state: DiagnosisState) -> DiagnosisState:
    print(f"[node] doc_agent: analyzing...")
    return {"doc_agent_result": {"root_cause": "mock_doc_cause", "confidence": "medium"}}


async def field_agent(state: DiagnosisState) -> DiagnosisState:
    print(f"[node] field_agent: analyzing...")
    return {"field_agent_result": {"root_cause": "mock_field_cause", "confidence": "medium"}}


async def arbitrate(state: DiagnosisState) -> DiagnosisState:
    print(f"[node] arbitrate: resolving conflict...")
    return {"arbitration_result": {
        "conflict_type": "real",
        "primary_conclusion": state.get("field_agent_result", {}).get("root_cause", ""),
        "reasoning": "mock arbitration",
    }, "fusion_result": {
        "conflict_type": "real",
        "primary_conclusion": state.get("field_agent_result", {}).get("root_cause", ""),
    }}


async def render_report(state: DiagnosisState) -> DiagnosisState:
    print(f"[node] render_report: finalizing...")
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
    graph.add_node("history_worker_fusion", history_worker_fusion)
    graph.add_node("fuse_simple", fuse_simple)
    graph.add_edge("error_code_worker", "fuse_simple")
    graph.add_edge("history_worker_fusion", "fuse_simple")
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
