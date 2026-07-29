"""Requests and results used by diagnosis application workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.collectors.models import CollectionResult


@dataclass(frozen=True)
class RunCaseRequest:
    case_id: str
    case_dir: Path
    source_type: str
    symptom: str = ""
    time_window: str = ""
    task_id: str = ""
    task_url: str = ""
    robot_ip: str = ""
    frp_port: str = ""
    site_robot_ip: str = ""
    log_path: str = ""
    artifacts: list[str] = field(default_factory=list)
    knowledge_sources: list[str] = field(default_factory=list)
    code_sources: list[str] = field(default_factory=list)
    collect_remote: bool = True
    allow_large_downloads: bool = False
    allow_all_attachments: bool = False
    analyze: bool = True
    external_evidence: bool = True


@dataclass
class RunCaseResult:
    context: dict[str, Any]
    collection: CollectionResult
