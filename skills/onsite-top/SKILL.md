---
name: onsite-top
description: 现场高频无错误码问题排查。当诊断流程发现症状（导航卡死、非法旋转、路径偏离、到点精度异常、运行参数异常、外部限速、速度跟踪偏差）但没有对应 JState 6 位错误码时，调用本 Skill 匹配问题模式，读取现场问题知识库文档，执行 Playbook 并输出诊断结论与处置建议。Triggers on "卡住" "不动" "移动中" "旋转" "走偏" "走歪" "偏离" "到点精度" "参数异常" "限速" "速度跟踪" "onsite" "现场问题".
author: zhr
---

# Onsite Top——无错误码现场高频问题排查

当下述症状出现但没有 6 位 JState 错误码可匹配时，从 `source-docs/onsite-top/` 知识库中匹配问题模式，执行版本检查和症状诊断。

---

## 1 症状 → 问题模式路由

根据用户描述或日志特征，匹配以下问题模式：

| 症状关键词 | 问题模式 | 文档 | Playbook |
|---|---|---|---|
| 卡住、不动、前进中不动、后退中不动、移动中实际未动、准备移动不动 | `navigation_stuck` | `01-navigation-stuck.md` | ✅ 有 |
| 非法旋转、禁止旋转点旋转、原地旋转、甩头、摆头、不受道路限制旋转 | `illegal_rotation` | `02-illegal-rotation.md` | ⚠️ 草稿，概念级 |
| 走偏、走歪、偏离路线、冲出路线、偏移超过阈值 | `path_deviation` | `03-path-deviation.md` | ⚠️ 草稿，概念级 |
| 到点精度异常、到点报错精度、REACH_WITH_ERROR | `arrival_precision_abnormal` | `06-arrival-precision-2412-agent.md` | ✅ 有 |
| 运行参数异常、参数错误、任务下发失败、chassis/speed/calib/task param error | `nav_param_error` | `07-nav-param-error-2412-agent.md` | ✅ 有 |
| 速度受限、限速、跑得慢、speed_confined | `speed_confined_by_navchecker` | `08-navchecker-speed-confined-2412-agent.md` | ✅ 有 |
| 速度跟踪偏差、速度不一致、CMD_INVALID、CMD_OSCILLATING | `speed_tracking_deviation` | `09-speed-tracking-deviation-2412-agent.md` | ✅ 有 |

匹配优先级：从用户描述中提取关键特征词 → 按上表从高到低（频率）匹配 → 首个命中即为问题模式。

多症状时：按时间顺序逐个诊断，判断因果链。

---

## 2 排查流程

### 2.0 版本基线检查（每次必做）

在匹配问题模式之前，先读取 `source-docs/onsite-top/00-version-baseline.md`，检查现场运行的子包版本：

```bash
# 获取现场子包版本
dpkg -l | grep -E "nav-base|jz-motion-common|nav-net|nav-manager|speed-manager|jz-pnc|safe-perception"
# 或
cat /opt/jz/version_manifest.json 2>/dev/null
```

与基线对照，任一子包版本 < 建议升级版本 → 标记 `version_mismatch`（高风险），输出升级建议。

```yaml
version_check:
  any_mismatch: true/false
  mismatches:
    - package: "nav-manager"
      running: "1.2412.120"
      recommended: "1.2412.185"
  recommendation: "建议优先升级以上子包后复测"
```

### 2.1 匹配问题模式

从用户描述/日志中提取症状关键词，按第 1 节路由表匹配。匹配到后：
- ✅ 标记的 → 读取对应文档，进入 2.2 执行 Playbook
- ⚠️ 草稿标记的 → 读取文档作为概念指导，无法执行 Playbook，输出 `insufficient_data`

### 2.2 读取文档并执行 Playbook

文档路径：`source-docs/onsite-top/{doc_name}`

1. 完整读取匹配到的文档
2. 从 `## 1 问题结论` 获取问题定义和触发条件
3. 从 `## 3 结合日志选择排查方向` 获取日志 grep 命令和决策表
4. 从 `## 6 Agent 自动排查 Playbook` 获取 YAML Playbook
5. 按 Playbook 的 `steps[].id` 顺序执行：
   - `grep_log` → 在指定模块日志中搜索 pattern
   - `ros_topic_check` / `ros_service_check` / `process_check` → 在线模式执行
   - `verify_fix` → 观察指定时长内是否复现
6. 命中 `on_match` → 记录 conclusion，按 `goto` 跳转
7. 未命中 `on_no_match` → 按 `goto` 或 `continue: true` 继续
8. 遇到 `insufficient_data` → 停止归因

### 2.3 未匹配到任何模式

如果症状不匹配任何已知问题模式：

1. 读取所有 `*-agent.md` 的 `## 1 问题结论`，判断是否有部分匹配
2. 仍无法匹配 → 标记 `unknown_pattern`，输出：
   ```yaml
   diagnosis_status: unknown_pattern
   checked_patterns: [已检查的模式列表]
   recommendation: "请补充症状细节或提供更多日志"
   ```
3. 建议使用 `error-code-analysis-doc-generator` 参考流程创建新的现场问题文档

---

## 3 输出格式

```yaml
diagnosis_result:
  problem_pattern: "navigation_stuck"
  version_check:
    any_mismatch: false
  playbook_execution:
    - step: "classify_block_point"
      matched_check: 0
      conclusion: "goal 已下发到 move_base"
      goto: "check_movebase_feedback"
    - step: "check_movebase_feedback"
      matched_check: 0
      conclusion: "move_base 有反馈"
      goto: "check_traffic_stop"
    # ... 后续步骤
  root_cause:
    cause: "交管信号阻塞 move_base"
    confidence: "已确认"
    evidence: ["traffic_stop=true 出现在日志"]
  actions:
    temporary: "释放交管或切单机模式"
    permanent: "修复交管算法死锁、缩减交管区域"
  missing_evidence: []
```

---

## 4 离线降级

Playbook 中 `ros_topic_check`、`ros_service_check`、`process_check` 等在线原语在离线分析时：
- 标记为 `skip_if_offline`
- 改用日志中的间接证据替代（如日志中有 cmd_vel 发布记录可替代 topic 检查）

---

## 5 与 diagnosis-orchestrator 协作

```
diagnosis-orchestrator（流程控制）
  ├── 解析日志，发现症状但无 JState 错误码
  ├── → 委托 onsite-top
  │     ├── 版本基线检查
  │     ├── 症状 → 问题模式匹配
  │     ├── 读取 onsite-top/{doc}.md
  │     ├── 执行 Playbook
  │     └── 返回结论 + 处置
  └── 继续主诊断流程
```

---

## 6 知识库维护

| 属性 | 说明 |
|---|---|
| 知识目录 | `source-docs/onsite-top/` |
| Agent 版（✅） | `06-09`，基于 2412 代码审计，含完整 Playbook |
| 草稿版（⚠️） | `01-03`，概念级，待补做 2412 代码审计 |
| 版本基线 | `00-version-baseline.md`，每次诊断必查 |
| 数据来源 | Q2 现场问题报表，197 条导航问题中归纳 |
| 代码基线 | `nav-manager` + `nav-base` `RC/1.2412.x` 分支 |
