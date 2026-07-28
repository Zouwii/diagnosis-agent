# JState 错误码 614006：调度要求到点精度阈值过高，本体无法满足

> 文档用途：当 AI Agent 在现场日志中发现 `614006` 时，用本文理解该错误码的注册信息、META 描述含义，以及在当前代码基线中的证据边界。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `614006` |
| JState Key | `/jstate/error/nav-manager/other_reason` |
| 错误描述（META） | 调度要求到点精度阈值过高，本体无法满足 |
| 等级 | `level5`，nav-manager 内部为 `ERROR` |
| 直接触发条件 | **当前代码基线中未找到置位调用**。注册表中描述为调度空间管理 footprint 配置不匹配。 |
| 直接影响 | 未知。ERROR 级别在触发态下最多发布 `/route/error` 3 次后停止。 |
| 自动恢复条件 | **当前代码基线中未找到清除调用**。依赖 `HealthMonitor::exit()` 任务重置时统一清除。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 机器人运行版本中包含该错误码的 META 注册 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` → 第 441 行 |

**核心判断**：`614006` 在 META XLSX 中注册为 "调度要求到点精度阈值过高，本体无法满足"，内部 key 为 `other_reason`。在 Java-monitor 源码中，`OTHER_REASON` 枚举已定义 (`abnormal_ids.h:53`) 并在 `health_monitor.cpp:122-123` 注册，但**当前本仓库代码基线中没有任何 `setStatus(OTHER_REASON, ...)` 的调用**。这意味着：

1. 该错误码的置位逻辑可能在其他仓库（如 nav-net、carrier-rotater）或通过 JState 外部 API 直接写入。
2. 可能是一个已废弃但未从注册表中清理的错误码。
3. 可能通过其他模块（如调度系统）的 ROS 消息间接触发。

本文基于现有证据给出排查方向，但不能给出根因分类。

本文使用以下证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | META、源码或现场原始日志可直接证明 |
| `高可能` | 特征与某一原因高度吻合，但仍缺少直接证据 |
| `待确认` | 当前只能作为排查方向 |
| `已排除` | 正常判据或反向证据已经排除该原因 |

## 2 错误触发的功能流程

META 描述 "调度要求到点精度阈值过高，本体无法满足" 表明该错误可能与以下机制相关：

1. 调度系统下发的到点精度（如 `feasible_region` 尺寸或 `xy_goal_tolerance`）比机器人实际能达到的精度更严格。
2. 机器人本体轮廓（footprint）或载货状态限制了到点精度能力。
3. `PrecisionManager` 模块在检查可行域与 footprint 匹配关系时发现不满足要求。

但在当前代码基线中，相关模块 (`precision_manager.cpp/h`, `precision_keeper.cpp/h`) 均未调用 `setStatus(OTHER_REASON, ...)`。

```text
推测流程（未在源码中证实）：
  调度系统下发任务（含到点精度参数）
    -> PrecisionManager 或相关模块检查精度要求
    -> 发现本体无法满足（footprint 超出精度边界）
    -> （未知模块）调用 setStatus(OTHER_REASON, true)
    -> /jstate/error/nav-manager/other_reason {trigger:true, level:5}
    -> JState 映射为 614006

ERROR 级别发布规则（health_monitor.cpp:250-259）：
  当 is_abnormal == true  → 发布 trigger:true 最多 3 次后停止
  当 is_abnormal == false → 不发送 trigger:false

因此：
  - ERROR 类型在置位后最多上报 3 次即静默
  - 不会自动发布恢复事件
  - 依赖任务重置时 exit() 统一清除
```

代码与注册证据：

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` → 第 441 行 |
| META 描述（中文） | 调度要求到点精度阈值过高，本体无法满足 |
| META 描述（英文） | scheduling requirement to point accuracy threshold is too high, and the vehicle cannot meet it. Please check the scheduling space management footprint related configuration |
| ERROR 等级和 JState key | `nav_core/src/health_monitor.cpp:122-123` |
| 枚举定义 | `nav_core/include/nav_core/struct/abnormal_ids.h:53` |
| **置位调用** | **本仓库中未找到 —— 证据边界** |
| **清除调用** | **本仓库中未找到 —— 证据边界** |
| 与 precision 相关的模块 | `manager/src/code_inserting/precision_manager.cpp`（但不设置 OTHER_REASON） |
| META 外部说明 | [调度要求到点精度阈值过高](https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7M4P5xhMwAA5LwVGXn6lpz) |

## 3 结合日志选择排查方向

由于当前代码基线没有置位逻辑，现场出现 `614006` 时，排查策略是：确定哪个外部模块触发了这个错误码。

先提取错误前后至少 120 秒的日志：

```bash
grep -E "other_reason|precision|footprint|feasible_region|精度|调度" \
  /opt/jz/log/nav-manager.log | tail -n 500
```

按顺序执行：

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间与版本 | JState、日志和任务属于同一时间窗 | 时间、任务或版本不一致 | 标记`待确认`并重新取证 |
| 2 | 错误来源确认 | 能从 `/route/error` 中确认 `other_reason` 出现 | JState 中出现但日志中无对应事件 | 错误可能从外部模块写入 JState，非 nav-manager 本地触发 |
| 3 | 调度任务上下文 | 错误出现时能找到对应的 dispatch 任务及其精度参数 | 无相关调度日志 | 扩大日志范围到调度系统 |
| 4 | precision 日志 | 日志显示 `precision` 或 `feasible_region` 相关计算 | 无 precision 相关日志 | 精度检查可能在其他模块完成 |
| 5 | footprint 配置 | 日志显示 footprint 解析和配置正常 | footprint 解析失败或配置缺失 | footprint 配置异常可能导致精度不匹配 |
| 6 | 跨模块关联 | 同任务中出现 carrier_init_failed、map_parse_error 等其他 INIT 类错误 | 仅 614006 孤立出现 | 组合出现时优先排查底层链路 |

停止规则：

- 如果没有 nav-manager 本地置位日志，跳转到调度系统或其他可能写入 JState 的模块。
- 已确认是外部模块触发时，标记证据边界，不可输出 nav-manager 内部的根因。
- 修复后持续监控同任务中再未出现 614006。

现场确认命令：

```bash
# 确认 JState 原始上报
rostopic echo -n 1 /route/error

# 确认 error 级别异常列表
grep "\[Abnormal\]" /opt/jz/log/nav-manager.log | tail -n 100

# 确认 precision 配置和计算
grep -E "precision|feasible_region" /opt/jz/log/nav-manager.log | tail -n 50

# 检查调度任务
grep -E "dispatch|preempt|task" /opt/jz/log/nav-manager.log | tail -n 100
```

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 调度下发精度过严：`feasible_region_width` 或 `xy_goal_tolerance` 小于机器人可达范围 | 调度系统、地图任务配置 | 临时放大到点精度参数或停止对当前点的高精度要求 | 修正调度系统中的精度配置，使其与机器人 footprint 和实际能力匹配 | 同一任务不再触发 614006 |
| P1 | footprint 配置不匹配：`schedule_footprint` 与实际机器人轮廓不一致 | footprint 配置、PrecisionManager | 核对并修正 footprint 参数 | 确保调度系统使用的 footprint 与机器人实际配置一致 | footprint 解析成功且精度检查通过 |
| P2 | 外部模块通过 JState 直接写入：nav-manager 本地无置位日志 | 调度系统、JState 代理、其他模块 | 确认写入来源后联系对应模块负责人 | 修正外部模块的触发逻辑或改为由 nav-manager 本地检查 | 614006 不再出现 |
| P3 | 旧版本残留：META 注册但代码中从未实现或已移除 | 注册表维护 | 确认是否需要保留该错误码 | 若不使用则从注册表中移除或补充实现 | 确认后更新注册表 |

**重要约束**：由于当前代码基线没有实现，上述原因均为基于 META 描述的推测。在拿到置位源码之前，不能将任何原因标记为 `已确认`。

## 5 修复验证与证据索引

闭环需要同时满足：

1. 已确认 `614006` 的触发来源（nav-manager 本地或外部模块）。
2. 如果是外部模块触发，已确认写入路径并定位根因。
3. 对应任务的到点精度参数与机器人实际能力匹配。
4. 相同任务连续执行多次不再出现 `614006`。

Agent 最少需要收集：

```text
错误时间及前后至少 120 秒的未过滤日志
/route/error 原始消息（确认 other_reason 的 trigger 字段）
同任务中所有异常日志
dispatch/preempt 任务参数（精度、feasible_region）
footprint 配置参数
nav-manager 及其他可能写入 JState 的模块版本
```

Agent 输出格式：

```yaml
error_code: 614006
error_name: other_reason
analysis_status: 待确认  # 已确认 / 高可能 / 待确认 / 已排除
applicable_version:
  primary_module: "nav-manager"
  trigger_source: unknown  # nav-manager / external / unknown
trigger_path: unknown
trigger_stage: unknown
confirmed_facts: []
most_likely_cause:
  cause: ""
  confidence: low
  evidence: []
excluded_causes: []
missing_evidence:
  - "本仓库无 OTHER_REASON setStatus 调用，需确认外部触发来源"
next_action:
  - "确认错误是否来自 nav-manager 本地置位还是外部模块写入"
temporary_action: ""
root_fix: ""
verification:
  result: not_started
  evidence: []
```

输出约束：

- 本仓库没有置位源码时，`trigger_source` 不得标记为 `nav-manager`。
- 根因必须是经源码证实的，不得用 META 描述代替根因。
- 未找到置位来源前，`analysis_status` 保持 `待确认`。

## 6 Agent 自动排查 Playbook

> 本章供 diagnosis-orchestrator 的确定性分析器自动执行。由于本仓库无触发源码，playbook 侧重跨模块证据搜集。

```yaml
playbook:
  meta:
    error_code: "614006"
    error_name: "other_reason"
    module: "nav-manager"
    time_window: 120

  steps:
    - id: classify_trigger_chain
      description: "确认 other_reason 是否在时间窗内出现"
      checks:
        - type: grep_log
          module: "nav-manager"
          pattern: "other_reason"
          on_match:
            trigger_chain: "other_reason_confirmed"
            conclusion: "命中 other_reason，可能在日志中作为 key 名出现"
            goto: diagnose_other_reason
        - type: on_no_match
          conclusion: "当前时间窗内未找到 other_reason 关键词，可能是通过 JState 外部写入"
          action: expand_time_window
          time_window: 300

    - id: diagnose_other_reason
      description: "按第3章决策表排查：错误来源 → precision 日志 → footprint 配置"
      checks:
        - type: grep_log
          module: "nav-manager"
          pattern: "setStatus.*other_reason"
          priority: P1
          on_match:
            conclusion: "nav-manager 本地置位 other_reason，非外部触发"
            root_cause: "待进一步分析本地置位上下文"
            goto: verify
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-manager"
          pattern: "\[Abnormal\].*other_reason"
          priority: P1
          on_match:
            conclusion: "other_reason 在异常列表中，确认为 nav-manager 注册的异常"
            continue: true
          on_no_match:
            conclusion: "other_reason 不在 nav-manager 异常列表中，确认非本模块触发"
            status: insufficient_data
            goto: verify
        - type: grep_log
          module: "nav-manager"
          pattern: "precision.*max|feasible_region|footprint.*parse"
          priority: P2
          on_match:
            conclusion: "存在 precision/footprint 相关日志，精度检查已执行"
            continue: true
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-manager"
          pattern: "schedule_footprint|origin_footprint"
          priority: P2
          on_match:
            conclusion: "footprint 配置日志存在，可核对调度 footprint 与实际是否一致"
            continue: true
          on_no_match:
            continue: true
        - type: on_no_match
          conclusion: "未找到 nav-manager 本地 other_reason 置位日志"
          status: insufficient_data
          root_cause: "other_reason 可能由外部模块通过 JState 写入，本仓库无触发源码"
          action: "扩展到调度系统日志，确认任务精度参数和 footprint 配置"

    - id: verify
      description: "验证 other_reason 是否消失"
      checks:
        - type: verify_fix
          grep_pattern: "other_reason"
          watch_duration_sec: 120
          on_match:
            status: still_present
            action: "other_reason 仍然存在，需扩展到外部模块日志排查"
          on_no_match:
            status: verified
            conclusion: "连续 120 秒未出现 other_reason，错误已清除"
```
