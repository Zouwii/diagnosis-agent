# LangGraph V1 架构设计

## 1. 一期产品目标

一期主题定义为：**诊断流程结构化与可控化**。

一期不追求重写全部 Claude 推理，也不建设多个 Agent 自由协作。它完成三件事：

1. 建立原 orchestrator 的兼容基线；
2. 将完整流程拆成可观察、可测试、可恢复的节点；
3. 为后续独立工作流准备统一的 Case、证据和安全契约。

## 2. 为什么使用 LangGraph

普通顺序 Python 可以完成 `collect → analyze → report`，但不能充分解决材料门禁、条件路由、
人工补充、持久化恢复和执行轨迹问题。LangGraph 的价值是让这些控制流成为显式、可测试的
业务结构，而不是隐藏在模型对话或异常处理里。

## 3. 双版本策略

`origin-v1` 是单节点兼容基线；`graph-v1` 是唯一演进版本。两者复用相同 Engine，通过冻结
Case 回放验证拆分没有改变诊断语义。

不再保留 Claude CLI 运行时和中间过渡版本。

## 4. 稳定契约

### Case

Case 记录租户、来源、请求、状态、材料、事件、版本和报告。它是 API、Worker、Graph 和
前端共同使用的业务契约。

### Material Manifest

采集节点统一输出：

```json
{
  "collected": true,
  "source": "local_logs",
  "case_dir": "...",
  "raw_dir": "...",
  "extracted_dir": "...",
  "artifacts": [],
  "warnings": [],
  "metadata": {}
}
```

### Evidence Ledger

后续节点产出的每条证据至少包含：`evidence_id`、来源文件、位置、摘要、提取节点、可信度和
关联假设。账本只追加，报告必须能由 evidence ID 回查材料。

### Conclusion

结论状态统一为：`confirmed`、`likely`、`need_human`、`insufficient_data`。材料不足和执行
故障必须分开，禁止把采集失败包装成诊断根因。

## 5. graph-v1 演进顺序

1. 保持当前 `collect → analyze → report` 通过兼容测试；
2. 增加 `material_gate` 条件边；
3. 增加持久化 checkpointer；
4. 用 `interrupt/resume` 实现人工补充；
5. 拆分 `signal_scan`、`diagnosis_route` 和两类分析路线；
6. 增加 `evidence_reduce` 与证据账本；
7. 增加节点级耗时、重试、错误和回放指标。

## 6. 验收

- 相同冻结 Case 下，origin-v1 与 graph-v1 的材料、结论和报告语义一致；
- 四种来源只采集一次，恢复后不重复执行已完成的副作用节点；
- 材料不足进入人工补充，不生成确定性根因；
- Case 和 checkpoint 在进程重启后可以恢复；
- 每个节点可独立单测，关键条件边有参数化覆盖；
- 所有报告结论都能回查证据与工具轨迹。
