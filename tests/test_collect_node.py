from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.nodes.collect import collect_materials


class CollectMaterialsTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_logs_are_copied_into_assigned_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()
            source = uploads / "source.log"
            source.write_text("614028 navigation error\n", encoding="utf-8")
            case_dir = root / "cases" / "case-local"

            result = await collect_materials(
                {
                    "case_id": "case-local",
                    "case_dir": str(case_dir),
                    "input_roots": [str(uploads)],
                    "source_type": "local_logs",
                    "selected_skill": "robot-diagnosis",
                    "extra_params": {
                        "log_path": str(source),
                        "external_evidence": False,
                    },
                }
            )

            materials = result["materials"]
            self.assertTrue(materials["collected"])
            self.assertEqual(materials["source"], "local_logs")
            self.assertEqual(materials["metadata"]["collection_skill"], "robot-diagnosis")
            self.assertEqual(len(materials["artifacts"]), 1)
            self.assertTrue((case_dir / "collection.json").is_file())

    async def test_local_logs_cannot_escape_tenant_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()
            outside = root / "other-tenant.log"
            outside.write_text("private\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outside the tenant"):
                await collect_materials(
                    {
                        "case_id": "case-isolation",
                        "case_dir": str(root / "cases" / "case-isolation"),
                        "input_roots": [str(uploads)],
                        "source_type": "local_logs",
                        "extra_params": {"log_path": str(outside)},
                    }
                )

    async def test_collection_manifest_has_stable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()
            source = uploads / "input.log"
            source.write_text("ok\n", encoding="utf-8")
            case_dir = root / "cases" / "case-contract"

            await collect_materials(
                {
                    "case_id": "case-contract",
                    "case_dir": str(case_dir),
                    "input_roots": [str(uploads)],
                    "source_type": "local_logs",
                    "extra_params": {"log_path": str(source), "external_evidence": False},
                }
            )

            manifest = json.loads((case_dir / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "collected",
                    "source",
                    "case_id",
                    "case_dir",
                    "raw_dir",
                    "extracted_dir",
                    "artifacts",
                    "warnings",
                    "metadata",
                    "collected_at",
                },
                set(manifest),
            )


if __name__ == "__main__":
    unittest.main()
