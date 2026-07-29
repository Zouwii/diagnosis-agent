"""Unified dispatcher for all supported diagnosis material sources."""

from __future__ import annotations

from pathlib import Path

from engine.collectors.local_logs import import_local_materials
from engine.collectors.models import CollectionRequest, CollectionResult
from engine.collectors.remote_hand import collect_remote_site_materials
from engine.collectors.ssh_robot import collect_internal_robot_materials
from engine.collectors.teambition import collect_teambition_materials


def collect(request: CollectionRequest) -> CollectionResult:
    destination = request.destination
    if request.source_type == "tb_task":
        if not request.task_id:
            raise ValueError("tb_task collection requires task_id")
        result, bundle = collect_teambition_materials(
            task_id=request.task_id,
            destination=destination,
            allow_large_downloads=request.allow_large_downloads,
            allow_all_attachments=request.allow_all_attachments,
        )
        result.payload = bundle
        return result
    if request.source_type == "internal_robot":
        if not request.robot_ip:
            raise ValueError("internal_robot collection requires robot_ip")
        if not request.collect_remote:
            return CollectionResult(metadata={"collection_skipped": True})
        return CollectionResult(artifacts=collect_internal_robot_materials(request.robot_ip, destination.raw_dir), metadata={"robot_ip": request.robot_ip, "method": "ssh"})
    if request.source_type == "remote_site":
        if not request.frp_port or not request.site_robot_ip:
            raise ValueError("remote_site collection requires frp_port and site_robot_ip")
        if not request.collect_remote:
            return CollectionResult(metadata={"collection_skipped": True})
        return CollectionResult(artifacts=collect_remote_site_materials(request.frp_port, request.site_robot_ip, destination.raw_dir), metadata={"frp_port": request.frp_port, "site_robot_ip": request.site_robot_ip, "method": "remote_hand"})
    if request.source_type == "local_logs":
        if not request.log_path:
            raise ValueError("local_logs collection requires log_path")
        return CollectionResult(artifacts=import_local_materials(Path(request.log_path).expanduser(), destination.raw_dir), metadata={"log_path": request.log_path, "method": "local_copy"})
    raise ValueError(f"unsupported source_type: {request.source_type}")
