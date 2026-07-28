# JState 错误码 615008：无法获取有效激光列表

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615008` |
| JState Key | `/jstate/error/nav-net/no_vaild_lasers` |
| 错误描述 | 无法获取有效激光列表 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `LaserView` 激光数据处理中 ValidLasers 为空——没有可用的激光传感器数据 |
| 触发源码 | `laser_view.cc:256` |

```mermaid
flowchart TD
    A[LaserView 处理激光请求] --> B{能获取 ValidLasers?}
    B -- 否 --> C[LOGE can not get ValidLasers!]
    C --> D[pubJ3State kNoValidLaser, level1]
    D --> E[/route/error 615008]
```

| P1 | 激光传感器离线 | 激光驱动 | 检查传感器连接 | 修复驱动 |
| P1 | 激光配置丢失 | ROS param | 检查参数 | 修复配置下发 |

代码证据：JState key `health_info.hpp:53`，触发 `laser_view.cc:256`

```yaml
playbook:
  meta: {error_code: "615008", error_name: "no_vaild_lasers", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "can not get ValidLasers!"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "ValidLasers|laser"; priority: P1; context_lines: 5; on_match: {conclusion: "激光传感器异常", root_cause: "激光驱动或配置异常"}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "can not get ValidLasers!"; watch_duration_sec: 60}]
```
