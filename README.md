# Diagnosis Agent

技术支持诊断 Agent，部署在公司服务器上，供所有应用工程师使用。

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
│   ├── main.py            API 入口（Agent 端口从 6001 开始）
│   ├── worker.py          独立文件队列 Worker（不占端口）
│   └── api/cases.py       Case CRUD + SSE 进度推送
├── agent/                 LangGraph 编排
│   ├── graph.py           薄 StateGraph（当前直接执行完整 CLI Engine）
│   ├── state.py           DiagnosisState TypedDict
│   └── nodes/             各节点实现 (逐步实现)
├── models/
│   └── router.py          LiteLLM 模型路由层
├── engine/                CLI 集成 (调 jz-claude-skills)
├── knowledge/             领域知识 (Playbook + 关联图)
├── data/                  开发环境运行时数据
│   ├── tenants/{owner}/   租户隔离的 uploads/ 和 cases/
│   └── stats/             闭环统计
└── requirements.txt
```

## 启动

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --port 6001 --reload
# 另开一个终端
python -m server.worker
```

API 创建 Case 后只写入持久化队列并立即返回；Worker 独立执行完整 CLI
Engine。SSE 只负责读取持久化 Case 进度，浏览器断开不会中止诊断。

### 独立 Web 页面

Diagnosis Agent 自带一个无前端构建步骤的简单页面：

```text
http://<server>:6001/
```

页面支持四种模式、日志上传、SSE 进度和 Markdown 报告查看。页面与 API
同源，不依赖 management-system 的前端代码。当前仍复用 management-system
登录身份：同一主机不同端口访问时浏览器会携带同一域名下的 Session Cookie，
Diagnosis Agent 再通过 `MANAGEMENT_SYSTEM_URL` 校验用户并完成租户隔离。

### 一键部署

默认部署到 `jz@172.19.3.79:/home/jz/zhr/diagnosis-agent`，API 使用
`6001`，Worker 不监听端口：

```bash
bash onekey-deploy.sh
```

首次部署推荐显式传 SSH 密码，或者预先配置 SSH Key：

```bash
DIAGNOSIS_DEPLOY_PASSWORD='<password>' bash onekey-deploy.sh
```

服务器进程管理：

```bash
bash run_on_pc_daemon.sh install
bash run_on_pc_daemon.sh start
bash run_on_pc_daemon.sh status
bash run_on_pc_daemon.sh logs
bash run_on_pc_daemon.sh restart
```

端口约定：Diagnosis API 使用 `6001`，后续 Agent 服务从 `6002` 继续分配；
脚本和生产启动检查都会拒绝小于 `6001` 的端口。

生产环境将 `DIAGNOSIS_STORAGE_ROOT` 指向持久化卷（例如
`/var/lib/diagnosis-agent`），并通过 management-system Session 或内部签名 Header
传递用户身份。默认不允许匿名访问。

### 多租户文件布局

```text
${DIAGNOSIS_STORAGE_ROOT}/
└── tenants/
    └── {sha256(owner_key)[:24]}/
        ├── uploads/                 # 该租户可导入的本地材料边界
        └── cases/
            └── {case_id}/
                ├── case.json       # Case 归属和状态，原子替换
                ├── collection.json
                ├── events.jsonl
                ├── raw/            # TB 附件、SSH 日志、远程材料
                ├── extracted/      # 解压后材料
                └── report.md
```

owner hash 算法与 management-system 的 `runtime/users/{owner_safe}` 一致，但诊断文件
使用独立持久化根目录。Case 查询、SSE 和报告下载都会校验 `owner_safe`；
`local_logs` 只能读取当前租户 `uploads/` 或配置的 management-system 当前用户工作区。
上传接口只是跨机器提交材料的可选方式，不是本地日志模式的必经步骤。

### 四种入口模式

Web 请求必须明确传 `mode`。服务端使用固定白名单映射，不由 LLM 猜来源，也不接受
客户端传任意 Skill 名称：

| mode | 采集 Skill 语义 | 后续分析 |
|---|---|---|
| `internal_robot` | `robot-peek` | `robot-diagnosis` |
| `tb_task` | `teambition` | `robot-diagnosis` |
| `remote_site` | `remote-hand` | `robot-diagnosis` |
| `local_logs` | `robot-diagnosis` 离线入口 | `robot-diagnosis` |

也就是说，它们是四种用户选择的诊断模式，但不是四个互不相关的分析 Skill。
当前后端直接调用从这些 Skills 迁移出的采集实现，并在 Case 中记录
`selected_skill` 和 `analysis_skill`，随后统一进入诊断图。

当前诊断图保持单一路径：

```text
START → run_cli_workflow → END
```

`run_cli_workflow` 直接复用从 `diagnosis-orchestrator` 拆分迁移的完整模块化
CLI Engine：采集、确定性日志分析、时间窗处理、外部证据补充和报告渲染。
后续只在它之后增加 `analysis_agent` 和 `fusion_agent`，不会恢复来源识别、
双 Agent 仲裁或多路 fan-out。

身份有两种可信来源：

- 浏览器携带 management-system Session Cookie，Diagnosis Agent 回调
  `${MANAGEMENT_SYSTEM_URL}/api/bt/auth/me` 验证。
- management-system 服务端代理请求，同时传递 `X-Diagnosis-User-Id` 和
  `X-Diagnosis-Internal-Token`；后者必须与 `DIAGNOSIS_INTERNAL_TOKEN` 一致。

不会从请求 body 中接受 `ownerKey/user_id`，避免客户端伪造其他租户身份。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/cases/uploads | 上传当前租户的本地日志，返回 `upload_id` |
| POST | /api/cases | 创建诊断 Case |
| GET  | /api/cases/{id} | 查询 Case 状态 |
| GET  | /api/cases/{id}/stream | SSE 进度推送 |
| GET  | /api/cases/{id}/report | 下载诊断报告 |
| GET  | /health | 健康检查 |

创建内网机器人诊断 Case：

```json
{
  "mode": "internal_robot",
  "robot_ip": "172.22.0.222",
  "symptom": "到点后旋转3圈停止"
}
```

`local_logs` 可直接传当前用户工作区内的 `log_path`；如果文件来自浏览器本机，先调用
`POST /api/cases/uploads`，再把返回的 `upload_id` 传给创建 Case 接口。

## 文档

- PRD: [../pm-learning/jz-product/05-技术支持诊断Agent-PRD.md](../pm-learning/jz-product/05-技术支持诊断Agent-PRD.md)
- 系统架构: [../pm-learning/jz-product/07-技术支持诊断Agent-系统架构设计.md](../pm-learning/jz-product/07-技术支持诊断Agent-系统架构设计.md)
