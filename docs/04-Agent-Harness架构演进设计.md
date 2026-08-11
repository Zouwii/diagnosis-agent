# Agent Harness 架构演进设计

> 日期：2026-08-04  
> 状态：设计待评审；本文不代表已实现能力。

---

## 1. 决策与目标

`origin-v1` 是 Diagnosis-Agent 的兼容基线：一次性调用完整 `diagnosis_cli`，复刻原始
orchestrator。`origin-split` 将同一流程拆成可测试节点。本文只描述 `graph-v1` 后续
如何在不改变前两个版本语义的前提下，引入证据路线、并行比较和人工接管。

后续不替换 Engine，也不让多个 LLM 自由协作。目标是把 Engine 作为受控工具集合，由 LangGraph 作为 Case 状态机，并以 Harness 统一约束路线、证据、预算、恢复和人工交接。

```text
API / Worker
    ↓
LangGraph Case Harness
    ├── 路由与状态恢复
    ├── 路线预算、工具权限、审计
    └── 证据汇合与人工接管
    ↓
Engine Tools
    ├── collect_materials
    ├── scan_signals
    ├── run_error_code_route
    ├── run_diagnosis_route
    ├── enrich_external_evidence
    └── render_report
```

## 2. 不变的边界

- 一个 Case 只选择一种采集来源；采集只能执行一次，后续路线复用同一份 Case 材料。
- 采集、日志扫描、Playbook 执行、外部检索和报告渲染继续由项目内 Python Engine 执行，不依赖 Claude Skill 运行时。
- LLM（若后续接入）只能从服务端登记的路线和工具中选择；不能生成任意 shell 命令、任意 URL 或新的路线名。
- 自动化只允许读取材料、分析和生成报告。远程写入、现场操作或风险动作必须停在 `awaiting_human` 并由人工确认。
- 所有结论必须关联可访问的证据引用；没有充分证据时输出缺失材料或人工交接，而不是猜测根因。

## 3. 分期图结构

### Phase A：graph-v1 演进基线

```text
START → run_graph_v1_case → END
```

`graph-v1` 的演进不改变 `origin-v1` 和 `origin-split`；两个兼容版本继续分别保留
完整入口和拆分入口的回归验证。

### Phase B：错误码路线

```text
START → collect → signal_scan
                         ├─ error_code_route → evidence_reduce → report
                         └─ insufficient_data → report / awaiting_human
```

`signal_scan` 仅抽取与归档信号：错误码、问题描述关键词、材料完整性、日志时间范围和初步问题类型。它不做路线结论。

当存在可信错误码时，`error_code_route` 执行对应 Playbook、相关日志窗口与必要的外部证据补充。错误码未命中或证据不足不能伪装为已确认结论。

### Phase C：无错误码多路线

```text
START → collect → signal_scan
                         ├─ error_code_route ─┐
                         └─ no_code_router ───┼→ evidence_reduce → decision → report
                              ├─ navigation   │
                              ├─ task_chain   │
                              ├─ safety       │
                              └─ device_sensor│
```

`no_code_router` 从固定注册表中选择零到两条候选路线。第一版使用症状、日志文件存在性和确定性信号评分；后续若引入 LLM，只允许它在同一注册表中排序和说明理由。

路线 Worker 的第一版是普通 Python 函数，不必先实现为 LLM Agent。只有某条路线确实需要不确定性处理、追问或工具选择时，才为它增加 LLM 节点。

## 4. 稳定数据契约

### 4.1 RouteResult

每一条路线必须返回同一种结构，供汇合节点比较，而不是直接写最终报告：

```python
RouteResult(
    route="navigation",
    status="completed",  # completed | insufficient | failed | awaiting_human
    findings=[...],
    evidence_refs=[...],
    confidence=0.0,
    missing_evidence=[...],
    tool_trace=[...],
)
```

`evidence_refs` 至少包含来源类型、Case 内相对路径或外部文档标识、定位信息（日志行号或时间窗）和摘录。`confidence` 是路线的证据充分度，不是模型自我评价。

### 4.2 Evidence Ledger

Case 内增加只追加的证据账本。采集、规则分析、外部检索和路线 Worker 都向账本写入证据；`evidence_reduce` 负责去重、检测矛盾和关联路线结果。

最终结论只能引用账本中的证据 ID。这样报告、SSE、回放评测和人工交接读取的是同一事实来源。

### 4.3 Case 状态

LangGraph State 只保存运行所需的结构化摘要和节点结果；Case 文件保存可恢复的事实状态。建议新增：

- `signal_summary`：错误码、材料完整性、候选路线和路由理由；
- `route_results`：按路线名保存的 `RouteResult`；
- `evidence_ledger_path`：证据账本位置；
- `execution_budget`：路线和工具的剩余预算；
- `pending_human_action`：需要人工补充或确认的明确动作。

## 5. Harness 最小职责

Harness 的第一版必须实现以下控制面，而不是只增加 Graph 节点：

| 能力 | 规则 |
|---|---|
| 路线注册 | 路线名、允许工具、最大执行时间和最大外部查询数由服务端固定配置。 |
| 预算 | 单条路线有工具调用和时间上限；预算耗尽返回 `insufficient`，不无限重试。 |
| 幂等与恢复 | 节点输出持久化；重启时跳过已完成且输入未变化的节点。 |
| 工具权限 | 采集器、外部搜索和未来 LLM 工具均通过统一封装调用；禁止节点自行执行任意命令。 |
| 审计 | 每次工具调用记录输入摘要、输出位置、耗时、结果和错误类别，不记录凭据。 |
| 人工接管 | 缺材料、证据冲突、预算耗尽或风险操作都生成明确交接项。 |

## 6. Evidence Reduce 与 Decision

初版不需要 LLM Judge。使用确定性规则：

- 强证据且不存在同级矛盾证据：`confirmed`；
- 有明确方向但证据未闭环：`likely`；
- 多路线冲突、缺少关键材料或需要风险操作：`awaiting_human`；
- 未获取到有效信号：`insufficient_data`。

后续 LLM 可以帮助解释不同证据的关系，但不能绕过上述状态和证据要求。

## 7. 首批无错误码路线

首批只实现高频且材料边界清晰的两条路线：

1. `navigation`：导航、定位、旋转、速度约束相关日志与时间线；
2. `task_chain`：任务下发、行为树、状态机与调度链路。

`safety` 与 `device_sensor` 在前两条路线经真实 Case 验证后再加入。这样可以避免初期全量 fan-out，也能形成路线级可比较的 Case 样本。

## 8. 验收原则

每一阶段至少准备：一条成功 Case、一条材料不足或冲突的失败 Case。验收至少记录：

- 采集是否只执行一次；
- 错误码 / 无错误码分支选择是否符合预期；
- 每条路线是否输出可追溯证据；
- 是否在预算、缺材料和冲突时正确转人工；
- 路线完成时间、工具调用数和人工介入率。

在缺少上述真实 Case 前，不宣称多 Agent 路线已有效。
