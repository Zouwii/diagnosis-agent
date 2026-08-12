from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from server.claude_origin import ClaudeOriginResult
from server.case_runner import run_diagnosis


class FakeGraph:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.input = None
        self.config = None

    async def ainvoke(self, graph_input, config):
        self.input = graph_input
        self.config = config
        if self.error:
            raise self.error
        return self.result


def make_request(**overrides):
    values = {
        "mode": "internal_robot",
        "symptom": "diagnosis",
        "time_window": None,
        "robot_ip": None,
        "task_url": None,
        "frp_port": None,
        "site_robot_ip": None,
        "log_path": None,
        "upload_id": None,
        "knowledge_sources": [],
        "code_sources": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def seed_case(case_id: str, req) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    case = {
        "case_id": case_id,
        "owner_safe": "a" * 24,
        "case_dir": "",
        "input_root": "",
        "input_roots": [],
        "status": "pending",
        "source_type": req.mode,
        "mode": req.mode,
        "selected_skill": {
            "internal_robot": "robot-peek",
            "tb_task": "teambition",
            "remote_site": "remote-hand",
            "local_logs": "robot-diagnosis",
        }[req.mode],
        "analysis_skill": "robot-diagnosis",
        "symptom": req.symptom,
        "conclusion_status": None,
        "report_url": None,
        "report_path": None,
        "created_at": now,
        "updated_at": now,
        "progress_events": [],
        "error": None,
    }
    return case


class RunDiagnosisTests(unittest.IsolatedAsyncioTestCase):
    async def test_claude_origin_runner_result_is_persisted_and_report_exposed(self) -> None:
        req = make_request(mode="local_logs", symptom="Claude 诊断")
        case_id = "case-api-claude"
        case = seed_case(case_id, req)
        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / case_id
            case_dir.mkdir()
            report = case_dir / "report.md"
            report.write_text("# Claude report\n", encoding="utf-8")
            case["case_dir"] = str(case_dir)
            fake = ClaudeOriginResult(True, report_path=str(report), session_id="session-test")
            with patch("server.claude_origin.ClaudeOriginRunner") as runner_class, patch(
                "server.case_runner.asyncio.to_thread", new=AsyncMock(return_value=fake)
            ):
                runner_class.return_value.run.return_value = fake
                await run_diagnosis(case_id, case, req, version="claude-origin-v1")

        self.assertEqual(case["status"], "awaiting_human")
        self.assertEqual(case["runtime"]["session_id"], "session-test")
        self.assertEqual(case["report_url"], f"/api/cases/{case_id}/report")

    async def test_claude_origin_failure_does_not_remain_running(self) -> None:
        req = make_request(mode="local_logs", symptom="材料不足")
        case_id = "case-api-claude-failed"
        case = seed_case(case_id, req)
        fake = ClaudeOriginResult(False, error="材料不足：raw/ 为空", exit_code=1, session_id="session-failed")
        with patch("server.claude_origin.ClaudeOriginRunner") as runner_class, patch(
            "server.case_runner.asyncio.to_thread", new=AsyncMock(return_value=fake)
        ):
            runner_class.return_value.run.return_value = fake
            await run_diagnosis(case_id, case, req, version="claude-origin-v1")
        self.assertEqual(case["status"], "failed")
        self.assertIn("材料不足", case["error"])

    async def test_success_invokes_graph_and_exposes_existing_report(self) -> None:
        req = make_request(
            mode="remote_site",
            symptom="现场机器人导航异常",
            time_window="2026-08-03 10:00",
            frp_port=22022,
            site_robot_ip="192.168.10.20",
            knowledge_sources=["kb/navigation"],
            code_sources=["nav-manager"],
        )
        case_id = "case-api-success"
        case = seed_case(case_id, req)

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / case_id
            case_dir.mkdir()
            report = case_dir / "report.md"
            report.write_text("# diagnosis\n", encoding="utf-8")
            graph = FakeGraph(
                {
                    "source_type": "remote_site",
                    "materials": {"collected": True, "case_dir": str(case_dir)},
                    "conclusion_status": "confirmed",
                    "report_path": str(report),
                    "errors": [],
                }
            )
            persisted_statuses = []
            with patch("server.case_runner._graph_app", return_value=graph):
                await run_diagnosis(
                    case_id,
                    case,
                    req,
                    persist=lambda record: persisted_statuses.append(record["status"]),
                )

        self.assertEqual(case["status"], "closed")
        self.assertEqual(case["conclusion_status"], "confirmed")
        self.assertEqual(case["report_url"], f"/api/cases/{case_id}/report")
        self.assertEqual(graph.config, {"configurable": {"thread_id": case_id}})
        self.assertEqual(graph.input["case_id"], case_id)
        self.assertEqual(graph.input["extra_params"]["frp_port"], 22022)
        self.assertEqual(graph.input["extra_params"]["site_robot_ip"], "192.168.10.20")
        self.assertEqual(graph.input["time_window"], "2026-08-03 10:00")
        self.assertEqual(graph.input["source_type"], "remote_site")
        self.assertEqual(graph.input["selected_skill"], "remote-hand")
        self.assertEqual(persisted_statuses[0], "collecting")
        self.assertEqual(persisted_statuses[-1], "closed")

    async def test_collection_failure_marks_case_failed(self) -> None:
        req = make_request(mode="local_logs", symptom="日志诊断", log_path="/missing/log")
        case_id = "case-api-collection-failure"
        case = seed_case(case_id, req)
        graph = FakeGraph(
            {
                "source_type": "local_logs",
                "materials": {"collected": False, "error": "log path does not exist"},
                "conclusion_status": "insufficient_data",
                "errors": ["local_logs collection failed"],
            }
        )

        with patch("server.case_runner._graph_app", return_value=graph):
            await run_diagnosis(case_id, case, req)

        self.assertEqual(case["status"], "failed")
        self.assertEqual(case["error"], "log path does not exist")
        self.assertIsNone(case["report_url"])

    async def test_graph_exception_marks_case_failed(self) -> None:
        req = make_request(mode="tb_task", symptom="任务诊断", task_url="https://example.com/task/123")
        case_id = "case-api-graph-failure"
        case = seed_case(case_id, req)
        graph = FakeGraph(error=RuntimeError("graph unavailable"))

        with patch("server.case_runner._graph_app", return_value=graph):
            await run_diagnosis(case_id, case, req)

        self.assertEqual(case["status"], "failed")
        self.assertEqual(case["error"], "graph unavailable")

    async def test_unconfirmed_result_waits_for_human(self) -> None:
        req = make_request(mode="internal_robot", symptom="无明确结论", robot_ip="172.22.0.2")
        case_id = "case-api-human"
        case = seed_case(case_id, req)
        graph = FakeGraph(
            {
                "source_type": "internal_robot",
                "materials": {"collected": True, "case_dir": "/tmp/case-api-human"},
                "conclusion_status": "insufficient_data",
                "errors": [],
            }
        )

        with patch("server.case_runner._graph_app", return_value=graph):
            await run_diagnosis(case_id, case, req)

        self.assertEqual(case["status"], "awaiting_human")
if __name__ == "__main__":
    unittest.main()
