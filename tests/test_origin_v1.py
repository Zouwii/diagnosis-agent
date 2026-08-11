from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.nodes.origin_v1 import run_origin_v1
from engine.collectors.models import CollectionResult


class OriginV1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_complete_workflow_once_with_analysis_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case-origin-v1"
            case_dir.mkdir(parents=True)
            fake_result = SimpleNamespace(
                context={
                    "created_at": "2026-08-10T00:00:00+00:00",
                    "analysis_summary": {
                        "findings": [{"message": "detected"}],
                        "error_codes": ["614028"],
                        "analysis_trace": {"problem_type": "device_sensor"},
                        "deep_insights": [],
                        "specialty_findings": [],
                        "analysis_route": ["robot-diagnosis"],
                    },
                    "conclusion_status": "likely",
                },
                collection=CollectionResult(
                    artifacts=[str(case_dir / "raw" / "input.log")],
                    metadata={"source": "local_logs"},
                ),
            )
            state = {
                "case_id": "case-origin-v1",
                "case_dir": str(case_dir),
                "input_roots": [str(Path(temp))],
                "source_type": "local_logs",
                "symptom": "二维码识别异常",
                "selected_skill": "robot-diagnosis",
                "extra_params": {
                    "log_path": str(Path(temp) / "input.log"),
                    "external_evidence": False,
                },
            }

            with patch("agent.nodes.origin_v1.run_case", return_value=fake_result) as mocked:
                result = await run_origin_v1(state)

            mocked.assert_called_once()
            request = mocked.call_args.args[0]
            self.assertTrue(request.analyze)
            self.assertFalse(request.external_evidence)
            self.assertEqual(result["error_codes"], ["614028"])
            self.assertEqual(result["conclusion_status"], "likely")
            self.assertTrue((case_dir / "collection.json").is_file())

    async def test_propagates_complete_workflow_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = {
                "case_id": "case-origin-v1-error",
                "case_dir": str(Path(temp) / "case-origin-v1-error"),
                "input_roots": [temp],
                "source_type": "local_logs",
                "extra_params": {"log_path": str(Path(temp) / "input.log")},
            }
            with patch(
                "agent.nodes.origin_v1.run_case",
                side_effect=RuntimeError("diagnosis_cli failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "diagnosis_cli failed"):
                    await run_origin_v1(state)


if __name__ == "__main__":
    unittest.main()
