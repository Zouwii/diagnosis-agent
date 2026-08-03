"""Diagnosis Agent - FastAPI 入口"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from server.api.cases import router as cases_router


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭"""
    port = int(os.getenv("PORT", "6001"))
    if port < 6001:
        raise RuntimeError("Diagnosis Agent ports must start at 6001")
    if os.getenv("DIAGNOSIS_ENV", "development").strip().lower() == "production":
        if not os.getenv("DIAGNOSIS_STORAGE_ROOT", "").strip():
            raise RuntimeError("DIAGNOSIS_STORAGE_ROOT is required in production")
        if os.getenv("DIAGNOSIS_ALLOW_ANONYMOUS", "").strip().lower() in {"1", "true", "yes", "on"}:
            raise RuntimeError("anonymous access must be disabled in production")
    # 启动时
    print(f"[diagnosis-agent] Starting on port {port}...")
    yield
    # 关闭时
    print("[diagnosis-agent] Shutting down...")


app = FastAPI(
    title="Diagnosis Agent",
    description="技术支持诊断 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（只允许显式配置的 management-system 来源携带登录 Cookie）
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "DIAGNOSIS_CORS_ORIGINS",
        "http://127.0.0.1:5002,http://localhost:5002",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(cases_router)

# 健康检查
@app.get("/", include_in_schema=False)
async def web_ui():
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "diagnosis-agent"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 6001))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)
