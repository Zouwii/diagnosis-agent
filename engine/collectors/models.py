"""Contracts shared by all diagnosis material collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CollectionDestination:
    raw_dir: Path
    extracted_dir: Path


@dataclass(frozen=True)
class CollectionRequest:
    """Source-neutral request accepted by the Collector dispatcher."""

    source_type: str
    destination: CollectionDestination
    task_id: str = ""
    robot_ip: str = ""
    frp_port: str = ""
    site_robot_ip: str = ""
    log_path: str = ""
    collect_remote: bool = True
    allow_large_downloads: bool = False
    allow_all_attachments: bool = False


@dataclass
class CollectionResult:
    """Materials, warnings, metadata, and optional source payload."""

    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
