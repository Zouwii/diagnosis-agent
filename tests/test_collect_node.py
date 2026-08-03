from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.nodes.collect import collect_data
from engine.collectors.models import CollectionResult


async def run_inline(function, *args):
    return function(*args)


class CollectDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_logs_are_copied_into_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            uploads = temp_path / "tenants" / "owner" / "uploads"
            uploads.mkdir(parents=True)
            source = uploads / "source.log"
            source.write_text("614028 navigation error\n", encoding="utf-8")
            assigned_case_dir = temp_path / "tenants" / "owner" / "cases" / "case-local"

            with patch("agent.nodes.collect.asyncio.to_thread", side_effect=run_inline):
                result = await collect_data(
                    {
                        "case_id": "case-local",
                        "case_dir": str(assigned_case_dir),
                        "input_root": str(uploads),
                        "source_type": "local_logs",
                        "extra_params": {"log_path": str(source)},
                    }
                )

            materials = result["materials"]
            self.assertTrue(materials["collected"])
            self.assertEqual(materials["source"], "local_logs")
            self.assertEqual(len(materials["artifacts"]), 1)
            self.assertEqual(Path(materials["artifacts"][0]).read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertEqual(Path(materials["case_dir"]), assigned_case_dir)
            self.assertTrue((assigned_case_dir / "collection.json").exists())
            self.assertTrue((assigned_case_dir / "events.jsonl").exists())

    async def test_local_logs_cannot_escape_tenant_upload_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            uploads = temp_path / "uploads"
            uploads.mkdir()
            outside = temp_path / "other-tenant.log"
            outside.write_text("private\n", encoding="utf-8")
            with patch("agent.nodes.collect.asyncio.to_thread", side_effect=run_inline):
                result = await collect_data(
                    {
                        "case_id": "case-isolation",
                        "case_dir": str(temp_path / "cases" / "case-isolation"),
                        "input_root": str(uploads),
                        "source_type": "local_logs",
                        "extra_params": {"log_path": str(outside)},
                    }
                )

            self.assertFalse(result["materials"]["collected"])
            self.assertIn("outside the tenant's allowed input directories", result["materials"]["error"])

    async def test_local_logs_can_read_current_tenant_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            workspace = temp_path / "runtime" / "users" / "owner" / "workspaces" / "default"
            workspace.mkdir(parents=True)
            source = workspace / "robot.log"
            source.write_text("workspace log\n", encoding="utf-8")

            with patch("agent.nodes.collect.asyncio.to_thread", side_effect=run_inline):
                result = await collect_data(
                    {
                        "case_id": "case-workspace",
                        "case_dir": str(temp_path / "cases" / "case-workspace"),
                        "input_roots": [str(temp_path / "uploads"), str(workspace)],
                        "source_type": "local_logs",
                        "selected_skill": "robot-diagnosis",
                        "extra_params": {"log_path": str(source)},
                    }
                )

            self.assertTrue(result["materials"]["collected"])
            self.assertEqual(result["materials"]["metadata"]["collection_skill"], "robot-diagnosis")

    async def test_all_remote_sources_map_to_existing_collectors(self) -> None:
        cases = [
            (
                "tb_task",
                {"task_url": "https://www.teambition.com/task/694a3c1d1234567890abcdef"},
                {"task_id": "694a3c1d1234567890abcdef"},
            ),
            ("internal_robot", {"robot_ip": "172.22.0.222"}, {"robot_ip": "172.22.0.222"}),
            (
                "remote_site",
                {"frp_port": 22022, "site_robot_ip": "192.168.10.20"},
                {"frp_port": "22022", "site_robot_ip": "192.168.10.20"},
            ),
        ]

        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"DIAGNOSIS_CASES_DIR": temp}):
                for index, (source_type, params, expected) in enumerate(cases):
                    captured = []

                    def fake_collect(request):
                        captured.append(request)
                        return CollectionResult(
                            artifacts=[str(request.destination.raw_dir / "artifact.log")],
                            metadata={"method": source_type},
                        )

                    with self.subTest(source_type=source_type), patch(
                        "agent.nodes.collect.collect", side_effect=fake_collect
                    ), patch("agent.nodes.collect.asyncio.to_thread", side_effect=run_inline):
                        result = await collect_data(
                            {
                                "case_id": f"case-remote-{index}",
                                "source_type": source_type,
                                "extra_params": params,
                            }
                        )

                    self.assertTrue(result["materials"]["collected"])
                    self.assertEqual(len(captured), 1)
                    request = captured[0]
                    self.assertEqual(request.source_type, source_type)
                    for field, value in expected.items():
                        self.assertEqual(getattr(request, field), value)

    async def test_collection_failure_is_returned_in_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"DIAGNOSIS_CASES_DIR": temp}), patch(
                "agent.nodes.collect.asyncio.to_thread", side_effect=run_inline
            ):
                result = await collect_data(
                    {
                        "case_id": "case-failure",
                        "source_type": "remote_site",
                        "extra_params": {"frp_port": 22022},
                    }
                )

            manifest = json.loads((Path(temp) / "case-failure" / "collection.json").read_text(encoding="utf-8"))

        self.assertFalse(result["materials"]["collected"])
        self.assertIn("site_robot_ip", result["materials"]["error"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(manifest["collected"])

    async def test_collection_manifest_has_stable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "input.log"
            source.write_text("ok\n", encoding="utf-8")
            with patch.dict(os.environ, {"DIAGNOSIS_CASES_DIR": str(temp_path / "cases")}), patch(
                "agent.nodes.collect.asyncio.to_thread", side_effect=run_inline
            ):
                result = await collect_data(
                    {
                        "case_id": "case-contract",
                        "source_type": "local_logs",
                        "extra_params": {"log_path": str(source)},
                    }
                )

            manifest = json.loads((Path(result["materials"]["case_dir"]) / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {"collected", "source", "case_id", "case_dir", "raw_dir", "extracted_dir", "artifacts", "warnings", "metadata", "collected_at"},
                set(manifest),
            )


if __name__ == "__main__":
    unittest.main()
