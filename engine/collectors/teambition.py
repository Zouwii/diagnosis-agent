"""Teambition material collection adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.collectors.models import CollectionDestination, CollectionResult
from engine.teambition_client import fetch_and_download_task_materials


def collect_teambition_materials(
    *,
    task_id: str,
    destination: CollectionDestination,
    allow_large_downloads: bool = False,
    allow_all_attachments: bool = False,
) -> tuple[CollectionResult, dict[str, Any]]:
    """Fetch one task and stage all allowed material under a Case directory.

    The raw API response is retained for compatibility with the current Case
    schema; callers should consume ``CollectionResult`` for collector-facing
    behavior.
    """
    bundle = fetch_and_download_task_materials(
        task_id=task_id,
        raw_dir=destination.raw_dir,
        extracted_dir=destination.extracted_dir,
        allow_large_downloads=allow_large_downloads,
        allow_all_attachments=allow_all_attachments,
    )
    artifacts = [
        str(destination.raw_dir / "teambition-task.json"),
        str(destination.raw_dir / "teambition-activities.json"),
        str(destination.raw_dir / "teambition-attachments.json"),
        *[str(item) for item in bundle.get("downloaded_files", [])],
        *[str(item) for item in bundle.get("extracted_dirs", [])],
    ]
    if bundle.get("manifest_path"):
        artifacts.append(str(bundle["manifest_path"]))
    if bundle.get("error_path"):
        artifacts.append(str(bundle["error_path"]))

    return (
        CollectionResult(
            artifacts=artifacts,
            warnings=[str(item) for item in bundle.get("warnings", [])],
            metadata={
                "task_id": task_id,
                "downloaded_count": len(bundle.get("downloaded_files", [])),
                "extracted_count": len(bundle.get("extracted_dirs", [])),
            },
        ),
        bundle,
    )
