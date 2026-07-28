"""Case API - 诊断 Case 的创建、查询、进度推送"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/cases", tags=["cases"])

# ────────────────────────────────────────────────────────────
# 内存存储（后续迁移到 Postgres）
# ────────────────────────────────────────────────────────────

_cases: dict[str, dict] = {}


# ────────────────────────────────────────────────────────────
# 请求/响应模型
# ────────────────────────────────────────────────────────────

class CreateCaseRequest(BaseModel):
    source_type: Literal["auto", "internal_robot", "tb_task", "remote_site", "local_logs"] = "auto"
    # 按来源二选一
    robot_ip: str | None = Field(None, description="内网机器人 IP，如 172.22.0.222")
    task_url: str | None = Field(None, description="TB 任务链接")
    frp_port: int | None = Field(None, description="远程现场 frp 端口")
    site_robot_ip: str | None = Field(None, description="现场机器人 IP")
    log_path: str | None = Field(None, description="本地日志路径")
    # 通用
    symptom: str = Field(..., description="问题现象，如 '到点后旋转3圈停止'")
    time_window: str | None = Field(None, description="问题时间，如 '2026-07-27 20:00'")
    knowledge_sources: list[str] = Field(default_factory=list)
    code_sources: list[str] = Field(default_factory=list)


class CaseResponse(BaseModel):
    case_id: str
    status: Literal["pending", "collecting", "analyzing", "awaiting_human", "closed", "failed"]
    source_type: str
    symptom: str
    conclusion_status: str | None
    report_url: str | None
    created_at: str
    updated_at: str


class CaseProgressEvent(BaseModel):
    event: str          # "node_start" | "node_complete" | "retry" | "fallback" | "error"
    node: str           # 当前节点名
    message: str        # 人可读的进度描述
    timestamp: str


# ────────────────────────────────────────────────────────────
# API 路由
# ────────────────────────────────────────────────────────────

@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(req: CreateCaseRequest, background: BackgroundTasks):
    """创建诊断 Case，异步启动诊断流程"""
    case_id = f"case-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    _cases[case_id] = {
        "case_id": case_id,
        "status": "pending",
        "source_type": req.source_type,
        "symptom": req.symptom,
        "extra_params": {
            "robot_ip": req.robot_ip,
            "task_url": req.task_url,
            "frp_port": req.frp_port,
            "site_robot_ip": req.site_robot_ip,
            "log_path": req.log_path,
            "time_window": req.time_window,
            "knowledge_sources": req.knowledge_sources,
            "code_sources": req.code_sources,
        },
        "conclusion_status": None,
        "report_url": None,
        "created_at": now,
        "updated_at": now,
        "progress_events": [],
        "error": None,
    }

    # 异步启动诊断
    background.add_task(_run_diagnosis, case_id, req)

    return CaseResponse(**_cases[case_id])


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str):
    """查询 Case 状态"""
    case = _cases.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse(**case)


@router.get("/{case_id}/stream")
async def stream_progress(case_id: str):
    """SSE 推送诊断进度"""
    case = _cases.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    async def event_generator():
        idx = 0
        while True:
            events = case.get("progress_events", [])
            while idx < len(events):
                yield f"data: {events[idx]['timestamp']} [{events[idx]['node']}] {events[idx]['message']}\n\n"
                idx += 1
            if case["status"] in ("closed", "failed"):
                yield f"event: done\ndata: {case['status']}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{case_id}/report")
async def get_report(case_id: str):
    """下载诊断报告"""
    case = _cases.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.get("report_url"):
        raise HTTPException(status_code=404, detail="Report not yet available")
    # TODO: 返回报告文件内容
    return {"case_id": case_id, "report_url": case["report_url"]}


# ────────────────────────────────────────────────────────────
# 诊断执行（占位，后续接入 LangGraph）
# ────────────────────────────────────────────────────────────

async def _run_diagnosis(case_id: str, req: CreateCaseRequest):
    """在后台执行 LangGraph 诊断流程"""
    case = _cases[case_id]
    try:
        _update_status(case, "collecting", f"开始诊断: {req.symptom}")
        _add_progress(case, "identify_source", "识别输入来源...")
        await asyncio.sleep(1)

        _update_status(case, "analyzing")
        _add_progress(case, "collect_data", "采集数据...")
        await asyncio.sleep(1)

        _add_progress(case, "classify_and_scan", "分析日志...")
        await asyncio.sleep(1)

        # TODO: 接入 LangGraph app.ainvoke()
        # from agent.graph import app
        # config = {"configurable": {"thread_id": case_id}}
        # result = await app.ainvoke({"user_input": req.symptom, ...}, config)

        _update_status(case, "closed", "诊断完成")
        case["conclusion_status"] = "likely"
        case["report_url"] = f"/data/cases/{case_id}/report.md"

    except Exception as e:
        _update_status(case, "failed", str(e))
        case["error"] = str(e)


def _update_status(case: dict, status: str, message: str = ""):
    case["status"] = status
    case["updated_at"] = datetime.now(timezone.utc).isoformat()
    if message:
        _add_progress(case, status, message)


def _add_progress(case: dict, node: str, message: str):
    case["progress_events"].append({
        "event": "node_complete",
        "node": node,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
