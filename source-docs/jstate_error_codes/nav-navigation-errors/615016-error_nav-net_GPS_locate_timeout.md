# JState 错误码 615016：使用GPS恢复定位超时

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
```
