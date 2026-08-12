---
name: nav-jstate-doc
description: JState 导航错误码知识库查询与处置。当诊断流程中发现 6 位 JState 错误码（614xxx/615xxx/617xxx/619xxx），调用本 Skill 查找对应的 Agent 文档，获取错误结论、日志决策树和可确定性执行的 Playbook，输出诊断结论与处置建议。当目标错误码尚不存在文档时，可生成新文档。Triggers on "错误码" "JState" "614" "615" "617" "619" "错误码查询" "map_parse_error" "offtrack" "qrcode" "perception" "locating" "speed_manager" "carrier_rotater".
author: zhr
---

# Nav JState Doc——导航错误码查询与处置

给定一个 6 位 JState 错误码，从 `source-docs/jstate_error_codes/agent/` 知识库中查找对应文档，读取结论和 Playbook，在日志中执行诊断步骤，给出结论和处置建议。

> 文档不存在时，按第 3 节流程生成新文档。

---

## 1 查询流程

### 1.1 定位文档

```
错误码 → source-docs/jstate_error_codes/agent/{code}-*.md
```

1. 从诊断上下文中提取 6 位数字错误码（如 `614002`、`615001`）。
2. 在 `source-docs/jstate_error_codes/agent/` 中按错误码前缀匹配文件：
   ```bash
   ls source-docs/jstate_error_codes/agent/{code}-*.md
   ```
3. 命中 → 进入 1.2。未命中 → 进入第 3 节"生成新文档"。

### 1.2 读取文档

完整读取命中的 Agent 文档。文档有以下章节（标记 `AUTO-GENERATED`，来自 `nav-navigation-errors/` 的人类文档裁剪）：

| 章节 | 内容 | 动作 |
|---|---|---|
| `## 1 错误结论` | 错误码注册信息、触发条件、影响、清除条件 | 理解错误本质 |
| `## 3 结合日志选择排查方向` | 决策表：按顺序检查项 + 判据 + 下一步 | 在日志中执行每步检查 |
| `## 5 修复验证与证据索引` | YAML 格式的证据状态与验证方法 | 标识当前证据级别 |
| `## 6 Agent 自动排查 Playbook` | YAML 格式的可确定性执行诊断步骤 | 按 Playbook 逐步执行 |

### 1.3 执行 Playbook

Playbook 位于 `## 6 Agent 自动排查 Playbook`，格式为 YAML fenced code block（` ```yaml ... ``` `）。

**执行规则：**

1. 读取 `playbook.meta`：记录 `error_code`、`module`、`time_window`。
2. 按 `steps[].id` 顺序执行。
3. 每个 step 的 `checks[]` 中，对每条 check 执行其 `type` 对应的操作：
   - `grep_log`：在 `/opt/jz/log/{module}.log` 中搜索 `pattern`（正则）。
   - `ros_topic_check`：检查 ROS topic 是否存在/有数据（仅在线模式）。
   - `ros_service_check`：检查 ROS service 是否可用（仅在线模式）。
   - `process_check`：检查进程是否存活（仅在线模式）。
   - `verify_fix`：观察 `watch_duration_sec` 秒内 `grep_pattern` 是否再次出现。
4. 命中 `on_match` → 记录 `conclusion`，按 `goto` 跳转到指定 step。
5. 未命中 `on_no_match` → 按 `goto` 或 `continue: true` 继续。
6. 遇到 `insufficient_data` → 停止，标记 `missing_evidence`，不输出确定性根因。

**输出要求：**

对每个执行的 step，输出：
```
Step [{id}]: {description}
  → 命中: [{check_index}] {on_match.conclusion}
  → 根因: {root_cause}（如有）
  → 临时处置: {temp_fix}（如有）
  → 根因修复: {root_fix}（如有）
```

所有步骤执行完毕后，汇总：
- 错误码、错误名、触发模块
- 触发链（从 Playbook classify 步骤得出）
- 根因结论与证据级别（`已确认`/`高可能`/`待确认`/`已排除`）
- 处置建议（临时 + 根因）
- 缺失证据（如有）

### 1.4 离线降级

Playbook 中标记 `online_only: true` 的原语仅在机器人可直接访问时执行。离线分析时：
- `ros_topic_check`、`ros_service_check`、`process_check` → 标记为 `skip_if_offline`，改用日志中间接证据替代。
- 所有 `grep_log` 原语始终可用，使用本地日志文件路径。

---

## 2 多错误码关联

当同一次诊断中出现多个错误码时：

1. 先按时间顺序排列错误码。
2. 逐个查询每个错误码的 `## 1 错误结论`，提取触发模块和直接影响。
3. 判断因果关系：上游模块的错误可能是下游错误的根因。
4. 从最早出现的错误码开始执行 Playbook，后续错误码视为级联影响。
5. 输出时列出错误码因果链，标注每个错误码的分析状态。

---

## 3 生成新文档

当目标错误码在 `agent/` 目录中没有对应文档时，启用文档生成模式。

### 3.1 定位注册表

按优先级搜索错误码注册表：
1. `source-docs/jstate_error_codes/机型3代状态数据-META大全.xlsx`
2. 工作区内文件名包含 `META`、`错误码`、`状态数据` 的 xlsx 文件。

用脚本提取注册信息：
```bash
python3 skills/nav-jstate-doc/scripts/find_error_code_in_xlsx.py \
  source-docs/jstate_error_codes/机型3代状态数据-META大全.xlsx \
  {错误码} [--sheet {sheet名}]
```

### 3.2 按模板生成

1. 完整阅读 `references/document-spec.md`。
2. 以 `assets/error-code-analysis-template.md` 为模板。
3. 在 `source-docs/jstate_error_codes/nav-navigation-errors/` 下创建 `{code}-{name}.md`。
4. 生成后运行脚本同步 Agent 视图：
   ```bash
   cd source-docs/jstate_error_codes && python3 generate_agent_docs.py
   ```
5. 生成完成后回到第 1 节查询流程。

### 3.3 生成约束

- 必须从注册表确认识别误差码数值、名称、等级和模块。
- 必须从源码确认真实置位条件（使用 `rg` 搜索）。
- Playbook 中每条 `grep_log` 的 `pattern` 必须是真实可执行的正则，不含概念性描述。
- 缺失源码时标记 `evidence_boundary: true`，不输出确定性根因。

---

## 4 与 diagnosis-orchestrator 协作

本 Skill 是 `diagnosis-orchestrator` 的知识层子技能，调用关系：

```
diagnosis-orchestrator（流程控制）
  ├── 发现 JState 错误码 → 委托 nav-jstate-doc
  │     ├── 查询 agent/{code}-*.md
  │     ├── 执行 Playbook
  │     └── 返回结论 + 处置
  └── 继续主诊断流程
```

输出格式兼容 `diagnosis-orchestrator` 的报告模板，使用统一的证据状态标签：`已确认`、`高可能`、`待确认`、`已排除`。
