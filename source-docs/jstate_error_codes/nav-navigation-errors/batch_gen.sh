#!/bin/bash
D=/home/zhr/zhr_ws/src/mainbody/nav-manager/docs/jstate_error_codes/nav-navigation-errors
cnt=0
gen() {
    local code=$1 file="$D/$2" content="$3"
    echo "$content" > "$file"
    cnt=$((cnt+1))
    echo "  [$cnt] $code → $2"
}

# 615016: GPS_locate_timeout
gen 615016 615016-error_nav-net_GPS_locate_timeout.md '# JState 错误码 615016：使用GPS恢复定位超时

> 与 615015 同类，但用于 GPS/RTK 定位。`checkGPSLocatingRet()` 轮询 10s 等待 `localization_type == "rtk_MANUAL"` 且 `pose_valid == true`。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615016` |
| JState Key | `/jstate/error/nav-net/GPS_locate_timeout` |
| 错误描述 | 使用GPS恢复定位超时 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `checkGPSLocatingRet()` 中 `ros::Time::now() - start_time > kCheckTimeout(10s)`：每 0.2s 检查一次 `locate_ret_ > 0` 且 `localization_type == rtk_MANUAL` |
| 直接影响 | GPS 恢复失败，`usingGPS()` 返回 false |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：与 615015 对称——615015 检查 `laser_MANUAL`，615016 检查 `rtk_MANUAL`。两者的退出条件和超时逻辑一致。

## 2 触发流程

```mermaid
flowchart TD
    A[checkGPSLocatingRet] --> B[循环: sleep 0.2s]
    B --> C{locate_ret_ > 0?}
    C -- 否 --> D{超时 > 10s?}
    D -- 否 --> B
    D -- 是 --> E[LOGE 5983|GPS locate timeout]
    C -- 是 --> F{localization_type == rtk_MANUAL?}
    F -- 否 --> B
    F -- 是 --> G{pose_valid?}
    G -- false --> H[LOGE 5980|GPS locate miss match]
    G -- true --> I[return true]
    E --> J[pubJ3State kGPSLocateTimeout]
    J --> K[/route/error 615016]
```

```text
checkGPSLocatingRet()  @ position_recover.cc:442-467
  -> 轮询: sleep(0.2s), 定位类型必须为 rtk_MANUAL
  -> 超时: pubJ3State(kGPSLocateTimeout, 1, "使用GPS恢复定位超时")
```

## 3 排查

```bash
grep -E "GPS locate timeout|5983|rtk_MANUAL|checkGPSLocatingRet" /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 超时日志 | `5983|GPS locate timeout` | 无 | 非超时分支→检查 5980 |
| 2 | RTK 模式 | localization_type == rtk_MANUAL | 一直是其他类型 | RTK 模式未激活 |

## 4 原因与方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 |
|---|---|---|---|---|
| P1 | RTK 定位无响应：locate_ret_ 始终 0 | RTK 驱动、/vtr/localization | 重试或切换定位方式 | 修复 RTK 数据发布 |
| P1 | RTK 类型不匹配：类型非 rtk_MANUAL | 定位模式 | 确认 RTK 模式 | 修复模式切换 |

代码证据：JState key `health_info.hpp:113`，触发 `position_recover.cc:462`，kCheckTimeout=10s `position_recover.h:75`

## 5 Playbook

```yaml
playbook:
  meta: {error_code: "615016", error_name: "GPS_locate_timeout", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "GPS locate timeout"
          on_match: {goto: diagnose}
        - type: on_no_match: {action: expand_time_window, time_window: 120}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "rtk_MANUAL"; priority: P1
          on_match: {conclusion: "RTK 模式未匹配", continue: true}
          on_no_match: {conclusion: "RTK 模式从未激活", root_cause: "RTK 定位未启用", goto: verify}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "GPS locate timeout"; watch_duration_sec: 60
```'

# 615017: last_pose_invalid  
gen 615017 615017-error_nav-net_last_pose_invalid.md '# JState 错误码 615017：上一次保存的pose无效

> 当 `usingLastPose()` 从 `RSI->location_state_` 获取上一次保存位置后，调用 `locate(pose, "Dragging")` 验证失败时触发。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615017` |
| JState Key | `/jstate/error/nav-net/last_pose_invalid` |
| 错误描述 | 上一次保存的pose无效 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `usingLastPose()` 中 `locate(locate_pose, "Dragging")` 返回 false（定位验证失败或超时） |
| 直接影响 | `usingLastPose()` 返回 false，整体恢复定位失败 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`usingLastPose()` 是 `handleNavStarted` 的兜底——当调度未提供有效 PoseId（`pose_ID <= 0`）时使用。它从 `RSI->location_state_` 取上一次保存的位姿再走 `locate()` 验证。如果上次保存的位姿已过期或当前定位系统无法匹配，触发 615017。

## 2 触发流程

```mermaid
flowchart TD
    A[handleNavStarted] --> B{pose_ID > 0?}
    B -- 否 --> C[usingLastPose]
    C --> D[RSI->location_state_.get locate_pose]
    D --> E[locate locate_pose, Dragging]
    E --> F{checkRet 成功?}
    F -- 否 --> G[LOGE 5989|usingLastPose, invalid worldPose]
    G --> H[pubJ3State kLastPoseInvalid]
    H --> I[/route/error 615017]
```

```text
usingLastPose()  @ position_recover.cc:469-484
  -> RSI->location_state_.get(locate_pose)
  -> locate(locate_pose, "Dragging") → checkRet()
  -> pubJ3State(kLastPoseInvalid, 1, "上一次保存的pose无效")
```

## 3 排查

```bash
grep -E "usingLastPose|5989|last_pose_invalid" /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 触发日志 | `5989|usingLastPose, invalid worldPose` | 无 | 扩大时间窗 |
| 2 | location_state_ | 存在有效历史位姿 | 位姿数据为空或过期 | 需重新建立定位 |

## 4 原因与方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 |
|---|---|---|---|---|
| P1 | 上一次位姿过期：机器人已移动但未更新 `location_state_` | RSI 状态管理 | 使用有效 PoseId 手动恢复 | 确保定位更新时写入 location_state_ |
| P1 | 定位验证失败：位姿存在但 `checkRet()` 无法匹配 | 定位系统 | 重试或选择合适的恢复点 | 修复定位匹配算法 |

代码证据：JState key `health_info.hpp:61`，触发 `position_recover.cc:477`

## 5 Playbook

```yaml
playbook:
  meta: {error_code: "615017", error_name: "last_pose_invalid", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "5989|usingLastPose, invalid"
          on_match: {goto: diagnose}
        - type: on_no_match: {action: expand_time_window}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "5989|usingLastPose"; priority: P1; context_lines: 10
          on_match: {conclusion: "上次保存的位姿验证失败", continue: true}
        - type: grep_log; module: nav-net; pattern: "location_state_|get.*pose"; priority: P2
          on_match: {conclusion: "location_state_ 数据存在", continue: true}
          on_no_match: {conclusion: "location_state_ 无数据", root_cause: "无历史位姿", goto: verify}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "usingLastPose, invalid"; watch_duration_sec: 60
```'

echo "Done: $cnt docs"
