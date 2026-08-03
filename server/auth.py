"""Authenticate Diagnosis Agent requests through the management-system identity."""

from __future__ import annotations

import os
import secrets

import httpx
from fastapi import HTTPException, Request

from server.identity import TenantIdentity


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _identity_from_profile(profile: dict) -> TenantIdentity | None:
    for key in ("user_id", "userid", "id", "name"):
        value = str(profile.get(key) or "").strip()
        if value:
            return TenantIdentity.from_owner_key(value)
    return None


async def require_tenant(request: Request) -> TenantIdentity:
    """Resolve only trusted proxy headers or a verified management session."""
    forwarded_user = request.headers.get("x-diagnosis-user-id", "").strip()
    if forwarded_user:
        expected = os.environ.get("DIAGNOSIS_INTERNAL_TOKEN", "").strip()
        provided = request.headers.get("x-diagnosis-internal-token", "").strip()
        if not expected or not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid internal identity token")
        return TenantIdentity.from_owner_key(forwarded_user)

    cookie = request.headers.get("cookie", "").strip()
    if cookie:
        base_url = os.environ.get("MANAGEMENT_SYSTEM_URL", "http://127.0.0.1:5002").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/api/bt/auth/me", headers={"Cookie": cookie})
            if response.status_code == 200:
                payload = response.json()
                profile = payload.get("data") if isinstance(payload, dict) else None
                identity = _identity_from_profile(profile if isinstance(profile, dict) else {})
                if identity:
                    return identity
        except (httpx.HTTPError, ValueError):
            pass

    if _enabled("DIAGNOSIS_ALLOW_ANONYMOUS"):
        return TenantIdentity.from_owner_key("anonymous")
    raise HTTPException(status_code=401, detail="Authentication required")
