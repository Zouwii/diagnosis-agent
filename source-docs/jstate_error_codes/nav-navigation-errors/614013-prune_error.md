# JState 错误码 614013：裁断异常

> 文档用途：当 AI Agent 在现场日志中发现 `614013` 时，用本文理解该错误码的 META 注册信息、pruner 模块的裁断机制，以及在当前代码基线中的证据边界。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `614013` |
| JState Key | `/jstate/error/nav-manager/prune_error` |
| 错误描述（META） | 裁断异常（path prune abnormal） |
| 等级 | `level1`，nav-manager 内部应映射为 `WARN`（META 登记为 `level1`） |
| 直接触发条件 | **当前代码基线的 `health_monitor.cpp` 中未注册此错误码，本仓库无 `PRUNE_ERROR` 枚举或 `setStatus` 调用。** |
| 直接影响 | 未知。pruner 模块的裁断失败通常不影响安全性——裁断失败时默认保留原路径不作削减。 |
| 自动恢复条件 | 未知。若实现为 WARN 级别，则置 false 后发布 3 次停止。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 机器人运行版本中包含该错误码的 META 记录 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` → 第 448 行 |

**核心判断**：`614013`（prune_error / 裁断异常）在 META XLSX 中注册但**不在当前代码基线的 `health_monitor.cpp` 注册列表中**。`AbnormalIds` 枚举 (`abnormal_ids.h`) 中没有 `PRUNE_ERROR`，全仓库搜不到 `prune_error` 或 `PRUNE_ERROR` 字符串。

但 `pruner` 模块本身在代码中是存在的（`manager/src/code_inserting/pruner.cpp/h`），负责路径裁断（根据定位类型、轨迹切换点、折角等条件削减路径点）。裁断逻辑中多处有失败处理和日志输出，但没有关联到任何 `HealthMonitor` 异常状态。

可能情况：
1. META 中预先注册但从未在代码中实现。
2. 在其他仓库或版本中实现，但当前基线没有。
3. 已废弃但未从 META 中清理。

本文基于 pruner 模块的裁断机制给出排查方向，但无法给出根因分类。

本文使用以下证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | META、源码或现场原始日志可直接证明 |
| `高可能` | 特征与某一原因高度吻合，但仍缺少直接证据 |
| `待确认` | 当前只能作为排查方向 |
| `已排除` | 正常判据或反向证据已经排除该原因 |

## 2 裁断机制说明（pruner 模块）

尽管 `prune_error` 未注册为异常状态，但 pruner 模块的裁断逻辑构成了错误描述的需求背景。了解裁断机制有助于理解如果未来实现该错误码，会涵盖哪些场景。

pruner 模块 (`manager/src/code_inserting/pruner.cpp`) 负责以下裁断类型：

| 裁断类型 (const_nr_name) | 说明 |
|---|---|
| `start_n` | 起点定位裁断：根据定位状态决定路径起点时应保留哪些点 |
| `smooth_through` | 顺滑过点裁断：两点之间角度过大时裁断 |
| `traffic_control` | 交通管制裁断：逆行↔正行切换时的路径裁断 |
| `carrier_n` | 载货机构裁断：载货状态变化时的路径裁断 |
| `drive_type` | 驱动类型裁断：不同驱动模式切换时的裁断 |
| `uptrack` | 上道裁断：上道场景专用裁断逻辑 |
| `LonOrLateral` | 横纵向裁断：横向/纵向行驶模式切换时的裁断 |
| `loc_n` | 定位源裁断：定位源（如激光/二维码/GPS）切换时的裁断 |
| `traj_n` | 轨迹裁断：进入/离开轨迹时的裁断 |
| `rotate_n` | 旋转裁断：原地旋转或其他特殊旋转场景的裁断 |

调用链（不从 pruner 触发错误码，仅说明裁断发生位置）：

```text
NavPlugin::execute() 或 DispatchPreemptProcessor::process()
  -> Pruner::n(paths, nr_param, n_reason)
  -> 各种裁断子逻辑
  -> 失败时记录日志但不设置 HealthMonitor 异常
  -> 裁断失败时默认保留原路径不削减（安全兜底）
```

## 3 结合日志选择排查方向

先提取错误前后至少 120 秒的日志：

```bash
grep -E "prune|裁断|n_reason|hard_prune|Pruner" \
  /opt/jz/log/nav-manager.log | tail -n 500
```

按顺序执行：

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间与版本 | JState、日志和任务属于同一时间窗 | 时间、任务或版本不一致 | 标记`待确认`并重新取证 |
| 2 | 错误来源确认 | 能从 `/route/error` 确认 `prune_error` 出现 | 仅在 META 中注册但日志未出现 | pruner 的裁断失败日志 ≠ prune_error 错误码 |
| 3 | 裁断日志 | pruner 正常工作，无异常裁断 | pruner 输出 `LOGEE`/`LOGEW` 级别裁断异常 | 裁断异常可能但不一定触发 prune_error |
| 4 | 路径点数量变化 | 裁断后路径点合理减少 | 裁断后路径为空或点数异常（0 或 1） | 路径裁断过度可能影响后续导航 |
| 5 | 定位状态 | 定位源稳定、无频繁切换 | 定位源频繁切换触发 `loc_n` 裁断 | 定位不稳定时裁断更频繁 |
| 6 | 任务切换频率 | 任务路径正常 | 频繁任务抢占导致 `uptrack` 或 `start_n` 反复裁断 | 调度策略不当可能导致裁断异常 |

停止规则：

- 如果 pruner 日志正常且路径点数量合理，裁断失败可能是临时状态，无需处理。
- pruner 的 `n_reason` 日志不等于 prune_error 错误码。
- 如果 `prune_error` 确实出现在 JState 中但 nav-manager 无相关日志，需确认外部写入来源。

现场确认命令：

```bash
# 确认 JState 原始上报
rostopic echo -n 1 /route/error

# 查看裁断相关日志
grep -E "prune|裁断|Pruner" /opt/jz/log/nav-manager.log | tail -n 200

# 查看路径点数量异常
grep "size:0\|size:1" /opt/jz/log/nav-manager.log | tail -n 50

# 查看定位切换
grep -E "loc_n|loc_type|localization" /opt/jz/log/nav-manager.log | tail -n 100
```

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 错误码未实现：pruner 模块存在但未注册/触发 prune_error | META 注册表、health_monitor | 确认现场是否真的收到了该错误码 | 如果确实需要，在 pruner 关键失败点增加 `setStatus(PRUNE_ERROR)` 和注册 | 确认 META 和代码一致 |
| P2 | 外部模块写入：prune_error 由其他模块通过 JState 写入 | 调度系统、外部服务 | 确认写入来源 | 修正外部模块或将其实现迁移到 nav-manager | 不再出现或代码匹配 |
| P3 | 路径裁断过度：pruner 输出错误但未触发 prune_error | pruner 模块 | 手动检查路径合理性 | 修正 pruner 逻辑或增加异常监控 | 路径点数量合理，裁断日志无错误 |
| P3 | 定位源切换频繁：`loc_n` 裁断频繁触发 | 定位模块 | 检查定位稳定性 | 减少定位源异常切换 | 定位稳定，裁断频率降低 |

## 5 修复验证与证据索引

闭环需要同时满足：

1. 已确认 `614013` 是否需要保留及实际触发来源。
2. 如果是 META 注册但未实现，确认是否补充实现或从 META 移除。
3. pruner 裁断逻辑正常运行，路径点数量合理。
4. 如果有外部写入，已确认并修复。

Agent 最少需要收集：

```text
错误时间及前后至少 120 秒的未过滤日志
/route/error 原始消息（确认 prune_error 是否真的出现）
pruner 裁断相关日志
路径点数量变化
定位源切换日志
nav-manager 和调度系统版本
```

Agent 输出格式：

```yaml
error_code: 614013
error_name: prune_error
analysis_status: 待确认
applicable_version:
  primary_module: "nav-manager"
  pruner_exists: true    # pruner 模块存在
  registered_in_health_monitor: false  # 未在 health_monitor 中注册
trigger_path: unknown
trigger_stage: unknown
confirmed_facts:
  - "pruner 模块存在但未注册 prune_error 异常状态"
most_likely_cause:
  cause: ""
  confidence: low
  evidence: []
excluded_causes: []
missing_evidence:
  - "PRUNE_ERROR 未在 health_monitor.cpp 注册，未见任何 setStatus 调用"
next_action:
  - "确认现场是否真的出现 614013"
  - "若出现则确认写入来源"
temporary_action: ""
root_fix: ""
verification:
  result: not_started
  evidence: []
```

代码与数据证据：

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` → 第 448 行 |
| **health_monitor 注册列表（无 PRUNE_ERROR）** | `nav_core/src/health_monitor.cpp:65-124` 全量列表中不包含 |
| **AbnormalIds 枚举（无 PRUNE_ERROR）** | `nav_core/include/nav_core/struct/abnormal_ids.h` 不包含 |
| pruner 模块存在 | `manager/src/code_inserting/pruner.cpp` |
| **pruner 模块不设置 HealthMonitor 异常** | 全量搜索 `pruner.cpp` 中无 `setStatus` 调用 |
| META 外部说明 | [裁断异常](https://alidocs.dingtalk.com/i/nodes/20eMKjyp81RjK3g0Cd0NryL6WxAZB1Gv) |

## 6 Agent 自动排查 Playbook

> 本章供 diagnosis-orchestrator 的确定性分析器自动执行。由于 prune_error 未在代码中注册/触发，playbook 侧重跨模块证据搜集。

```yaml
playbook:
  meta:
    error_code: "614013"
    error_name: "prune_error"
    module: "nav-manager"
    time_window: 120

  steps:
    - id: classify_trigger_chain
      description: "确认 prune_error 是否在日志中出现"
      checks:
        - type: grep_log
          module: "nav-manager"
          pattern: "prune_error"
          on_match:
            trigger_chain: "prune_error_in_log"
            conclusion: "日志中出现 prune_error 关键词，可能是 pruner 的裁断失败日志"
            goto: diagnose_prune_error
        - type: on_no_match
          conclusion: "当前时间窗内未找到 prune_error，可能是通过 JState 外部写入或未触发"
          action: expand_time_window
          time_window: 300

    - id: diagnose_prune_error
      description: "排查：pruner 裁断日志 → 路径点异常 → 定位切换"
      checks:
        - type: grep_log
          module: "nav-manager"
          pattern: "Pruner|prune|n_reason"
          priority: P1
          on_match:
            conclusion: "pruner 模块有裁断活动"
            continue: true
          on_no_match:
            conclusion: "无 pruner 活动日志，裁断未触发或未记录"
            continue: true
        - type: grep_log
          module: "nav-manager"
          pattern: "path.*size:[01][^0-9]"
          priority: P2
          on_match:
            conclusion: "路径点数量异常（0或1），裁断可能过度"
            root_cause: "裁断后路径点数量过少，影响后续导航"
            goto: verify
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-manager"
          pattern: "loc_n|loc_type|localization.*switch"
          priority: P2
          on_match:
            conclusion: "定位源切换日志存在，可能触发 loc_n 裁断"
            continue: true
          on_no_match:
            continue: true
        - type: on_no_match
          conclusion: "prune_error 未在 nav-manager 代码中注册为异常状态，本仓库无触发源码"
          status: insufficient_data
          root_cause: "prune_error 在 META 中注册但未在代码中实现"
          action: "确认现场是否真的通过 JState 收到此错误码，若收到则追踪外部写入来源"

    - id: verify
      description: "验证 pruner 是否恢复正常"
      checks:
        - type: verify_fix
          grep_pattern: "prune_error"
          watch_duration_sec: 120
          on_match:
            status: still_present
            action: "仍然存在，需确认是否影响导航功能"
          on_no_match:
            status: verified
            conclusion: "连续 120 秒未出现 prune_error"
```
