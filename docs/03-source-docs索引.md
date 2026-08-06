# source-docs 知识源索引

> 日期：2026-08-04
> 说明：记录 `source-docs/` 下知识资产的来源、生成方式和维护方式

---

## 1. 目录总览

```
source-docs/
├── jstate_error_codes/        错误码体系（有脚本生成器）
│   ├── nav-navigation-errors/  人版正式文档（54 份）→ 领导 Skill 生成
│   ├── agent/                  Agent 执行文档（54 份）→ 脚本生成
│   ├── generate_agent_docs.py  生成脚本（已验证）
│   ├── normalize_bc_agent_docs.py  规范化脚本（已验证）
│   ├── error-code-analysis-doc-generator/  领导维护的 Skill
│   └── 机型3代状态数据-META大全.xlsx  错误码元数据
└── onsite-top/                现场高频问题文档
    ├── README.md                    目录索引（2026-08-06）
    ├── 01-navigation-stuck.md       导航卡住草稿
    ├── 02-illegal-rotation.md       非法旋转草稿
    ├── 03-path-deviation.md         路径偏离草稿
    ├── 06-arrival-precision-2412-agent.md      到点精度 Agent 版 ✅
    ├── 07-nav-param-error-2412-agent.md        运行参数异常 Agent 版 ✅
    ├── 08-navchecker-speed-confined-2412-agent.md 外部限速 Agent 版 ✅
    ├── 09-speed-tracking-deviation-2412-agent.md  速度跟踪偏差 Agent 版 ✅
    └── scripts/                    辅助分析脚本
        ├── classify_q2.py            TB 单问题分类
        ├── Q2_origin.md              TB 原始数据
        ├── Q2_real.md                TB 真实分类
        └── migrate_customfields.py   字段迁移脚本
```

---

## 2. jstate_error_codes：有脚本生成器的错误码体系

### 2.1 人版正式文档（nav-navigation-errors/）

| 属性 | 说明 |
|---|---|
| **数量** | 54 份 Markdown |
| **来源** | 领导维护的 `error-code-analysis-doc-generator` Skill 生成 |
| **内容** | 每个错误码的完整分析：触发条件、日志位置、排查方向、处置建议 |
| **维护方式** | 由领导通过 Skill 更新后同步到本仓库 |
| **运行时引用** | Agent 不直接加载此目录，仅供人工阅读和生成脚本的输入 |
| **上游** | `nav-manager/docs/jstate_error_codes/nav-navigation-errors/`（两边当前字节级一致） |

### 2.2 Agent 执行文档（agent/）

| 属性 | 说明 |
|---|---|
| **数量** | 54 份 Markdown |
| **生成脚本** | `generate_agent_docs.py`（已通过 CHANGELOG 记录验证：54/54 可加载） |
| **生成方式** | 从 `nav-navigation-errors/` 的人版文档中提取结构化章节和 YAML Playbook |
| **内容** | 面向 Agent 执行视图：问题识别、日志关键字、Playbook YAML、停止规则、下一步建议 |
| **维护方式** | **不应手工修改**。人版更新后重新运行 `generate_agent_docs.py` 生成 |
| **运行时引用** | `knowledge/playbook_loader.py` 加载此目录下的 Playbook |
| **规范化脚本** | `normalize_bc_agent_docs.py`：对 B/C 类文档的只读诊断规范化（已执行） |

### 2.3 生成与规范化脚本

| 脚本 | 路径 | 状态 | 说明 |
|---|---|---|---|
| `generate_agent_docs.py` | `jstate_error_codes/` | ✅ 已验证 | 从人版文档批量生成 Agent 版 |
| `normalize_bc_agent_docs.py` | `jstate_error_codes/` | ✅ 已验证 | B/C 类 Agent 文档规范化（补充章节、Playbook 格式修复） |

### 2.4 领导维护的 Skill

| 文件 | 说明 |
|---|---|
| `error-code-analysis-doc-generator/SKILL.md` | Skill 定义 |
| `error-code-analysis-doc-generator/agents/openai.yaml` | Agent 配置 |
| `error-code-analysis-doc-generator/assets/error-code-analysis-template.md` | 文档模板 |
| `error-code-analysis-doc-generator/references/document-spec.md` | 文档规范 |
| `error-code-analysis-doc-generator/scripts/find_error_code_in_xlsx.py` | 从 Excel 提取错误码 |

**本 Skill 本轮不修改**，由领导单独维护。

---

## 3. onsite-top：现场高频问题文档

### 3.1 文档清单

| 编号 | 文件 | 说明 | 状态 | 对应问题模式 |
|---|---|---|---|---|
| 01 | `01-navigation-stuck.md` | 导航卡住 | ⚠️ 草稿（无 Agent Playbook） | `navigation_stuck` |
| 02 | `02-illegal-rotation.md` | 非法旋转 | ⚠️ 草稿（无 Agent Playbook） | `illegal_rotation` |
| 03 | `03-path-deviation.md` | 路径偏离 | ⚠️ 草稿（无 Agent Playbook） | `path_deviation` |
| 06 | `06-arrival-precision-2412-agent.md` | 到点精度异常 | ✅ Agent 版 | `arrival_precision_abnormal` |
| 07 | `07-nav-param-error-2412-agent.md` | 导航运行参数异常 | ✅ Agent 版 | `nav_param_error` |
| 08 | `08-navchecker-speed-confined-2412-agent.md` | nav-checker 外部限速 | ✅ Agent 版 | `speed_confined_by_navchecker` |
| 09 | `09-speed-tracking-deviation-2412-agent.md` | 速度跟踪偏差 | ✅ Agent 版 | `speed_tracking_deviation` |
| — | `README.md` | 目录索引 | ✅ 2026-08-06 | — |

### 3.2 生成方式

| 版本 | 数量 | 来源 | 说明 |
|---|---|---|---|
| 草稿（01-03） | 3 | 通用概念文档 | 未基于 2412 代码审计，缺少 Playbook，待后续补做 |
| Agent 版（06-09） | 4 | 手工派生 | 基于 `RC/1.2412.x` 代码审计，含 §1-§5 知识底座 + §6 YAML Playbook |

> **生成流程**：从人版代码审计稿 → 手工添加 YAML Playbook → Agent 版。
> 当前没有自动生成脚本。`docs/02-开发任务.md` 规划了 Agent 版自动生成器（待实现）。

### 3.3 已删除的文件

| 文件 | 删除原因 |
|---|---|
| `04-arrival-precision.md` | 通用版，被 `05` 的 2412 精确代码分析替代 |
| `05-arrival-precision-2412.md` | 人版，内容已完整收录在 `06` Agent 版中，纯冗余 |

### 3.3 辅助脚本

| 文件 | 说明 |
|---|---|
| `scripts/classify_q2.py` | 对 TB 单 Q2（问题分类字段）做分类统计 |
| `scripts/Q2_origin.md` | TB Q2 原始数据样本 |
| `scripts/Q2_real.md` | TB Q2 真实分类结果 |
| `scripts/migrate_customfields.py` | 自定义字段迁移 |

这些脚本用于数据分析，不参与 Agent 运行时的文档加载。

---

## 4. source-docs 与运行时代码的关系

```
source-docs/
│
├── jstate_error_codes/
│   ├── nav-navigation-errors/*.md       ← 人工阅读，不直接加载
│   ├── agent/*.md                       ← knowledge/playbook_loader.py 加载
│   ├── generate_agent_docs.py           ← 生成脚本（手动运行）
│   └── normalize_bc_agent_docs.py       ← 规范化脚本（手动运行）
│
└── onsite-top/
    ├── 06-arrival-precision-2412-agent.md     ← 手工派生
    ├── 07-nav-param-error-2412-agent.md       ← 手工派生
    ├── 08-navchecker-speed-confined-2412-agent.md ← 手工派生
    ├── 09-speed-tracking-deviation-2412-agent.md  ← 手工派生
    └── scripts/                         ← 分析辅助，不参与运行时
```

### 4.1 运行时加载

| 加载器 | 加载目录 | 内容 |
|---|---|---|
| `knowledge/playbook_loader.py` | `source-docs/jstate_error_codes/agent/` | 54 个 Playbook YAML |
| `knowledge/topk_loader.py` | 硬编码路径指向 management-system `docs/error-code-system/` | B 类文档关键词匹配 |

### 4.2 更新流程

错误码文档的更新流程：

```
领导更新 Skill → 运行 Skill 生成人版文档
    → 同步人版到 source-docs/jstate_error_codes/nav-navigation-errors/
    → 运行 generate_agent_docs.py
    → 运行 normalize_bc_agent_docs.py（如有需要）
    → 验证 knowledge/playbook_loader.py 可加载所有 Playbook
```

现场高频问题文档的更新流程（当前）：

```
人工撰写人版文档 → 人工派生 Agent 版
    → 两版同步修改
```

---

## 5. 资产状态汇总

| 目录 | 数量 | 来源 | 生成器 | Agent 版 | 运行时加载 |
|---|---|---|---|---|---|
| `jstate_error_codes/nav-navigation-errors/` | 54 md | 领导 Skill | — | — | ❌ |
| `jstate_error_codes/agent/` | 54 md | 脚本生成 | `generate_agent_docs.py` ✅ | ✅ | `playbook_loader.py` |
| `onsite-top/` | 7 md + README | 人工撰写 | 无已验证脚本 | 手工派生 ⚠️ | ❌（当前未接入） |
