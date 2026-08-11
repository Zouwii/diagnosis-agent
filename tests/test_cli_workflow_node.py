from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.nodes.origin_v1 import run_origin_v1
class CliWorkflowNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_material_runs_complete_migrated_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()
            source = uploads / "nav-manager.log"
            source.write_text(
                "2026-08-03 10:00:00 ERROR error_code: 614028 camera missed\n",
                encoding="utf-8",
            )
            case_dir = root / "cases" / "case-cli"

            result = await run_origin_v1({
                    "case_id": "case-cli",
                    "case_dir": str(case_dir),
                    "input_roots": [str(uploads)],
                    "source_type": "local_logs",
                    "selected_skill": "robot-diagnosis",
                    "symptom": "机器人二维码识别异常，错误码614028",
                    "time_window": "2026-08-03 10:00:00",
                    "extra_params": {
                        "log_path": str(source),
                        "external_evidence": False,
                    },
            })

            self.assertTrue(result["materials"]["collected"])
            self.assertIn("614028", result["error_codes"])
            self.assertGreaterEqual(len(result["findings"]), 1)
            self.assertTrue((case_dir / "context.json").is_file())
            self.assertTrue((case_dir / "status.json").is_file())
            self.assertTrue((case_dir / "collection.json").is_file())
            self.assertTrue((case_dir / "report.md").is_file())
            self.assertTrue((case_dir / "human-handoff.md").is_file())
            self.assertTrue((case_dir / "knowledge-draft.md").is_file())
            self.assertEqual(result["report_path"], str(case_dir / "report.md"))

    async def test_local_material_keeps_tenant_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()
            outside = root / "outside.log"
            outside.write_text("private\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outside the tenant"):
                await run_origin_v1(
                    {
                        "case_id": "case-isolation",
                        "case_dir": str(root / "cases" / "case-isolation"),
                        "input_roots": [str(uploads)],
                        "source_type": "local_logs",
                        "symptom": "test",
                        "extra_params": {
                            "log_path": str(outside),
                            "external_evidence": False,
                        },
                    }
                )


if __name__ == "__main__":
    unittest.main()
