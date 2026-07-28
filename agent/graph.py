"""LangGraph StateGraph - 诊断 Agent 编排引擎

流程图:
  identify_source → collect_data → classify_and_scan → deep_insight_and_route
    → [有错误码?]
       YES → error_code_worker ∥ history_worker → fuse_simple → render
       NO  → doc_agent ∥ field_agent → [冲突?]
               YES → arbitrate → render
               NO  → render
"""

import os
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from agent.state import DiagnosisState
# from agent.nodes import *  # 逐步实现

# ────────────────────────────────────────────────────────────
# Checkpointer
# ────────────────────────────────────────────────────────────

def build_checkpointer():
    """生产用 PostgresSaver，开发用 MemorySaver"""
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return PostgresSaver.from_conn_string(db_url)
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


# ────────────────────────────────────────────────────────────
# 条件路由函数
# ────────────────────────────────────────────────────────────

def route_by_error_code(state: DiagnosisState) -> Literal["fusion_path", "multi_agent_path"]:
    """有错误码 → 融合路径；无错误码 → 多 Agent 路径"""
    if state.get("error_codes"):
        return "fusion_path"
    return "multi_agent_path"


def check_conflict(state: DiagnosisState) -> Literal["arbitrate", "render"]:
    """两个 Agent 结论是否冲突"""
    doc = state.get("doc_agent_result", {})
    field = state.get("field_agent_result", {})
    if doc.get("root_cause") != field.get("root_cause"):
        return "arbitrate"
    return "render"


# ────────────────────────────────────────────────────────────
# 图构建
# ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(DiagnosisState)

    # ── 主路径节点 ──
    graph.add_node("identify_source", _placeholder("identify_source"))
    graph.add_node("collect_data", _placeholder("collect_data"))
    graph.add_node("classify_and_scan", _placeholder("classify_and_scan"))
    graph.add_node("deep_insight_and_route", _placeholder("deep_insight_and_route"))

    # 主路径边
    graph.add_edge("identify_source", "collect_data")
    graph.add_edge("collect_data", "classify_and_scan")
    graph.add_edge("classify_and_scan", "deep_insight_and_route")

    # ★ 条件分叉
    graph.add_conditional_edges(
        "deep_insight_and_route",
        route_by_error_code,
        {
            "fusion_path": "error_code_worker",
            "multi_agent_path": "doc_agent"
        }
    )

    # ── 融合路径节点 ──
    graph.add_node("error_code_worker", _placeholder("error_code_worker"))
    graph.add_node("history_worker_fusion", _placeholder("history_worker_fusion"))
    graph.add_node("fuse_simple", _placeholder("fuse_simple"))

    graph.add_edge("error_code_worker", "fuse_simple")
    graph.add_edge("history_worker_fusion", "fuse_simple")
    graph.add_edge("fuse_simple", "render_report")

    # ── 多 Agent 路径节点 ──
    graph.add_node("doc_agent", _placeholder("doc_agent"))
    graph.add_node("field_agent", _placeholder("field_agent"))
    graph.add_node("arbitrate", _placeholder("arbitrate"))

    # 并行分叉
    graph.add_edge("deep_insight_and_route", "field_agent")  # field_agent 也从分叉点启动

    # doc_agent 完成后等待 field_agent，然后检查冲突
    graph.add_conditional_edges(
        "field_agent",
        check_conflict,
        {"arbitrate": "arbitrate", "render": "render_report"}
    )
    graph.add_edge("doc_agent", "arbitrate")  # doc 结果进仲裁
    graph.add_edge("arbitrate", "render_report")

    # ── 终点 ──
    graph.add_node("render_report", _placeholder("render_report"))
    graph.add_edge("render_report", END)

    return graph


def _placeholder(name: str):
    """占位节点，后续替换为真实实现"""
    async def node(state: DiagnosisState) -> DiagnosisState:
        return state
    node.__name__ = name
    return node


# ────────────────────────────────────────────────────────────
# 编译
# ────────────────────────────────────────────────────────────

graph = build_graph()
checkpointer = build_checkpointer()
app = graph.compile(checkpointer=checkpointer)
