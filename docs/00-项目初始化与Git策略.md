# 项目初始化与 Git 策略

> 日期：2026-07-28  
> 项目：diagnosis-agent

---

## 1. 项目定位

diagnosis-agent 是一个**多 Agent 诊断系统**，部署在公司服务器上，供应用工程师使用。

项目包含两类代码：

| 类别 | 内容 | 公开？ |
|---|---|---|
| **通用框架** | LangGraph 编排、LiteLLM 模型路由、FastAPI 服务、状态管理 | ✅ GitHub |
| **公司资产** | Playbook 知识库、错误码关联图、CLI 集成、AGV 领域术语、API 地址 | ❌ 仅公司 GitLab |

---

## 2. Git 双 Remote 策略

### 2.1 两个远端

```
GitHub (个人)                          公司 GitLab
──────────────────────────────        ──────────────────────────────
仓库: github.com/zhr/diagnosis-agent   仓库: gitlab.公司.com/ai/diagnosis-agent
内容: 通用框架                         内容: 完整项目（含领域知识）
用途: 个人项目展示、开源社区            用途: 公司内部使用、部署
```

### 2.2 初始化

```bash
cd diagnosis-agent

# 初始化 Git
git init
git checkout -b main

# 添加个人 GitHub
git remote add origin git@github.com:zhr/diagnosis-agent.git

# 添加公司 GitLab（等地址确定后执行）
# git remote add company git@gitlab.公司.com:ai/diagnosis-agent.git
```

---

## 3. 哪些推哪里

### 3.1 .gitignore

```gitignore
# ── 密钥（永远不推）──
.env
*.key
*.pem

# ── 公司资产（不推 GitHub）──
knowledge/
engine/

# ── 运行时数据（不推任何远端）──
data/cases/
data/stats/

# ── 通用忽略 ──
__pycache__/
*.pyc
.venv/
.env
.DS_Store
```

### 3.2 目录对照

```
diagnosis-agent/
│
├── agent/              → ✅ GitHub + 公司
│   ├── graph.py             LangGraph 编排（通用）
│   ├── state.py             DiagnosisState（通用）
│   └── nodes/               各节点实现（通用）
│
├── models/             → ✅ GitHub + 公司
│   └── router.py            LiteLLM 路由（通用）
│
├── server/             → ✅ GitHub + 公司
│   ├── main.py              FastAPI 入口（通用）
│   └── api/cases.py         Case API（通用）
│
├── knowledge/          → ❌ 仅公司 GitLab
│   ├── correlation_graph.yaml   错误码关联图（AGV 领域）
│   └── playbooks/               Playbook 文档（公司 IP）
│
├── engine/             → ❌ 仅公司 GitLab
│   └── cli_adapter.py          调 jz-claude-skills CLI（公司依赖）
│
├── docs/               → ✅ GitHub（公开文档）+ 公司
│   ├── 00-项目初始化与Git策略.md
│   ├── 01-架构概览.md
│   └── ...
│
├── data/               → ❌ 不推（运行时数据）
│   ├── cases/                 Case 目录
│   └── stats/                 统计文件
│
├── .gitignore
├── .env.example        → ✅ GitHub（占位符模板）
├── requirements.txt    → ✅ GitHub + 公司
└── README.md           → ✅ GitHub + 公司
```

---

## 4. 日常推送流程

### 4.1 开发时：推公司

```bash
git add .
git commit -m "feat: 新增 identify_source 节点实现"
git push company main
```

### 4.2 框架稳定后：推 GitHub

```bash
# GitHub 上已经忽略 knowledge/ engine/，直接推即可
git push origin main
```

### 4.3 或者用分支区分

如果希望 GitHub 和公司仓库结构完全不同：

```bash
# 公司仓库是完整版（main 分支）
git push company main

# GitHub 仓库只有框架（public 分支，剔除敏感目录）
git checkout -b public main
git rm -r knowledge/ engine/ docs/01-*  # 剔除公司资产
git commit -m "strip: remove company assets for public release"
git push origin public
```

---

## 5. 配置文件管理

### 5.1 .env.example（公开）

```bash
# ── 模型 API Key ──
DEEPSEEK_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
ZHIPU_API_KEY=your-key

# ── 默认模型 ──
DEFAULT_MODEL=deepseek/deepseek-chat
STRONG_MODEL=anthropic/claude-sonnet-4-20250514

# ── 数据库 ──
DATABASE_URL=postgresql://user:pass@localhost:5432/diagnosis

# ── 公司服务（部署时填写实际地址）──
RAG_API_URL=http://management-system:5001/api/knowledge/search
ERROR_CODE_API_URL=http://management-system:5001/api/error-codes
CLI_PATH=../jz-claude-skills/scripts/diagnosis_cli.py

# ── 服务端口 ──
PORT=5002
```

### 5.2 .env（不提交）

```bash
# 从 .env.example 复制，填入真实 Key
DEEPSEEK_API_KEY=sk-real-key
ANTHROPIC_API_KEY=sk-ant-real-key
...
```

---

## 6. README 两套内容

### 6.1 GitHub README

面向外部开发者，只讲框架：

```markdown
# Diagnosis Agent

A multi-agent diagnostic system built with LangGraph + LiteLLM + FastAPI.

## Architecture
- LangGraph StateGraph with conditional branching
- Multi-model routing (DeepSeek / Claude / GLM-4)
- SSE progress streaming
- Checkpoint-based resume

## Quick Start
pip install -r requirements.txt
python -m uvicorn server.main:app --port 5002

## Docs
- [Architecture Overview](docs/01-架构概览.md)
```

### 6.2 公司 README

面向公司内部，包含部署和领域知识：

```markdown
# Diagnosis Agent (内部)

AGV 技术支持诊断 Agent。详见 docs/。

## 部署
1. 复制 .env.example → .env，填入真实 Key
2. pip install -r requirements.txt
3. python -m uvicorn server.main:app --port 5002

## 文档
- [Git 策略](docs/00-项目初始化与Git策略.md)
- [架构概览](docs/01-架构概览.md)
- [PRD](../pm-learning/jz-product/05-技术支持诊断Agent-PRD.md)
- [系统架构设计](../pm-learning/jz-product/07-技术支持诊断Agent-系统架构设计.md)
```

---

## 7. 后续文档计划

| 编号 | 文档 | 内容 | 放哪里 |
|---|---|---|---|
| 00 | 项目初始化与 Git 策略 | 本文档 | ✅ 双推 |
| 01 | 架构概览 | 系统全貌 + 技术栈 + 部署架构 | ✅ 双推 |
| 02 | LangGraph 编排设计 | StateGraph 节点 + 条件路由 + Checkpoint | ✅ 双推 |
| 03 | 多模型路由策略 | LiteLLM 配置 + 分层策略 + Fallback | ✅ 双推 |
| 04 | 多 Agent 协作设计 | 融合 vs 仲裁 + 代码文档 Agent + 现场 Agent | ⚠️ 通用部分双推，AGV 示例仅公司 |
| 05 | 开发指南 | 本地运行、添加新节点、测试、调试 | ✅ 双推 |
| 06 | 部署运维指南 | 服务器部署、Nginx、多实例、监控 | ❌ 仅公司 |

---

## 8. 跨仓库依赖与部署

### 8.1 为什么能 import 其他仓库

开发阶段通过 `PYTHONPATH` 环境变量让 Python 找到 jz-claude-skills：

```bash
# 本地开发
export PYTHONPATH=/home/zhr/zhr_ws/src/ai/jz-claude-skills/skills/diagnosis-orchestrator/scripts:$PYTHONPATH
python3 -m uvicorn server.main:app --port 5002
```

部署时 jz-claude-skills 作为依赖目录一同打包到 Docker 镜像，通过 Dockerfile 的 `ENV PYTHONPATH` 设置。

### 8.2 部署架构

```
公司服务器
    │
    ├── /opt/diagnosis-agent/          # LangGraph 编排 + FastAPI
    ├── /opt/jz-claude-skills/         # CLI + Playbook（只读依赖）
    ├── /opt/management-system/        # RAG + 错误码 API（HTTP 调用）
    │
    └── PYTHONPATH 包含:
        /opt/jz-claude-skills/skills/diagnosis-orchestrator/scripts
```

### 8.3 依赖关系

```
diagnosis-agent ──import──▶ jz-claude-skills (CLI 函数, Playbook 文件)
diagnosis-agent ──HTTP───▶ management-system (RAG API, 错误码 API, Auth)
```

jz-claude-skills 对 diagnosis-agent 来说是**只读依赖**——只调它的函数，不改它的代码。
