# JState 错误码 615005：长距离里程计数据不更新

> 文档用途：当 AI Agent 在现场日志中发现 `615005` 时，用本文理解定位里程计与实时里程计的偏差检测逻辑，并根据同期数据判断是定位卡死、odom 异常还是传感器配置不匹配。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615005` |
| JState Key | `/jstate/error/nav-net/locating_muted_for_a_long_ride` |
| 错误描述 | 长距离里程计数据不更新 |
| 等级 | `level1`（WARN）。nav-net 通过 `pubJ3State` 直接发布 `trigger:true`，无 `pubJ3StateFalse` 清除调用；依赖下一轮 `HDI->clear()` 自动清除。 |
| 直接触发条件 | 导航运行中（`is_nav_running_ == true`），最近一次定位触发的里程计点（`locating_odom_`）与当前里程计点（`current_odom_`）的欧氏距离 > 阈值。阈值：2D 激光 `kDefaultVal2d=30m`，3D 激光 `kDefaultVal3d=10m`。 |
| 直接影响 | 标记 `mute_lost_active_=true`，错误通过 `/route/error` 对外发布；定位有效性可能受影响。 |
| 自动恢复条件 | 下一轮 `setLoop()` 迭代（500ms 间隔）检测到里程计距离 ≤ 阈值时，`HDI->clear()` 清除；`setLocatingMutedLost(false)` 不主动发布恢复事件。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 机器人运行版本包含 nav-net 模块，`/algo/property/motion_odom_topic` 配置了里程计话题 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`615005` 不是简单的"里程计坏了"，而是 nav-net 在导航状态下持续对比**定位触发的参考里程计**（`locating_odom_`）与**实时里程计**（`current_odom_`）的差值。`locating_odom_` 仅在定位验证通过时更新（`handlelocateStatusTopic`），而 `current_odom_` 每帧更新。差值 > 阈值意味着**定位系统已长时间没有确认有效位置**，机器人可能已跑出允许范围。

本文使用以下证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | META 注册、源码可证明触发条件和阈值 |
| `高可能` | 现场同期日志和 odom 数据与触条件吻合 |
| `待确认` | 存在差值但缺少原始 odom 数据对比 |
| `已排除` | 里程计距离在阈值内 |

## 2 错误触发的功能流程

进入该错误链的前置条件：

1. nav-net 处于导航模式（`car_mode_ == Mode::kNav`）
2. 导航任务正在运行（`is_nav_running_ == true`，由 `/vtr/move/feedback` 置位）
3. 上一轮已获取到参考里程计（`get_locating_odom_ == true`，由 `handlelocateStatusTopic` 确认）
4. 当前 odom 数据可用（`get_current_odom_ == true`，由 `handleMotionOdomTopic` 更新）

```mermaid
flowchart TD
    A[setLoop 2Hz 循环] --> B{car_mode_ == kNav?}
    B -- 否 --> Z[跳过, sleep]
    B -- 是 --> C[handlelocateStatusTopic]
    C --> D{get_locating_odom_ && get_current_odom_?}
    D -- 否 --> E[reset mute_lost_active_=false]
    D -- 是 --> F[计算 tfDistance]
    F --> G{locating_odom_ vs current_odom_}
    G -- "距离 > 30m/10m" --> H[setLocatingMutedLost true]
    G -- "距离 <= 阈值" --> I{之前是 mute 态?}
    I -- 是 --> J[setLocatingMutedLost false]
    I -- 否 --> K[正常]
    H --> L[pJ3State kLocatingMutedLost]
    L --> M[/route/error 615005]
    H --> N[mute_lost_active_ = true]
    E --> O[HDI->clear]
    J --> O
    K --> O
    M --> O
    O --> P[HDI->publish]
    P --> A
```

对应调用链：

```text
PositionRecover::setLoop()                    @ position_recover.cc:515
  -> handleMotionOdomTopic()                  @ :505  更新 current_odom_
  -> handlelocateStatusTopic(locate_status_)  @ :154  更新 locating_odom_（仅当定位验证通过）
  -> 检查条件：is_nav_running_ && get_locating_odom_ && get_current_odom_
  -> tf::tfDistance(locating_odom_, current_odom_) > threshold
  -> setLocatingMutedLost(true, threshold)    @ :576
  -> HDI->pubJ3State(kLocatingMutedLost, 1, "长距离定位数据不更新")
  -> /route/error -> JState 615005

恢复（同一循环）：
  -> 下一次 loop: HDI->clear()  @ :570  无条件清除所有异常
  -> 若距离 <= 阈值: setLocatingMutedLost(false, 0)  @ :577  只做 mute_lost_active_=false
  -> HDI->publish()  @ :569  此时 615005 已清除
```

错误生命周期：

```text
setLoop 2Hz 循环（500ms 间隔）:
  每一帧开始 → HDI->clear() 无条件清空所有异常
  → 若触发条件满足 → pubJ3State(trigger:true) → /route/error 发布
  → 若条件不满足且之前已触发 → setLocatingMutedLost(false) → 不发布 pubJ3StateFalse
  → HDI->publish() → 发布到 /agent/health/in
  → 下一帧 HDI->clear() 后 615005 自动消失

因此：
  - 615005 的生命周期 = 最多 500ms（一个 loop 周期）
  - 如果 odom 差距持续 > 阈值，每帧重新触发
  - "不再出现 615005" 不代表定位恢复，只代表 odom 差距回落到阈值内
  - 实际恢复验证需要确认定位源持续有效
```

关联错误的时序解释：

| 时序或组合 | 优先判断 |
|---|---|
| `615005` 与 `615011`（recover_position_failed）同时出现 | 优先排查定位恢复链——定位恢复失败导致长时间无 valid pose，odom 差距累积 |
| `615005` 单独反复出现 | 优先排查定位系统卡死或 odom topic 异常 |
| `615005` 出现后 `615037`（req_locate_failed）出现 | 定位系统整体不可用，`locating_odom_` 停止更新 |
| `615005` 2D(30m) vs 3D(10m) 频繁触发差异 | 检查 `/j3/jzhw/model/laser` 中 `laserType` 是否正确配置 |

## 3 结合日志选择排查方向

先提取错误前后至少 120 秒的日志：

```bash
grep -E "locating muted|locatingOdom|currentOdom|mute_lost|setLoop|kLocatingMutedLost" \
  /opt/jz/log/nav-net.log | tail -n 500
```

按顺序执行：

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间与版本 | JState、日志属于同一时间窗，激光类型（laserType）正确配置 | 时间、版本或配置不一致 | 标记`待确认`并重新取证 |
| 2 | 直接触发日志 | 出现 `locating muted for a long ride:30m` 或 `:10m` | 找不到该日志 | 扩大时间窗或核对 nav-net 日志级别 |
| 3 | odom 数据源 | `handleMotionOdomTopic` 正常收到数据，`get_current_odom_=true` | topic `/algo/property/motion_odom_topic` 无消息或 `get_current_odom_=false` | odom 数据中断→`高可能`，检查 odom topic 发布者 |
| 4 | 定位里程计更新 | `handlelocateStatusTopic` 中 `get_locating_odom_` 被置为 true（定位验证通过） | locating_odom_ 长期未更新（定位验证持续失败） | 定位系统异常→`高可能`，检查 `/vtr/localization` 和定位状态 |
| 5 | 阈值合理性 | 2D 激光阈值 30m 或 3D 阈值 10m，odom 差值偶尔超阈值后恢复 | 差值持续大幅超过阈值（如 >100m） | 配置不合理或定位严重偏移→`高可能` |
| 6 | laserType 配置 | `state` 日志显示正确的 laserType（"2d" 或 "3d"） | laserType 配置与实际硬件不匹配 | 阈值用错→`已确认`，修正 laserType |
| 7 | 导航状态 | `is_nav_running_` 持续为 true，move_task feedback 正常 | `is_nav_running_` 为 false 但仍有 615005 | 状态不一致→`待确认`，核对 move_task 时序 |
| 8 | 复测 | 同一导航任务中 odom 差值稳定在阈值内，615005 不再出现 | 复测仍偶发 | 检查定位系统稳定性和 odom 频率 |

停止规则：

- 命中 `locatingOdom`/`currentOdom` 日志时，直接对比两个 odom 坐标差。
- odom topic 无消息时，先修复数据链，不分析阈值。
- 激光类型配置错误时，修正 laserType 后复测。
- 修复后同一导航任务全程无 615005 方可闭环。

现场确认命令：

```bash
# 确认 JState 原始上报
rostopic echo -n 1 /route/error

# 确认 odom topic 和定位 topic
rostopic info /algo/property/motion_odom_topic
rostopic info /vtr/localization

# 查看触发上下文（含 locatingOdom / currentOdom 坐标对比）
grep -B 10 -A 5 "locating muted for a long ride" /opt/jz/log/nav-net.log

# 确认激光类型
rosparam get /j3/jzhw/model/laser/laserType
```

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 定位卡死：`locating_odom_` 长期不变（日志中 locatingOdom 坐标连续多帧相同），`current_odom_` 持续增长 | 定位系统 `/vtr/localization`、`handlelocateStatusTopic` | 停止当前导航任务，触发定位重新初始化 | 修复定位系统（激光匹配、反光板数据、定位算法） | `locating_odom_` 随导航移动正常更新 |
| P1 | 里程计异常：`current_odom_` 数值跳变或不变，与 `locating_odom_` 差值异常大 | odom 传感器、`handleMotionOdomTopic`、ROS topic | 检查 odom 传感器状态，必要时切换到备用 odom 源 | 修复 odom 传感器驱动、标定或 topic 配置 | odom 数据平滑连续，无跳变 |
| P1 | laserType 配置错误：日志显示 `state` 为 "2d" 但实际为 3D 激光（或反之） | 机型配置 `/j3/jzhw/model` | 临时修正 laserType 参数 | 修正机型配置模板中的 laserType 字段 | 阈值与实际硬件匹配，不再误触发 |
| P2 | 导航反馈丢失：`is_nav_running_` 在导航中变为 false（`/vtr/move/feedback` 中断） | move_task 反馈、ROS 通信 | 检查 move_task 节点和 topic | 修复 move_task 的反馈发布稳定性 | 导航中 is_nav_running_ 持续为 true |
| P2 | kDefaultVal 阈值过小：特定场景（如高速行驶）下 10m/30m 阈值偏小 | 常量配置 | 临时调整阈值（需改代码编译） | 评估场景后调整 kDefaultVal2d/3d 常量 | 同场景不再误触发，且定位安全不受影响 |

不要通过关闭定位检查来规避。必须确认 odom 差距的原因是定位卡死、odom 传感器故障还是配置不匹配。

## 5 修复验证与证据索引

闭环需要同时满足：

1. 已确认 `locating_odom_` 和 `current_odom_` 中哪一方异常。
2. `/jstate/error/nav-net/locating_muted_for_a_long_ride` 不再上报 `trigger:true`。
3. 同一导航任务全程 odom 差值稳定在阈值内。
4. 定位系统持续提供有效更新（`locating_odom_` 跟随车辆移动变化）。

Agent 最少需要收集：

```text
错误时间及前后至少 120 秒的未过滤日志
/route/error 原始消息
locatingOdom 和 currentOdom 坐标序列对比
/vtr/localization 和 /algo/property/motion_odom_topic 的状态
laserType 配置值
nav-net 版本
修复后同场景复测结果
```

Agent 输出格式：

```yaml
error_code: 615005
error_name: locating_muted_for_a_long_ride
analysis_status: 待确认  # 已确认 / 高可能 / 待确认 / 已排除
applicable_version:
  primary_module: "nav-net"
  laser_type: ""  # "2d" or "3d"
trigger_path: "PositionRecover::setLoop() -> setLocatingMutedLost()"
trigger_stage: navigation  # 仅在导航模式下触发
confirmed_facts:
  - ""
most_likely_cause:
  cause: ""
  confidence: low
  evidence:
    - ""
excluded_causes: []
missing_evidence:
  - ""
next_action:
  - ""
temporary_action: ""
root_fix: ""
verification:
  result: not_started
  evidence:
    - ""
```

代码与数据证据：

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |
| JState key 定义 | `nav-net/include/common/health_info.hpp:63` → `kLocatingMutedLost` |
| 阈值常量：kDefaultVal2d=30, kDefaultVal3d=10 | `nav-net/controllers/position_recover.h:76-77` |
| 超时常量：kCheckTimeout=10s | `nav-net/controllers/position_recover.h:75` |
| odom 订阅和运算 | `position_recover.cc:505`（handleMotionOdomTopic）、`position_recover.cc:545`（setLoop 对比逻辑） |
| 触发调用 | `position_recover.cc:576-583` |
| 错误清除（HDI->clear） | `position_recover.cc:570` |
| 发布实现 | `nav-net/src/common/health_info.cpp:24` |

## 6 Agent 自动排查 Playbook

> 本章供 diagnosis-orchestrator 的确定性分析器自动执行。

```yaml
playbook:
  meta:
    error_code: "615005"
    error_name: "locating_muted_for_a_long_ride"
    module: "nav-net"
    time_window: 120

  steps:
    - id: classify_trigger_chain
      description: "确认 615005 触发，并区分 2D(30m) 还是 3D(10m) 阈值"
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "locating muted for a long ride:30m"
          on_match:
            trigger_chain: "muted_2d"
            conclusion: "2D 激光阈值 30m 触发，当前激光类型为 2d"
            goto: diagnose_muted_lost
        - type: grep_log
          module: "nav-net"
          pattern: "locating muted for a long ride:10m"
          on_match:
            trigger_chain: "muted_3d"
            conclusion: "3D 激光阈值 10m 触发，当前激光类型为 3d"
            goto: diagnose_muted_lost
        - type: on_no_match
          conclusion: "当前时间窗内未找到 locating muted 日志"
          action: expand_time_window
          time_window: 300

    - id: diagnose_muted_lost
      description: "沿 setLoop 链路排查：odom 对比 → 定位更新 → laserType 配置"
      checks:
        # 提取 locatingOdom 和 currentOdom 坐标对比
        - type: grep_log
          module: "nav-net"
          pattern: "locatingOdom"
          priority: P1
          context_lines: 2
          on_match:
            conclusion: "找到 locatingOdom 日志，可提取参考里程计坐标"
            continue: true
          on_no_match:
            conclusion: "无 locatingOdom 日志，可能 get_locating_odom_ 为 false"
            continue: true
        - type: grep_log
          module: "nav-net"
          pattern: "currentOdom"
          priority: P1
          context_lines: 2
          on_match:
            conclusion: "找到 currentOdom 日志，可对比里程计坐标差"
            continue: true
          on_no_match:
            conclusion: "无 currentOdom 日志，odom topic 可能无数据"
            root_cause: "odom topic /algo/property/motion_odom_topic 无消息"
            temp_fix: "检查 odom topic 发布者和传感器状态"
            goto: verify
        # 检查定位状态——locating_odom_ 是否更新
        - type: grep_log
          module: "nav-net"
          pattern: "locate miss match|5980|position.*valid"
          priority: P1
          on_match:
            conclusion: "定位验证失败（pose_valid=false 或 locate miss match），locating_odom_ 停止更新"
            root_cause: "定位系统验证失败，导致 locating_odom_ 冻结"
            temp_fix: "触发定位重新初始化或检查 /vtr/localization"
            goto: verify
          on_no_match:
            continue: true
        # 检查 laserType 配置
        - type: grep_log
          module: "nav-net"
          pattern: "state.*laserType|laserType"
          priority: P2
          on_match:
            conclusion: "laserType 日志存在，核对 2d/3d 与实际硬件是否一致"
            continue: true
          on_no_match:
            continue: true
        # 检查导航反馈
        - type: grep_log
          module: "nav-net"
          pattern: "handleMoveTaskFeedback|move_task"
          priority: P2
          on_match:
            conclusion: "move_task 反馈正常"
            continue: true
          on_no_match:
            conclusion: "move_task 反馈中断，is_nav_running_ 可能异常"
            continue: true
        - type: on_no_match
          conclusion: "odom 差值超过阈值但未找到明确根因，需核对 locating_odom_ 和 current_odom_ 的完整时间序列"
          status: insufficient_data
          action: "收集更长时段的 odom 坐标数据和定位状态日志"

    - id: verify
      description: "验证修复：同一导航任务中连续 120 秒不再出现定位静默"
      checks:
        - type: verify_fix
          grep_pattern: "locating muted for a long ride"
          watch_duration_sec: 120
          on_match:
            status: still_present
            action: "定位静默仍然存在，升级人工排查定位系统内部状态"
          on_no_match:
            status: verified
            conclusion: "连续 120 秒未出现定位静默，odom 差值稳定在阈值内"
```
