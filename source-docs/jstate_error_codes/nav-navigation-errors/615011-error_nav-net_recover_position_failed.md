# JState 错误码 615011：无法正确恢复定位

> 文档用途：当 AI Agent 在现场日志中发现 `615011` 时，用本文理解 lasermark 定位恢复流程，判断失败发生在定位调用、定位验证还是超时阶段。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615011` |
| JState Key | `/jstate/error/nav-net/recover_position_failed` |
| 错误描述 | 无法正确恢复定位（lasermark 模式） |
| 等级 | `level1`（WARN）。通过 `pubJ3State` 发布 `trigger:true`，无专门的 `pubJ3StateFalse` 调用。 |
| 直接触发条件 | `handleNavStarted()` 中 `from == "lasermark"` 时，`locate(result_pose, "Dragging")` 返回 false |
| 直接影响 | 定位恢复失败，`location_valid_` 设为 false，`res.success = false`；容差降为 `kSafeTol=5` 以允许短距离运行 |
| 自动恢复条件 | 后续成功的定位恢复覆盖。无自动清除；下一次 `HDI->clear()` 可清除。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 调度系统下发 `From=lasermark` 的导航启动请求 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`615011` 只在 lasermark（反光板）恢复模式下触发。`locate(result_pose, "Dragging")` 内部调用 `checkRet()`，在 10 秒（`kCheckTimeout`）内轮询验证定位有效性。失败原因有三：定位类型不匹配（不是 `laser_MANUAL`）、`pose_valid=false`、或超时。三者通过不同的日志代码区分。

本文使用以下证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | 源码和日志代码可证明触发分支 |
| `高可能` | 特征与某一分支吻合但缺定位内部日志 |
| `待确认` | 当前只能作为排查方向 |

## 2 错误触发的功能流程

进入该错误链的前置条件：

1. 调度系统下发 `From=lasermark` 的导航启动请求
2. `req_msg` 中包含 `Pose` 字段（反光板重定位给出的 pose）
3. `locate_lock_` 未被其他定位操作占用

```mermaid
flowchart TD
    A[handleNavStarted] --> B{req_msg 包含 From?}
    B -- "From=lasermark" --> C{req_msg 包含 Pose?}
    C -- 否 --> D[跳过定位, 走 usingPose/usingLastPose]
    C -- 是 --> E[getJsonPose 解析 result_pose]
    E --> F[locate result_pose, Dragging]
    F --> G[获取 locate_lock_]
    G --> H[RSI->locate 发起定位]
    H --> I[checkRet 轮询 10s]
    I --> J{is_tag_localization_?}
    J -- true --> K[Tag 定位成功, return true]
    J -- false --> L{locate_ret_ > 0?}
    L -- 否 --> M{超时 > kCheckTimeout?}
    M -- 否 --> N[睡眠0.5s, 继续轮询]
    N --> I
    M -- 超时 --> O[615015: checkPoseVaildTimeout]
    L -- 是 --> P{localization_type == laser_MANUAL?}
    P -- 否 --> N
    P -- 是 --> Q{pose_valid?}
    Q -- false --> R[LOGE 5980|locate miss match]
    Q -- true --> S[定位成功, return true]
    R --> T[locate 返回 false]
    O --> T
    T --> U[pubJ3State kRecoverPositionFailed]
    U --> V[/route/error 615011]
    U --> W[location_valid_ = false]
    U --> X[localize_failure_tolorence_ = kSafeTol=5]
```

对应调用链：

```text
PositionRecover::handleNavStarted()              @ position_recover.cc:45
  -> from == "lasermark"
  -> RSI->getJsonPose(req_msg["Pose"], result_pose)
  -> locate(result_pose, "Dragging")             @ :386
  -> checkRet()                                  @ :412
  -> 轮询循环：sleep(0.5s), 检查 locate_ret_ > 0
  -> 超时或类型不匹配 → return false
  -> HDI->pubJ3State(kRecoverPositionFailed, 1, "无法正确恢复定位")  @ :95
```

错误生命周期：

```text
触发 pubJ3State(trigger:true, level:1) → /route/error 发布
  -> location_valid_ = false
  -> localize_failure_tolorence_ = kSafeTol=5（限制后续移动范围）
  -> 下一次 setLoop: HDI->clear() → 清除
  -> 后续成功的 locate 重新设置 location_valid_=true
```

关联错误的时序解释：

| 时序或组合 | 优先判断 |
|---|---|
| `615011` + `615015`（定位有效性检测超时）同时出现 | 定位轮询超时是直接原因，优先排查定位系统为何 10 秒内无响应 |
| `615011` + `615035`（反光板重定位失败）先出现 | 反光板数据或重定位算法先失败，lasermark 恢复在后 |
| `615011` 单独出现（未超时） | 定位类型不匹配（非 laser_MANUAL）或 pose_valid=false |

## 3 结合日志选择排查方向

```bash
grep -E "PositionRecover|locate|5980|5983|5987|lasermark|Dragging|recover_position_failed"   /opt/jz/log/nav-net.log | tail -n 500
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间与版本 | JState、日志属于同一时间窗 | 不一致 | 标记`待确认` |
| 2 | 触发分支 | 找到 `5983|timeout` 或 `5980|locate miss match` 日志 | 无分支日志，仅有 `PositionRecover failed` | 分支不明→`待确认`，扩大时间窗 |
| 3 | 超时分支(5983) | `checkRet` 在 10s 内完成 | 出现 `5983|timeout` | 定位系统响应慢或无响应→`高可能` |
| 4 | 类型不匹配(5980) | `locating_status_.localization_type == laser_MANUAL` | `5980|locate miss match`（pose_valid=false） | 定位类型不符合预期→`已确认` |
| 5 | 锁定冲突(5987) | `locate_lock_` 获取成功 | `5987|another locate is under going` | 并发定位调用→`高可能`，检查调用时序 |
| 6 | 上游反光板数据 | lasermark pose 通过 onRelocate 获取成功 | onRelocate 本身失败（615034/615035） | 上游反光板链失败，415011 为后续表现 |
| 7 | 复测 | 同一 lasermark pose 恢复成功 | 复测仍失败 | 检查激光/反光板数据一致性和定位算法 |

停止规则：
- 命中 `5980` 时，定位类型不匹配是直接原因，不先怀疑激光数据。
- 命中 `5983` 时，检查定位系统响应（/vtr/localization），不先修改 kCheckTimeout。
- 上游 615034/615035 先出现时优先排查反光板链路。

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 定位超时：日志出现 `5983|timeout`，定位系统 10 秒内未确认有效位姿 | 定位系统 `/vtr/localization`、`checkRet` 轮询 | 重试定位恢复或手动指定起点 | 修复定位系统响应速度或增加超时容忍 | 同场景定位在 10s 内完成 |
| P1 | 定位类型不匹配：日志出现 `5980|locate miss match`，`localization_type != laser_MANUAL` 或 `pose_valid=false` | 定位类型切换、laser 模式配置 | 确认激光定位模式已激活后重试 | 修复定位模式切换逻辑或激光定位参数 | localization_type 持续为 laser_MANUAL |
| P1 | 并发定位冲突：日志出现 `5987|another locate is under going` | locate_lock_ 互斥 | 等待前一次定位完成后重试 | 修复定位调用的互斥或排队机制 | 不再出现并发调用报错 |
| P2 | lasermark pose 本身无效：onRelocate 给出的 result_pose 不合理 | 反光板数据、loadLasermark | 检查反光板地图数据完整性 | 修复反光板地图或重定位算法 | 相同反光板 pose 恢复成功 |

## 5 修复验证与证据索引

闭环需要同时满足：
1. 已确认触发分支为超时、类型不匹配还是并发冲突。
2. `/jstate/error/nav-net/recover_position_failed` 不再出现。
3. `location_valid_` 置为 true，`localize_failure_tolorence_` 恢复为 `kDefaultTol=50`。

```yaml
error_code: 615011
error_name: recover_position_failed
analysis_status: 待确认
trigger_path: "handleNavStarted() -> locate() -> checkRet()"
confirmed_facts: []
most_likely_cause:
  cause: ""
  confidence: low
  evidence: []
missing_evidence: []
next_action: []
temporary_action: ""
root_fix: ""
verification:
  result: not_started
```

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |
| JState key | `nav-net/include/common/health_info.hpp:59` → `kRecoverPositionFailed` |
| 触发调用 | `position_recover.cc:95` |
| locate/checkRet 实现 | `position_recover.cc:386-440` |
| 超时常量 kCheckTimeout=10s | `position_recover.h:75` |
| 容差常量 kDefaultTol=50, kSafeTol=5 | `position_recover.h:72,74` |

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615011"
    error_name: "recover_position_failed"
    module: "nav-net"
    time_window: 120

  steps:
    - id: classify_trigger_chain
      description: "区分 615011 的触发分支：超时 vs 类型不匹配 vs 并发冲突"
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "recover_position_failed|PositionRecover failed"
          on_match:
            trigger_chain: "recover_failed_confirmed"
            conclusion: "命中定位恢复失败"
            goto: diagnose_recover_position_failed
        - type: on_no_match
          conclusion: "未找到触发日志"
          action: expand_time_window
          time_window: 300

    - id: diagnose_recover_position_failed
      description: "按三种分支排查：超时(5983) → 类型不匹配(5980) → 并发冲突(5987)"
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "5983|timeout"
          priority: P1
          on_match:
            conclusion: "定位检测超时（kCheckTimeout=10s），定位系统 10s 内未确认有效位姿"
            root_cause: "定位系统响应超时"
            temp_fix: "重试定位恢复或检查 /vtr/localization"
            goto: verify
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-net"
          pattern: "5980|locate miss match"
          priority: P1
          on_match:
            conclusion: "定位类型不匹配或 pose_valid=false（非 laser_MANUAL）"
            root_cause: "定位类型不符合 laser_MANUAL 或位姿无效"
            temp_fix: "确认激光定位模式已激活"
            goto: verify
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-net"
          pattern: "5987|another locate is under going"
          priority: P1
          on_match:
            conclusion: "并发定位调用冲突（locate_lock_ 被占用）"
            root_cause: "并发定位调用"
            temp_fix: "等待前一次定位完成后重试"
            goto: verify
          on_no_match:
            continue: true
        - type: grep_log
          module: "nav-net"
          pattern: "lLmRelocationFailed|反光板重定位失败"
          priority: P2
          on_match:
            conclusion: "上游反光板重定位失败，lasermark 恢复后续触发 615011"
            root_cause: "反光板数据或重定位算法失败"
            temp_fix: "优先排查 615034/615035"
            goto: verify
          on_no_match:
            continue: true
        - type: on_no_match
          conclusion: "定位恢复失败但无明显分支特征"
          status: insufficient_data

    - id: verify
      description: "验证修复"
      checks:
        - type: verify_fix
          grep_pattern: "recover_position_failed|PositionRecover failed"
          watch_duration_sec: 120
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
