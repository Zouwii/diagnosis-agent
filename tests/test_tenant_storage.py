from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tenant_storage import TenantStorage, safe_owner_key


class TenantStorageTests(unittest.TestCase):
    def test_owner_hash_matches_management_system_contract(self) -> None:
        owner_key = "ding-user-123"
        expected = hashlib.sha256(owner_key.encode("utf-8")).hexdigest()[:24]
        self.assertEqual(safe_owner_key(owner_key), expected)

    def test_tenants_get_separate_case_and_upload_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp))
            first = safe_owner_key("user-a")
            second = safe_owner_key("user-b")
            first_case = storage.case_dir(first, "case-same", create=True)
            second_case = storage.case_dir(second, "case-same", create=True)
            first_uploads = storage.uploads_dir(first, create=True)
            second_uploads = storage.uploads_dir(second, create=True)

            self.assertNotEqual(first_case, second_case)
            self.assertNotEqual(first_uploads, second_uploads)
            self.assertEqual(first_case.stat().st_mode & 0o777, 0o700)
            self.assertEqual(first_uploads.stat().st_mode & 0o777, 0o700)

    def test_case_record_is_private_and_owner_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp))
            owner = safe_owner_key("user-a")
            other = safe_owner_key("user-b")
            record = {"case_id": "case-1", "owner_safe": owner, "status": "pending"}
            path = storage.write_case_record(owner, "case-1", record)

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(storage.read_case_record(owner, "case-1"), record)
            self.assertIsNone(storage.read_case_record(other, "case-1"))

    def test_upload_id_resolves_only_inside_its_tenant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp))
            owner = safe_owner_key("user-a")
            other = safe_owner_key("user-b")
            upload_id, target = storage.new_upload_path(owner, "../robot.log")
            target.write_text("log\n", encoding="utf-8")

            self.assertEqual(target.name, "robot.log")
            self.assertEqual(storage.resolve_upload(owner, upload_id), target.parent)
            with self.assertRaises(FileNotFoundError):
                storage.resolve_upload(other, upload_id)
            with self.assertRaises(ValueError):
                storage.resolve_upload(owner, "../upload")

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            storage = TenantStorage(Path(temp))
            owner = safe_owner_key("user-a")
            with self.assertRaises(ValueError):
                storage.case_dir(owner, "../other")
            with self.assertRaises(ValueError):
                storage.case_dir("not-a-hash", "case-1")

    def test_management_workspace_is_scoped_to_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            users_root = Path(temp) / "runtime" / "users"
            owner = safe_owner_key("user-a")
            workspace = users_root / owner / "workspaces" / "default"
            workspace.mkdir(parents=True)
            storage = TenantStorage(Path(temp) / "diagnosis")
            with patch.dict(os.environ, {"DIAGNOSIS_USER_WORKSPACES_ROOT": str(users_root)}):
                self.assertEqual(storage.management_workspace_dir(owner), workspace.resolve())


if __name__ == "__main__":
    unittest.main()
