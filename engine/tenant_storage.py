"""Tenant-isolated filesystem layout for diagnosis Cases."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
OWNER_SAFE_PATTERN = re.compile(r"^[a-f0-9]{24}$")
UPLOAD_ID_PATTERN = re.compile(r"^upload-[a-f0-9]{16}$")


def safe_owner_key(owner_key: str) -> str:
    """Match management-system's 24-character owner directory hash."""
    normalized = str(owner_key or "").strip()
    if not normalized:
        raise ValueError("owner_key is required")
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _private_dir(path: Path) -> Path:
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if created:
        path.chmod(0o700)
    return path


@dataclass(frozen=True)
class TenantStorage:
    """Resolve and persist paths without allowing tenant or Case traversal."""

    root: Path

    @classmethod
    def from_environment(cls) -> "TenantStorage":
        configured = os.environ.get("DIAGNOSIS_STORAGE_ROOT", "").strip()
        root = Path(configured).expanduser() if configured else PROJECT_ROOT / "data"
        return cls(root=root.resolve())

    def case_dir(self, owner_safe: str, case_id: str, *, create: bool = False) -> Path:
        if not OWNER_SAFE_PATTERN.fullmatch(owner_safe):
            raise ValueError("invalid owner_safe")
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError("invalid case_id")
        tenants_root = self.root / "tenants"
        tenant_root = tenants_root / owner_safe
        cases_root = tenant_root / "cases"
        path = cases_root / case_id
        if create:
            for directory in (self.root, tenants_root, tenant_root, cases_root, path):
                _private_dir(directory)
        return path

    def uploads_dir(self, owner_safe: str, *, create: bool = False) -> Path:
        if not OWNER_SAFE_PATTERN.fullmatch(owner_safe):
            raise ValueError("invalid owner_safe")
        tenants_root = self.root / "tenants"
        tenant_root = tenants_root / owner_safe
        path = tenant_root / "uploads"
        if create:
            for directory in (self.root, tenants_root, tenant_root, path):
                _private_dir(directory)
        return path

    def management_workspace_dir(self, owner_safe: str) -> Path | None:
        """Return this tenant's existing management-system workspace, if configured."""
        if not OWNER_SAFE_PATTERN.fullmatch(owner_safe):
            raise ValueError("invalid owner_safe")
        configured = os.environ.get("DIAGNOSIS_USER_WORKSPACES_ROOT", "").strip()
        if not configured:
            return None
        users_root = Path(configured).expanduser().resolve()
        workspace = (users_root / owner_safe / "workspaces" / "default").resolve()
        if not workspace.is_relative_to(users_root):
            raise ValueError("management workspace escapes the configured users root")
        return workspace if workspace.is_dir() else None

    def new_upload_path(self, owner_safe: str, filename: str) -> tuple[str, Path]:
        safe_name = Path(str(filename or "")).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("invalid upload filename")
        upload_id = f"upload-{uuid.uuid4().hex[:16]}"
        upload_dir = self.upload_dir(owner_safe, upload_id, create=True)
        return upload_id, upload_dir / safe_name

    def upload_dir(self, owner_safe: str, upload_id: str, *, create: bool = False) -> Path:
        if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
            raise ValueError("invalid upload_id")
        path = self.uploads_dir(owner_safe, create=create) / upload_id
        if create:
            _private_dir(path)
        return path

    def resolve_upload(self, owner_safe: str, upload_id: str) -> Path:
        path = self.upload_dir(owner_safe, upload_id)
        if not path.is_dir() or not any(child.is_file() for child in path.iterdir()):
            raise FileNotFoundError("upload not found")
        return path

    def write_case_record(self, owner_safe: str, case_id: str, record: dict[str, Any]) -> Path:
        case_dir = self.case_dir(owner_safe, case_id, create=True)
        target = case_dir / "case.json"
        temporary = case_dir / ".case.json.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(target)
        return target

    def read_case_record(self, owner_safe: str, case_id: str) -> dict[str, Any] | None:
        path = self.case_dir(owner_safe, case_id) / "case.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("owner_safe") != owner_safe or data.get("case_id") != case_id:
            return None
        return data
