# JState 错误码 615015：定位有效性检测超时

> 文档用途：当 AI Agent 在现场日志中发现 `615015` 时，用本文理解 `checkRet()` 轮询机制，判断定位系统在 10s 内无响应的原因。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615015` |
| JState Key | `/jstate/error/nav-net/check_pose_vaild_timeout` |
| 错误描述 | 定位有效性检测超时 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `checkRet()` 轮询循环中 `ros::Time::now() - start_time > kCheckTimeout(10s)`，且期间未收到匹配的定位确认 |
| 直接影响 | `locate()` 返回 false，导致定位恢复失败（615011） |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`checkRet()` 每 0.5s 轮询一次 `locate_ret_`（由 `handlelocatingStatusTopic` 回调累加）。退出条件：
1. `is_tag_localization_` == true → 成功返回
2. `localization_type == laser_MANUAL && pose_valid == true` → 成功返回  
3. `localization_type == laser_MANUAL && pose_valid == false` → "locate miss match" 失败返回
4. 超时 10s → 触发 615015

## 2 错误触发的功能流程

```mermaid
flowchart TD
    A[locate pose, Dragging] --> B[checkRet]
    B --> C[循环: sleep 0.5s]
    C --> D{is_tag_localization_?}
    D -- true --> E[return true 成功]
    D -- false --> F{locate_ret_ > 0?}
    F -- 否 --> G{超时 > 10s?}
    G -- 否 --> C
    G -- 是 --> H[LOGE 5983|timeout]
    H --> I[pubJ3State kCheckPoseVaildTimeout]
    I --> J[/route/error 615015]
    I --> K[return false]
    F -- 是 --> L{localization_type == laser_MANUAL?}
    L -- 否 --> C
    L -- 是 --> M{pose_valid?}
    M -- false --> N[5980|locate miss match, return false]
    M -- true --> O[return true 成功]
```

```text
checkRet()  @ position_recover.cc:412-440
  -> 轮询: sleep(0.5s), 检查 locate_ret_ (handlelocatingStatusTopic 累加)
  -> 超时: ros::Time::now() - start_time > kCheckTimeout(10s)
  -> pubJ3State(kCheckPoseVaildTimeout, 1, "定位有效性检测超时")
```

## 3 结合日志选择排查方向

```bash
grep -E "5983|timeout|checkRet|check_pose_vaild_timeout|locate_ret"   /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 超时日志 | `5983|timeout` | 无 | 非超时分支→检查 5980 或 Tag 分支 |
| 2 | locate_ret_ 计数 | `locate_ret_` 日志显示持续增长 | 始终为 0 | `/vtr/localization` topic 无消息→`已确认` |
| 3 | localization_type | 类型变为 laser_MANUAL | 一直是其他类型 | 激光定位模式未切换成功→`高可能` |

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 定位系统无响应：`locate_ret_` 始终为 0，/vtr/localization 无消息 | `/vtr/localization` topic、定位驱动 | 检查定位 topic | 修复定位系统启动和数据发布 | 定位消息持续更新 |
| P1 | 定位类型未匹配：`locate_ret_` 增长但 localization_type 不是 laser_MANUAL | 定位模式切换 | 确认激光定位模式 | 修复模式切换逻辑 | 类型变为 laser_MANUAL |
| P2 | kCheckTimeout 过小：正常定位需要更长时间 | 常量配置 | 评估后调整 | 按场景调整 kCheckTimeout | 不再超时且定位准确 |

| 证据 | 位置 |
|---|---|
| JState key | `health_info.hpp:115` |
| 触发调用 | `position_recover.cc:435` |
| kCheckTimeout=10s | `position_recover.h:75` |

## 5 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615015"
    error_name: "check_pose_vaild_timeout"
    module: "nav-net"
    time_window: 60
  steps:
    - id: classify_trigger_chain
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "5983|timeout"
          on_match:
            goto: diagnose_check_pose_vaild_timeout
        - type: on_no_match:
            action: expand_time_window
    - id: diagnose_check_pose_vaild_timeout
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "locate_ret_|locating_status"
          priority: P1
          context_lines: 5
          on_match:
            conclusion: "定位响应存在，检查类型是否匹配 laser_MANUAL"
            continue: true
          on_no_match:
            conclusion: "locate_ret_ 无输出，/vtr/localization 可能无消息"
            root_cause: "定位系统无响应"
            goto: verify
        - type: grep_log
          module: "nav-net"
          pattern: "5980|locate miss match"
          priority: P1
          on_match:
            conclusion: "定位类型不匹配或 pose_valid=false"
            root_cause: "定位类型不是 laser_MANUAL"
            goto: verify
    - id: verify
      checks:
        - type: verify_fix
          grep_pattern: "5983|timeout"
          watch_duration_sec: 60
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
