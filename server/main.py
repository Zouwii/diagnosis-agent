"""Diagnosis Agent - FastAPI 入口"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.cases import router as cases_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭"""
    # 启动时
    print(f"[diagnosis-agent] Starting on port {os.getenv('PORT', 5002)}...")
    yield
    # 关闭时
    print("[diagnosis-agent] Shutting down...")


app = FastAPI(
    title="Diagnosis Agent",
    description="技术支持诊断 Agent - 多 Agent 架构",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（允许 management-system 前端调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(cases_router)

# 健康检查
@app.get("/health")
async def health():
    return {"status": "ok", "service": "diagnosis-agent"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5002))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=True)
