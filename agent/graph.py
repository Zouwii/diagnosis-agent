"""LangGraph diagnosis graphs — origin, origin-v1, origin-split, graph-v1."""

from __future__ import annotations

import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes.run_cli import run_cli_workflow
from agent.nodes.analyze import analyze_engine
from agent.nodes.origin_v1 import run_origin_v1
from agent.nodes.report import write_report_node
from agent.state import DiagnosisState


def build_origin_v1_graph() -> StateGraph:
    """Run the complete migrated diagnosis_cli as one graph node."""
    graph = StateGraph(DiagnosisState)
    graph.add_node("diagnosis_cli", run_origin_v1)
    graph.add_edge(START, "diagnosis_cli")
    graph.add_edge("diagnosis_cli", END)
    return graph


def build_graph_v1() -> StateGraph:
    """graph-v1: engine collect → engine analyze → report"""
    graph = StateGraph(DiagnosisState)
    graph.add_node("collect", run_cli_workflow)
    graph.add_node("analyze", analyze_engine)
    graph.add_node("report", write_report_node)
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "report")
    graph.add_edge("report", END)
    return graph


def _build_checkpointer():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from langgraph.checkpoint.postgres import PostgresSaver
        return PostgresSaver.from_conn_string(db_url)
    return MemorySaver()


checkpointer = _build_checkpointer()

GRAPHS = {
    "origin-v1":    build_origin_v1_graph().compile(checkpointer=checkpointer),
    "origin-split": build_graph_v1().compile(checkpointer=checkpointer),                      # engine 子函数拆分
    "graph-v1":     build_graph_v1().compile(checkpointer=checkpointer),                      # graph后续(同split)
}

app = GRAPHS["graph-v1"]
