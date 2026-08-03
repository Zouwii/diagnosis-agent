"""Tenant identity shared by HTTP authentication and storage code."""

from __future__ import annotations

from dataclasses import dataclass

from engine.tenant_storage import safe_owner_key


@dataclass(frozen=True)
class TenantIdentity:
    owner_key: str
    owner_safe: str

    @classmethod
    def from_owner_key(cls, owner_key: str) -> "TenantIdentity":
        normalized = str(owner_key or "").strip()
        return cls(owner_key=normalized, owner_safe=safe_owner_key(normalized))
