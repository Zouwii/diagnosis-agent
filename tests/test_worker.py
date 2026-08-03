from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from engine.tenant_storage import TenantStorage
from server.worker import run_pending_once


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_case_is_executed_from_persistent_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp).resolve())
            owner = "a" * 24
            case_id = "case-worker"
            uploads = storage.uploads_dir(owner, create=True)
            source = uploads / "input.log"
            source.write_text("ERROR navigation failed\n", encoding="utf-8")
            case_dir = storage.case_dir(owner, case_id, create=True)
            now = datetime.now(timezone.utc).isoformat()
            storage.write_case_record(owner, case_id, {
                "case_id": case_id,
                "owner_safe": owner,
                "case_dir": str(case_dir),
                "input_root": str(uploads),
                "input_roots": [str(uploads)],
                "status": "pending",
                "source_type": "local_logs",
                "mode": "local_logs",
                "selected_skill": "robot-diagnosis",
                "analysis_skill": "robot-diagnosis",
                "symptom": "导航失败",
                "extra_params": {
                    "log_path": str(source),
                    "time_window": "",
                    "knowledge_sources": [],
                    "code_sources": [],
                },
                "conclusion_status": None,
                "report_url": None,
                "report_path": None,
                "created_at": now,
                "updated_at": now,
                "progress_events": [],
                "error": None,
            })

            completed = await run_pending_once(storage)
            record = storage.read_case_record(owner, case_id)

            self.assertEqual(completed, 1)
            self.assertEqual(record["status"], "closed")
            self.assertEqual(record["report_url"], f"/api/cases/{case_id}/report")
            self.assertTrue(Path(record["report_path"]).is_file())
            self.assertFalse((case_dir / ".worker.lock").exists())

    async def test_terminal_case_is_not_reexecuted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp).resolve())
            owner = "b" * 24
            case_id = "case-closed"
            storage.write_case_record(owner, case_id, {
                "case_id": case_id,
                "owner_safe": owner,
                "status": "closed",
            })
            self.assertEqual(await run_pending_once(storage), 0)


if __name__ == "__main__":
    unittest.main()
