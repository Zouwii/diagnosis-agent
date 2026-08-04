# 变更记录

本文记录 `diagnosis-agent` 的重要改动、设计边界和验证结果，帮助后续开发快速回答：改了什么、为什么改、影响哪些文件、目前做到什么程度。

记录约定：

- 新改动优先写入“未发布”章节，按日期倒序排列。
- 使用“新增 / 变更 / 修复 / 删除 / 验证 / 暂不处理”分类。
- 只记录已经落地的事实；计划中的工作必须明确标注为“暂不处理”或“待办”。
- 涉及自动生成内容时，同时记录源文档、生成脚本和生成目录，避免误改生成文件。

## 未发布

### 2026-08-03：JState 错误码文档整理与 Agent 化

#### 新增

- 新增 `source-docs/jstate_error_codes/agent/`，保存面向 Agent 的精简错误码文档。
- 新增 `source-docs/jstate_error_codes/generate_agent_docs.py`：从领导 Skill 生成的正式文档中提取 Agent 所需章节。
- 新增 `source-docs/jstate_error_codes/normalize_bc_agent_docs.py`：对缺章节或 Playbook 不可解析的 B/C 类 Agent 文档进行只读诊断规范化。
- 新增到点精度异常 2412 版文档：
  - `source-docs/onsite-top/05-arrival-precision-2412.md`
  - `source-docs/onsite-top/06-arrival-precision-2412-agent.md`
- 新增高频导航问题知识建设任务说明：`docs/06-高频导航问题知识建设任务.md`。

#### 变更

- JState 文档调整为两层：
  - `nav-navigation-errors/`：领导 Skill 生成的人的原文和完整分析依据。
  - `agent/`：脚本生成的 Agent 执行视图，不应直接手工修改。
- `knowledge/playbook_loader.py` 改为从本项目的 `source-docs/jstate_error_codes/agent/` 加载 Playbook，不再依赖其他仓库中的绝对路径。
- Agent 错误码排查边界明确为：优先分析同期日志和关键字段，执行只读检查，输出证据、结论状态和下一步人工建议。
- B/C 类规范化会补充缺失的日志决策表、停止规则、结构化输出契约和可解析 Playbook。

#### 修复

- 修复部分文档虽然包含 Playbook 文本，但使用分号式伪 YAML、错误章节编号或不完整分支，导致 loader 无法解析的问题。
- 修复 Playbook 中缺少兜底分支、跳转目标不完整的问题。
- 共规范化 25 份原先不可加载的 Agent 文档，其中包含 B/C 类文档以及 5 份章节看似完整但 YAML 无法解析的文档。

#### 删除

- 删除 JState 顶层重复的单码文档和参考模板，避免与 `nav-navigation-errors/` 中的正式文档重复。
- 删除旧的 `nav-navigation-errors/batch_gen.sh`。
- 删除历史拆分过程产生的中间目录、嵌套 Agent 目录、缓存及报告文件。

#### 验证

- 正式错误码源文档：54 份。
- Agent 错误码文档：54 份。
- loader 可加载 Playbook：54/54。
- 已检查 Playbook 跳转目标，无悬空 `goto`。
- 新增的规范化 Playbook 不包含 bag、配置写入、服务重启或车辆控制原语。
- `knowledge/playbook_loader.py`、生成脚本和规范化脚本均通过 Python 语法检查。

#### 暂不处理

- 暂不建设 case 数据集。
- 暂不开发 rosbag 自动分析能力。
- 暂不允许 Agent 修改车辆状态、修改配置、重启服务或改动业务代码。
- 领导维护的 `source-docs/jstate_error_codes/error-code-analysis-doc-generator/` Skill 本轮不修改。

### 后续记录模板

复制下面内容追加到“未发布”章节顶部：

```markdown
### YYYY-MM-DD：变更主题

#### 新增

-

#### 变更

-

#### 修复

-

#### 删除

-

#### 验证

-

#### 暂不处理

-
```

## 文档来源关系

- `diagnosis-agent/source-docs/jstate_error_codes/` 最初来自 `mainbody/nav-manager/docs/jstate_error_codes/` 的迁入。
- 根据当前文件状态，这次操作应准确理解为“复制/迁入”，不是彻底移动：`nav-manager` 中的原始文件目前仍然保留。
- 两边 `nav-navigation-errors/` 下的 54 份人版错误码文档当前字节级一致；领导 Skill、模板、规范、辅助脚本和 META Excel 也一致。
- 当前暂定 `nav-manager/docs/jstate_error_codes/` 为上游原始技术资料，`diagnosis-agent/source-docs/jstate_error_codes/` 为诊断项目内的知识副本及 Agent 加工入口。
- Agent 实际运行只加载 `diagnosis-agent/source-docs/jstate_error_codes/agent/`，不直接加载 `nav-manager` 中的文档。

### 2026-08-03：清理旧错误码文档目录

#### 删除

- 删除 `docs/error-code-system/`。该目录中的旧错误码总表、4 份 `fix` 文档及旧数据库/RAG 说明已由 `source-docs/jstate_error_codes/` 体系替代，且当前运行时代码不读取这些本地文件。

#### 保留

- 保留 `source-docs/onsite-top/05-arrival-precision-2412.md`。
- 保留 `source-docs/onsite-top/06-arrival-precision-2412-agent.md`。

### 2026-08-03：修正高频问题文档建设设计

#### 变更

- 将建设主线由“先建立 TB Case 数据集”修正为“报表选择 Top 问题、识别所需代码仓库、跨仓库定位日志与字段、生成人版和 Agent 版排查文档”。
- 明确代码仓库用于建立可能的触发链和日志判据；具体现场根因仍需同期日志、版本、配置和复测证据确认。
- TB 单调整为可选验证材料，不再作为第一阶段启动前提，也暂不建设完整 Case 数据集。
- 现有到点精度 05/06 文档定位为 `nav-manager` 单仓库范围内的第一版草稿，待仓库覆盖表完善后再补齐跨模块链路。
