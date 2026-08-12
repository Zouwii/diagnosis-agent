"""Case API - 诊断 Case 的创建、查询、进度推送"""

import uuid
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from engine.mode_registry import validate_mode_params
from engine.tenant_storage import TenantStorage
from server.auth import require_tenant
from server.identity import TenantIdentity

router = APIRouter(prefix="/api/cases", tags=["cases"])

# ────────────────────────────────────────────────────────────
# 内存存储（后续迁移到 Postgres）
# ────────────────────────────────────────────────────────────

_cases: dict[str, dict] = {}


# ────────────────────────────────────────────────────────────
# 请求/响应模型
# ────────────────────────────────────────────────────────────

class CreateCaseRequest(BaseModel):
    mode: Literal["internal_robot", "tb_task", "remote_site", "local_logs"]
    version: Literal["claude-origin-v1", "origin-v1", "origin-split", "graph-v1"] = Field(
        default_factory=lambda: (
            os.getenv("DIAGNOSIS_DEFAULT_RUNTIME", "claude-origin-v1").strip()
            if os.getenv("DIAGNOSIS_DEFAULT_RUNTIME", "claude-origin-v1").strip()
            in {"claude-origin-v1", "origin-v1", "origin-split", "graph-v1"}
            else "claude-origin-v1"
        )
    )
    # 按来源二选一
    robot_ip: str | None = Field(None, description="内网机器人 IP，如 172.22.0.222")
    task_url: str | None = Field(None, description="TB 任务链接")
    frp_port: int | None = Field(None, description="远程现场 frp 端口")
    site_robot_ip: str | None = Field(None, description="现场机器人 IP")
    log_path: str | None = Field(None, description="当前租户工作区或 uploads 目录内的服务器路径")
    upload_id: str | None = Field(None, description="由日志上传接口返回的 ID")
    # 通用
    symptom: str | None = Field(None, description="问题现象，tb_task 可省略（自动从 TB 标题提取）")
    time_window: str | None = Field(None, description="问题时间，如 '2026-07-27 20:00'")
    knowledge_sources: list[str] = Field(default_factory=list)
    code_sources: list[str] = Field(default_factory=list)


class CaseResponse(BaseModel):
    case_id: str
    version: str | None = None
    status: Literal["pending", "collecting", "analyzing", "awaiting_human", "closed", "failed"]
    source_type: str
    mode: str
    selected_skill: str
    analysis_skill: str
    symptom: str
    conclusion_status: str | None
    report_url: str | None
    error: str | None = None
    created_at: str
    updated_at: str


class CaseProgressEvent(BaseModel):
    event: str          # "node_start" | "node_complete" | "retry" | "fallback" | "error"
    node: str           # 当前节点名
    message: str        # 人可读的进度描述
    timestamp: str


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size: int


# ────────────────────────────────────────────────────────────
# API 路由
# ────────────────────────────────────────────────────────────

@router.post("/uploads", response_model=UploadResponse, status_code=201)
async def upload_material(
    file: UploadFile = File(...),
    tenant: TenantIdentity = Depends(require_tenant),
):
    """Stage one local material file inside the authenticated tenant boundary."""
    storage = TenantStorage.from_environment()
    try:
        upload_id, target = storage.new_upload_path(tenant.owner_safe, file.filename or "upload.bin")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    max_bytes = int(os.environ.get("DIAGNOSIS_UPLOAD_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
    size = 0
    try:
        with target.open("xb") as output:
            target.chmod(0o600)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
                output.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        try:
            target.parent.rmdir()
        except OSError:
            pass
        raise
    finally:
        await file.close()
    return UploadResponse(upload_id=upload_id, filename=target.name, size=size)


@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(
    req: CreateCaseRequest,
    tenant: TenantIdentity = Depends(require_tenant),
):
    """Create a persistent pending Case for the diagnosis worker."""
    case_id = f"case-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    storage = TenantStorage.from_environment()
    uploads_root = storage.uploads_dir(tenant.owner_safe, create=True).resolve()
    input_roots = [uploads_root]
    workspace_root = storage.management_workspace_dir(tenant.owner_safe)
    if workspace_root is not None:
        input_roots.append(workspace_root)
    if req.upload_id:
        try:
            req.log_path = str(storage.resolve_upload(tenant.owner_safe, req.upload_id))
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif req.log_path:
        resolved_log = Path(req.log_path).expanduser().resolve()
        if not any(resolved_log.is_relative_to(root) for root in input_roots):
            raise HTTPException(
                status_code=400,
                detail="log_path must be inside the current tenant workspace or upload directory",
            )
        req.log_path = str(resolved_log)

    params = {
        "robot_ip": req.robot_ip,
        "task_url": req.task_url,
        "frp_port": req.frp_port,
        "site_robot_ip": req.site_robot_ip,
        "log_path": req.log_path,
        "upload_id": req.upload_id,
    }
    try:
        mode_spec = validate_mode_params(req.mode, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    case_dir = storage.case_dir(tenant.owner_safe, case_id, create=True)

    _cases[case_id] = {
        "case_id": case_id,
        "owner_safe": tenant.owner_safe,
        "case_dir": str(case_dir),
        "input_root": str(uploads_root),
        "input_roots": [str(root) for root in input_roots],
        "status": "pending",
        "version": req.version,
        "source_type": req.mode,
        "mode": req.mode,
        "selected_skill": mode_spec.collection_skill,
        "analysis_skill": mode_spec.analysis_skill,
        "symptom": req.symptom,
        "extra_params": {
            "robot_ip": req.robot_ip,
            "task_url": req.task_url,
            "frp_port": req.frp_port,
            "site_robot_ip": req.site_robot_ip,
            "log_path": req.log_path,
            "upload_id": req.upload_id,
            "time_window": req.time_window,
            "knowledge_sources": req.knowledge_sources,
            "code_sources": req.code_sources,
        },
        "conclusion_status": None,
        "report_url": None,
        "report_path": None,
        "created_at": now,
        "updated_at": now,
        "progress_events": [],
        "error": None,
    }
    storage.write_case_record(tenant.owner_safe, case_id, _cases[case_id])

    return CaseResponse(**_cases[case_id])


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str, tenant: TenantIdentity = Depends(require_tenant)):
    """查询 Case 状态"""
    case = _owned_case(case_id, tenant)
    return CaseResponse(**case)


@router.get("/{case_id}/stream")
async def stream_progress(case_id: str, tenant: TenantIdentity = Depends(require_tenant)):
    """SSE 推送诊断进度"""
    _owned_case(case_id, tenant)
    storage = TenantStorage.from_environment()

    async def event_generator():
        idx = 0
        while True:
            case = storage.read_case_record(tenant.owner_safe, case_id)
            if case is None:
                yield "event: error\ndata: Case not found\n\n"
                break
            events = case.get("progress_events", [])
            while idx < len(events):
                yield f"data: {events[idx]['timestamp']} [{events[idx]['node']}] {events[idx]['message']}\n\n"
                idx += 1
            if case["status"] in ("awaiting_human", "closed", "failed"):
                yield f"event: done\ndata: {case['status']}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{case_id}/report")
async def get_report(case_id: str, tenant: TenantIdentity = Depends(require_tenant)):
    """下载诊断报告"""
    case = _owned_case(case_id, tenant)
    report_path = case.get("report_path")
    if not report_path or not Path(report_path).is_file():
        raise HTTPException(status_code=404, detail="Report not yet available")
    return FileResponse(report_path, media_type="text/markdown", filename=f"{case_id}-report.md")


# ────────────────────────────────────────────────────────────
# 诊断执行
# ────────────────────────────────────────────────────────────

def _owned_case(case_id: str, tenant: TenantIdentity) -> dict:
    # Disk is authoritative because the API and diagnosis worker are separate
    # processes. The in-process dict is only a response cache.
    case = TenantStorage.from_environment().read_case_record(tenant.owner_safe, case_id)
    if case is not None:
        _cases[case_id] = case
    if case is None or case.get("owner_safe") != tenant.owner_safe:
        raise HTTPException(status_code=404, detail="Case not found")
    # Read compatibility for records created before explicit mode routing.
    case.setdefault("mode", str(case.get("source_type") or "unknown"))
    if not case.get("selected_skill"):
        try:
            case["selected_skill"] = validate_mode_params(
                case["mode"], dict(case.get("extra_params") or {})
            ).collection_skill
        except ValueError:
            case["selected_skill"] = "unknown"
    case.setdefault("analysis_skill", "robot-diagnosis")
    return case
