"""Thin LangGraph wrapper around the migrated diagnosis CLI engine."""

from __future__ import annotations

import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes.run_cli import run_cli_workflow
from agent.state import DiagnosisState


def build_graph() -> StateGraph:
    """Keep orchestration simple until the analysis and fusion agents are added."""
    graph = StateGraph(DiagnosisState)
    graph.add_node("run_cli_workflow", run_cli_workflow)
    graph.add_edge(START, "run_cli_workflow")
    graph.add_edge("run_cli_workflow", END)
    return graph


def _build_checkpointer():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        return PostgresSaver.from_conn_string(db_url)
    return MemorySaver()


graph = build_graph()
checkpointer = _build_checkpointer()
app = graph.compile(checkpointer=checkpointer)
