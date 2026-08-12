# Diagnosis Agent

Diagnosis Agent 是运行在 `6001` 端口的 LangGraph 诊断工作流服务。

一期主题是：**诊断流程结构化与可控化**。

一期不重写全部诊断推理，也不建设多个 Agent 自由协作，集中完成三件事：

1. 建立原 orchestrator 的兼容基线；
2. 将完整流程拆成可观察、可测试、可恢复的节点；
3. 为后续独立工作流准备统一的 Case、证据和安全契约。

## 两个运行版本

| version | 定位 | 当前图结构 |
|---|---|---|
| `origin-v1` | 兼容基线 | `START → diagnosis_cli → END` |
| `graph-v1` | LangGraph 迭代主线 | `START → collect → analyze → report → END` |

`origin-v1` 通过单节点运行迁移后的 Python orchestrator/Engine，用于冻结原流程语义。
它不是 Claude CLI 或 ttyd 运行时。

`graph-v1` 将同一诊断能力拆为独立节点。后续的条件路由、材料门禁、人工中断、
持久化恢复和证据归并只进入 `graph-v1`。

## 架构

```text
Web / API :6001
      │
      ▼
FastAPI Case API
      │ 写入持久化 Case
      ▼
File Queue Worker
      │
      ▼
LangGraph
  ├─ origin-v1：兼容基线
  └─ graph-v1：结构化工作流
      │
      ▼
Engine
  ├─ collectors：四类材料采集
  ├─ analysis：日志、时间窗、Playbook 与证据分析
  └─ reporting：报告与人工交接材料
```

## 四种入口

| mode | 必要输入 |
|---|---|
| `internal_robot` | `robot_ip` |
| `tb_task` | `task_url` |
| `remote_site` | `frp_port`、`site_robot_ip` |
| `local_logs` | `upload_id` 或当前租户允许目录内的 `log_path` |

入口由固定白名单校验，客户端不能传任意 Skill、命令或本地路径。

## Case 契约

每个 Case 按租户隔离，保存请求、状态、材料清单、事件、报告和中间结果。浏览器断开不
终止 Worker。报告和本地材料路径必须位于当前租户 Case 或允许的上传/工作区边界内。

## 启动

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --port 6001 --reload

# 另一个终端
python -m server.worker
```

浏览器访问 `http://127.0.0.1:6001/`。

## 测试

```bash
pytest -q
```

重点测试包括：版本图拓扑、四类入口、租户隔离、Case/Worker 生命周期，以及
`origin-v1` 与 `graph-v1` 的冻结 Case 一致性。

## 目录

```text
agent/          LangGraph State、图与节点
engine/         与框架无关的采集、分析、报告和兼容工作流
server/         FastAPI、Case、身份认证与 Worker
knowledge/      Playbook 运行时加载
source-docs/    错误码和现场高频问题知识
templates/      报告、交接和知识草稿模板
tests/          自动化测试与兼容性回放
legacy/         不属于 6001 主线的历史实现
```

## 边界

- 6001 不启动或托管 Claude CLI/ttyd。
- 不保留 `claude-origin-v1`、`origin-split` 等重复运行版本。
- 不建设多 Agent fan-out、辩论或仲裁。
- 5433 ttyd 历史实现仅保存在 `legacy/ttyd-5433/` 供参考。
- 原始知识和 Engine 保留，graph-v1 在其上做结构化编排，而不是重新实现所有诊断逻辑。

详细设计见 [LangGraph V1 架构设计](docs/04-Agent-Harness架构演进设计.md)。
