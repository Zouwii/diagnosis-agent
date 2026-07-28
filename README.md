# Diagnosis Agent

技术支持诊断 Agent — 多 Agent 架构，部署在公司服务器上，供所有应用工程师使用。

## 架构

```
FastAPI (server/)  →  LangGraph (agent/)  →  diagnosis_cli.py (jz-claude-skills)
                          │
                    ┌─────┴─────┐
                    │ LiteLLM    │  LangSmith
                    │ 模型路由   │  可观测性
                    └───────────┘
```

## 目录结构

```
diagnosis-agent/
├── server/                FastAPI 服务
│   ├── main.py            入口 (端口 5002)
│   └── api/cases.py       Case CRUD + SSE 进度推送
├── agent/                 LangGraph 编排
│   ├── graph.py           StateGraph 定义 (条件分叉)
│   ├── state.py           DiagnosisState TypedDict
│   └── nodes/             各节点实现 (逐步实现)
├── models/
│   └── router.py          LiteLLM 模型路由层
├── engine/                CLI 集成 (调 jz-claude-skills)
├── knowledge/             领域知识 (Playbook + 关联图)
├── data/                  运行时数据
│   ├── cases/             Case 目录
│   └── stats/             闭环统计
└── requirements.txt
```

## 启动

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --port 5002 --reload
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/cases | 创建诊断 Case |
| GET  | /api/cases/{id} | 查询 Case 状态 |
| GET  | /api/cases/{id}/stream | SSE 进度推送 |
| GET  | /api/cases/{id}/report | 下载诊断报告 |
| GET  | /health | 健康检查 |

## 文档

- PRD: [../pm-learning/jz-product/05-技术支持诊断Agent-PRD.md](../pm-learning/jz-product/05-技术支持诊断Agent-PRD.md)
- 系统架构: [../pm-learning/jz-product/07-技术支持诊断Agent-系统架构设计.md](../pm-learning/jz-product/07-技术支持诊断Agent-系统架构设计.md)
