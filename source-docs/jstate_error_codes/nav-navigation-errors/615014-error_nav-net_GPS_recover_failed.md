# JState 错误码 615014：使用GPS恢复定位失败

> 文档用途：当 AI Agent 在现场日志中发现 `615014` 时，用本文理解 GPS 定位恢复流程，判断失败在 checkGPSLocatingRet 超时还是异常中断。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615014` |
| JState Key | `/jstate/error/nav-net/GPS_recover_failed` |
| 错误描述 | 使用GPS恢复定位失败 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `usingGPS()` 中 `checkGPSLocatingRet()` 抛出异常（通常为定位系统不可达） |
| 直接影响 | GPS 恢复失败，`usingGPS` 返回 false；若 lasermark 也失败则整体恢复失败 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | `robot_info_["laserType"] == "3d"`（仅 3D 激光机型走 GPS 恢复） |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`615014`（GPS 恢复失败，异常中断）与 `615016`（GPS 定位超时）的区别：615014 是 `checkGPSLocatingRet()` 本身抛出异常导致 `try-catch` 捕获，615016 是轮询循环中时间超过 `kCheckTimeout=10s` 而正常退出。

## 2 错误触发的功能流程

```mermaid
flowchart TD
    A[usingGPS] --> B[try_lock locate_lock_]
    B -- 失败 --> C[LOGE 5987, return false]
    B -- 成功 --> D[locate_process_=true, locate_ret_=0]
    D --> E[try: checkGPSLocatingRet]
    E --> F{checkGPSLocatingRet 正常?}
    F -- 抛出异常 --> G[pubJ3State kGPSRecoverFailed]
    F -- 正常返回 --> H{返回值?}
    H -- false --> I[615016: GPS_locate_timeout]
    H -- true --> J[GPS 恢复成功]
    G --> K[/route/error 615014]
```

```text
PositionRecover::usingGPS()              @ position_recover.cc:341
  -> locate_lock_.try_lock() 失败 → "5987|usingGPS failed"
  -> try: checkGPSLocatingRet()
  -> catch: LOGE "GPS recover position failed"
  -> HDI->pubJ3State(kGPSRecoverFailed, 1, "使用GPS恢复定位失败")
```

## 3 结合日志选择排查方向

```bash
grep -E "GPS recover|GPS.*failed|usingGPS|checkGPSLocatingRet|GPS locate timeout"   /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 触发分支 | `GPS recover position failed` + 异常信息 | 仅有 `GPS locate timeout`（615016） | 异常 vs 超时→区分根因 |
| 2 | RTK 定位状态 | `/vtr/localization` 中 localization_type == "rtk_MANUAL" | 定位类型不匹配 | RTK 模式未启用→`已确认` |
| 3 | laserType 配置 | `robot_info_["laserType"]=="3d"` | 非 3d 但走了 GPS 恢复 | 配置错误→`已确认` |

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | GPS/RTK 定位系统不可达：异常包含网络/服务信息 | RTK 定位服务、ROS 通信 | 重试或切换到其他定位方式 | 修复 RTK 定位服务可用性 | RTK 定位恢复成功 |
| P1 | 定位锁定冲突：`5987|usingGPS failed` | locate_lock_ | 等待其他定位完成后重试 | 优化定位调用互斥机制 | 不再出现并发 |

## 5 代码证据

| 证据 | 位置 |
|---|---|
| JState key | `health_info.hpp:117` → `kGPSRecoverFailed` |
| 触发调用 | `position_recover.cc:356` |
| checkGPSLocatingRet | `position_recover.cc:442-467` |

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615014"
    error_name: "GPS_recover_failed"
    module: "nav-net"
    time_window: 120
  steps:
    - id: classify_trigger_chain
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "GPS recover position failed"
          on_match:
            goto: diagnose_GPS_recover_failed
        - type: on_no_match:
            action: expand_time_window
            time_window: 300
    - id: diagnose_GPS_recover_failed
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "GPS recover position failed"
          priority: P1
          context_lines: 10
          on_match:
            conclusion: "GPS 恢复异常，检查异常信息中的具体原因"
            continue: true
        - type: grep_log
          module: "nav-net"
          pattern: "5987|usingGPS failed"
          priority: P1
          on_match:
            conclusion: "locate_lock_ 被占用，并发定位冲突"
            root_cause: "并发定位调用"
            goto: verify
    - id: verify
      checks:
        - type: verify_fix
          grep_pattern: "GPS recover position failed"
          watch_duration_sec: 120
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
