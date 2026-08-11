"""Single-host file-queue worker for persistent diagnosis Cases."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from engine.tenant_storage import TenantStorage
from server.case_runner import run_diagnosis


TERMINAL_STATUSES = {"awaiting_human", "closed", "failed"}


def _request_from_case(case: dict[str, Any]) -> SimpleNamespace:
    params = dict(case.get("extra_params") or {})
    return SimpleNamespace(
        mode=str(case.get("mode") or case.get("source_type") or ""),
        symptom=str(case.get("symptom") or ""),
        time_window=params.get("time_window"),
        robot_ip=params.get("robot_ip"),
        task_url=params.get("task_url"),
        frp_port=params.get("frp_port"),
        site_robot_ip=params.get("site_robot_ip"),
        log_path=params.get("log_path"),
        upload_id=params.get("upload_id"),
        knowledge_sources=list(params.get("knowledge_sources") or []),
        code_sources=list(params.get("code_sources") or []),
    )


def _case_records(storage: TenantStorage) -> list[Path]:
    return sorted((storage.root / "tenants").glob("*/cases/*/case.json"))


def _claim(case_dir: Path) -> Path | None:
    lock_path = case_dir / ".worker.lock"
    try:
        with lock_path.open("x", encoding="utf-8") as lock:
            lock.write(f"pid={os.getpid()}\n")
    except FileExistsError:
        return None
    return lock_path


async def run_pending_once(storage: TenantStorage | None = None) -> int:
    """Claim and execute every currently pending Case once."""
    storage = storage or TenantStorage.from_environment()
    completed = 0
    for record_path in _case_records(storage):
        try:
            case = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if case.get("status") != "pending":
            continue
        case_dir = record_path.parent
        lock_path = _claim(case_dir)
        if lock_path is None:
            continue
        try:
            owner_safe = str(case.get("owner_safe") or "")
            case_id = str(case.get("case_id") or "")
            current = storage.read_case_record(owner_safe, case_id)
            if current is None or current.get("status") != "pending":
                continue

            def persist(record: dict[str, Any]) -> None:
                storage.write_case_record(owner_safe, case_id, record)

            print(f"[diagnosis-worker] start case={case_id} mode={current.get('mode')} version={current.get('version','graph-v1')}", flush=True)
            await run_diagnosis(case_id, current, _request_from_case(current), version=str(current.get("version") or "graph-v1"), persist=persist)
            print(f"[diagnosis-worker] finish case={case_id} status={current.get('status')}", flush=True)
            completed += 1
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
    return completed


async def worker_loop() -> None:
    poll_seconds = max(0.2, float(os.getenv("DIAGNOSIS_WORKER_POLL_SECONDS", "1")))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass
    print(f"[diagnosis-worker] started poll={poll_seconds}s", flush=True)
    while not stop.is_set():
        await run_pending_once()
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            pass
    print("[diagnosis-worker] stopped", flush=True)


def main() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
