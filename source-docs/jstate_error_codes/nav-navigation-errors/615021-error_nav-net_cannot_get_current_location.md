# JState 错误码 615021：无法获取当前位置

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615021` |
| JState Key | `/jstate/error/nav-net/cannot_get_current_location` |
| 错误描述 | 无法获取当前位置 |
| 等级 | `level5`（ERROR） |
| 直接触发条件 | `getStartPose()` 中 `RSI->updateTf("map", "base_footprint", ...)` 失败——无法获取 map 坐标系下机器人位姿 |
| 触发源码 | `qrcode_servo.cc:956` |

**核心判断**：这是二维码导航启动的第一个检查——必须知道机器人在 map 下的位置才能查找起始二维码。如果 tf 树中 `map → base_footprint` 变换不可用，直接报 ERROR。

```mermaid
flowchart TD
    A[getStartPose] --> B[RSI->updateTf map→base_footprint]
    B -- 失败 --> C[LOGE 5992|can't get current location]
    C --> D[pubJ3State kCannotGetCurrentLocation, level5]
    D --> E[/route/error 615021]
```

| P1 | tf 树断裂 | tf、定位 | 检查 tf 树 | 修复定位发布 map→base_footprint |
| P1 | 定位未初始化 | 定位系统 | 等待定位就绪 | 确保定位初始化完成后再启动导航 |

代码证据：JState key `health_info.hpp:105`，触发 `qrcode_servo.cc:956`

```yaml
playbook:
  meta: {error_code: "615021", error_name: "cannot_get_current_location", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "5992|can't get current location"
          on_match: {goto: diagnose}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "5992|can't get current location"; priority: P1; context_lines: 10
          on_match: {conclusion: "tf map→base_footprint 不可用", root_cause: "定位或 tf 异常", goto: verify}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "5992|can't get current location"; watch_duration_sec: 60
```
