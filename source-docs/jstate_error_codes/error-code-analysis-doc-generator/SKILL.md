---
name: error-code-analysis-doc-generator
description: Generate or update evidence-based Markdown troubleshooting documents for one or more error codes by correlating error registries (XLSX/CSV/YAML/JSON/Markdown), source-code trigger and recovery paths, runtime logs, versions, and fixes. Each document includes a structured Agent Playbook (Chapter 6) that the diagnosis-orchestrator's deterministic analyzer can execute automatically — grep logs, check ROS topics/services, compare values against thresholds, and follow decision branches. Use when Codex needs to梳理错误码、从错误名反查错误码、生成错误码知识库或模板、记录完整功能流程、设计日志排查决策树、沉淀原因与解决方案，或制作可供 AI Agent 读取日志后逐步深入代码排障的文档。
---

# Error Code Analysis Doc Generator

## 1 核心原则

生成”可执行的排障知识”，而不是错误名称释义。**文档同时服务两类消费者：人类工程师（第 1-5 章）和诊断 Agent（第 6 章 Playbook）。**

- 以错误码注册表确认数值码、名称、描述、等级和所属模块。
- 以源码确认真实的置位条件、调用链、影响路径、恢复条件和上报机制。
- 以现场日志确认本次事件命中了哪个分支；没有日志时只描述可证明的机制。
- 区分`已确认`、`高可能`、`待确认`、`已排除`，禁止把推测写成事实。
- 区分临时处置、根因修复和修复验证；”重启后消失”不等于闭环。
- **Playbook 的每一步必须可被 diagnosis-orchestrator 的确定性分析器自动执行。**
- 默认只生成或更新文档并执行只读检查；不要修改业务代码、机器人或线上状态，除非用户明确要求。

开始工作前完整读取 [references/document-spec.md](references/document-spec.md)。创建文档时复制并裁剪 [assets/error-code-analysis-template.md](assets/error-code-analysis-template.md)，不要重新发明章节结构。

## 2 输入与输出

接受以下输入的任意组合：

- 一个或多个错误码、错误名、JState key 或日志片段；
- XLSX、CSV、YAML、JSON、Markdown 等错误码注册表；
- 相关模块源码、构建清单、版本或提交号；
- 现场日志、状态消息、配置、topic 或进程信息；
- 用户指定的现有模板或输出目录。

默认每个错误码生成一个 Markdown 文件，命名为`{错误码}-{稳定英文名}.md`。优先写入用户指定目录；未指定时，沿用仓库现有错误码文档目录，仍不存在时使用`docs/error_codes/`。批量生成时逐码独立取证，不因编号相邻而推断实现相同。

注册表按以下优先级解析，命中后记录实际路径，不要假设文件仍在旧位置：

1. 用户本次明确指定的文件；
2. 目标文档同目录及当前模块的`docs/jstate_error_codes/`、`docs/error_codes/`；
3. Skill 自身`references/`或`assets/`下的注册表；
4. 当前工作区内文件名包含`META`、`错误码`、`状态数据`的候选文件。

若找到多个候选，按目标模块、机型和版本消歧；无法消歧时不得自行任选。

## 3 执行流程

### 3.1 确认注册信息

1. 按第 2 章的优先级定位注册表；优先使用与目标模块文档一起版本管理的 META 文件。
2. 对工作区候选先执行：

```bash
rg --files | rg '(META|错误码|状态数据).*\.xlsx$'
```

3. 定位用户指定的 sheet；未指定 sheet 时搜索全部 sheet。
4. 精确匹配错误码或错误名，保留文件、sheet、行号和字段值。
5. XLSX 优先运行：

```bash
python3 <skill目录>/scripts/find_error_code_in_xlsx.py <workbook.xlsx> <错误码或错误名> [--sheet <sheet名>]
```

6. 若同一编号存在多条记录，先按机型、版本和模块收敛适用项；无法消歧时在文档中明确歧义。
7. 注册表没有结果时不要臆造数值映射，记录`missing_evidence`并继续搜索源码常量、接口定义和历史文档。

### 3.2 建立源码证据链

使用`rg`按以下顺序搜索并阅读上下文：

1. 数值码、错误名、key、枚举和描述；
2. 所有置位、发布、抛出或返回该错误的路径；
3. 所有清除、恢复、重试或超时路径；
4. 直接调用者、上游输入生产者和下游影响；
5. 版本历史、接口协议和相关错误码。

至少回答：

- 什么业务入口会进入该流程？
- 哪个最小条件直接触发错误？
- 错误发生在功能流程的哪个阶段？
- 当前动作、任务和安全策略受到什么影响？
- 状态如何上报、保持、清除或自动恢复？
- 哪些底层实现不在当前仓库，因而仍是证据边界？

源码缺失时先搜索当前工作区和仓库依赖线索。仍无法取得时，明确“当前只能确认到的最深边界”，不要把模块名当根因。

### 3.3 构造日志决策树

围绕调用链列出可观测信号，按“低成本、高区分度、接近触发点”的顺序安排检查。每一步必须包含：

- 检查项；
- 正常判据；
- 异常判据；
- 命中后的结论状态；
- 下一步或停止条件。

先校验时间窗、进程实例和版本，再检查直接触发日志、发生阶段、输入、依赖和底层分支。命中首个异常生产者后沿该链继续追因，不要让 Agent 无条件执行所有命令。

只给出现场环境可用且默认只读的命令。命令中使用明确日志路径或占位符，并解释期望观察结果。

### 3.4 形成解决与验证闭环

每个候选原因写出可区分的唯一特征、负责链路、临时处置、根因修复和验证方法。优先级应来自触发距离、现场概率和风险，而不是凭空排序。

验证至少覆盖：

- 错误状态按设计清除且不反复置位；
- 直接触发日志不再出现；
- 原功能流程恢复；
- 上游输入和依赖持续正常；
- 相同场景重复执行不再复现。

### 3.5 写入前五章并自检

使用**六章结构**（前五章供人类阅读，第六章供 Agent 执行）：

1. 错误结论
2. 错误触发的功能流程
3. 结合日志选择排查方向
4. 可能原因与解决方案
5. 修复验证与证据索引
6. Agent 自动排查 Playbook（见 3.6）

所有 Markdown 标题使用编号层级；仅文档主标题不编号。保留必要的 Mermaid、表格、命令和结构化 YAML，删除不能帮助诊断的重复说明。

完成后逐项检查 [references/document-spec.md](references/document-spec.md) 的验收清单，并检查：

```bash
rg -n '^#{2,6} ' <输出文档>
rg -n 'TODO|待补充|TBD|PLACEHOLDER' <输出文档>
```

若用户要求”输出文档”，必须实际创建或更新文件，而不只在对话中给出草稿。

### 3.6 生成 Agent 自动排查 Playbook

Playbook 是第六章，让 diagnosis-orchestrator 的确定性分析器可以**不调模型、纯规则执行**排查步骤。格式为 YAML fenced code block，位于 `## 6 Agent 自动排查 Playbook` 标题下。

**生成原则：**

1. **覆盖第 3 章决策树的每一步**，但转换为机器可执行的检查项。
2. **覆盖第 4 章的每个候选原因**，为每个原因定义唯一的 detection pattern。
3. **层级决定顺序**：先区分触发链 → 再沿触发链逐层深入 → 最后验证修复。
4. **每一步必须包含**：`match`（命中判据）、`on_match`（命中的结论和跳转）、`on_no_match`（未命中时做什么）。
5. **Playbook 步骤只做只读操作**：grep 日志、检查 topic/service、比较数值。不写配置、不重启服务。

**可用的 Agent 执行原语：**

| 原语 | 用途 | 必填参数 |
|---|---|---|
| `grep_log` | 在指定模块日志中搜索正则 | `module`, `pattern`, `context_lines`（可选） |
| `ros_topic_check` | 检查 ROS topic 是否存在/有数据 | `topic`, `online_only: true` |
| `ros_service_check` | 检查 ROS service 是否可用 | `service`, `online_only: true` |
| `process_check` | 检查进程是否存活 | `process_name`, `online_only: true` |
| `extract_field` | 从日志行提取结构化字段 | `pattern`（含 capture groups）, `fields` |
| `compare_values` | 比较提取值是否在阈值内 | `field`, `min`/`max`/`equals` |
| `verify_fix` | 验证修复后错误不再复现 | `grep_pattern`, `watch_duration_sec` |

**从第 3 章决策树到 Playbook 的映射规则：**

```
决策表”顺序”列 → playbook step 的 id（如 classify_trigger_chain / check_map_service / check_json_parse）
决策表”检查项”列 → step 的 description
决策表”正常判据”列 → check 的 on_match 分支
决策表”异常判据”列 → check 的 on_no_match 分支
决策表”结论状态与下一步”列 → conclusion + goto 字段
停止规则        → 对应各 step 的 stop_on_match / stop_on_no_match 标记
```

**从第 4 章原因表到 Playbook 的映射规则：**

```
原因表的每一行 → playbook 最后阶段的一个 diagnose_* block
“原因与唯一特征”列 → detection 的 grep_log pattern
“负责链路”列     → responsible_module 字段
“临时处置”列     → temp_fix 字段
“根因修复”列     → root_fix 字段
“修复验证”列     → verify_fix 原语
```

**Playbook 结构模板：**

```yaml
playbook:
  meta:
    error_code: “<code>”
    error_name: “<name>”
    module: “<检查模块>”
    time_window: <错误前后秒数>
    
  steps:
    - id: classify_trigger_chain
      description: “区分触发链”
      checks:
        - type: grep_log
          module: “<模块>”
          pattern: “<触发链A的日志特征>”
          on_match:
            trigger_chain: “<名称>”
            conclusion: “<结论>”
            goto: diagnose_<chain_a>
        - type: grep_log
          module: “<模块>”
          pattern: “<触发链B的日志特征>”
          on_match:
            trigger_chain: “<名称>”
            conclusion: “<结论>”
            goto: diagnose_<chain_b>
        - type: on_no_match  # 兜底
          conclusion: “无法区分触发链”
          action: “expand_time_window”
          time_window: <扩大后的秒数>

    - id: diagnose_<chain_a>
      description: “<触发链A的深入排查>”
      checks:
        - type: grep_log
          module: “<模块>”
          pattern: “<更深层的日志特征>”
          priority: P1
          on_match:
            conclusion: “<结论>”
            root_cause: “<根因>”
            temp_fix: “<临时处置>”
          on_no_match:
            continue: true

    - id: diagnose_<chain_b>
      description: “<触发链B的深入排查>”
      checks: [...]

    - id: verify
      description: “修复验证”
      checks:
        - type: verify_fix
          grep_pattern: “<错误不再出现的判据>”
          watch_duration_sec: 60
          on_match:
            status: still_present
            action: escalate
          on_no_match:
            status: verified
```

**Playbook 质量要求：**

- 每条 `grep_log` 的 `pattern` 必须是从源码或日志中提取的**真实字符串**（不能是概念性描述）。
- `online_only: true` 的原语仅在机器人可达时可用；必须同时给出离线替代方案或标记为 “skip_if_offline”。
- 每个 step 只能有一个 `goto` 目标，确保 Agent 的决策路径是确定性的。
- 如果某个原因在当前仓库没有源码（底层模块在外部），在 playbook 中把该步骤标记为 `evidence_boundary: true`，不输出确定根因。

## 4 证据与结论约束

- `已确认`：注册表、源码、原始日志或复现实验能直接证明。
- `高可能`：特征高度吻合且已排除主要替代原因，但缺少最后一层直接证据。
- `待确认`：当前仅能作为排查方向或缺少关键输入。
- `已排除`：存在明确正常判据或反向证据。

错误码映射、触发机制和现场根因是三个不同结论，分别标注证据。代码位置优先记录“仓库相对路径 + 符号 + commit”；行号只作辅助，因为代码演进后会漂移。

若信息不足，仍可生成“证据受限版”文档，但必须：

- 写明适用版本与缺失证据；
- 把未证实原因保留为候选项；
- 给出取得关键证据的下一步；
- 禁止输出确定性根因或宣称修复成功。

## 5 完成标准

仅当以下条件全部满足时交付：

- 注册映射可追溯到文件、sheet/条目和版本；
- 置位、影响、上报、清除链路均有证据或明确边界；
- 日志决策表可引导 Agent 从现象走到具体模块或输入生产者；
- 每个候选原因都有唯一特征、行动和验证；
- 文档包含 Agent 结构化输出契约（第五章 YAML）；
- **Playbook 覆盖第 3 章决策树的每一步和第 4 章的每个候选原因；**
- **Playbook 的每个 grep/check 步骤都有明确的 on_match 和 on_no_match 分支；**
- **Playbook 中所有 grep_log pattern 均为可执行的正则，不包含概念性描述；**
- 所有链接、路径、命令和标题均已检查；
- 批量任务中每个用户指定的错误码都有明确产物或明确说明为何无法生成。
