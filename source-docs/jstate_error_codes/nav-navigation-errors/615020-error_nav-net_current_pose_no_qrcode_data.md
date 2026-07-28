# JState 错误码 615020：当前位置无二维码数据

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615020` |
| JState Key | `/jstate/error/nav-net/current_pose_no_qrcode_data` |
| 错误描述 | 当前位置无二维码数据 |
| 等级 | `level5`（ERROR） |
| 直接触发条件 | `onToggleNav()` 中 `getStartPose()` 返回的 `start_pose.qrcode_ID < 0`——机器人当前位置无法关联到任何二维码矩阵区域 |
| 触发源码 | `qrcode_servo.cc:356` |

```mermaid
flowchart TD
    A[onToggleNav: 启动导航] --> B[getStartPose rest_path]
    B --> C{返回的 start_pose.qrcode_ID}
    C -- "< 0" --> D[LOGE 5991|current pose no qrcode data]
    D --> E[pubJ3State kCurrentPoseNoQrcodeData, level5]
    E --> F[/route/error 615020 ERROR]
    C -- ">= 0" --> G[正常获取二维码区域]
```

```text
onToggleNav() @ qrcode_servo.cc:349-359
  -> start_pose = getStartPose(rest_path)
  -> if start_pose.qrcode_ID < 0
  -> pubJ3State(kCurrentPoseNoQrcodeData, 5, "当前位置无二维码数据")
```

getStartPose() 优先从剩余路径中找有 qrcode_ID 的点（`qrcode_ID >= 0`），找不到则用 nearbyPose 搜 2m 内最近点。两个都失败时返回 qrcode_ID < 0 的 start_pose。

| P1 | 当前位置无二维码覆盖 | rest_path 路径点、地图 | 移动机器人到二维码区域 | 确保地图覆盖全部作业区域 |
| P1 | 定位错误：机器人实际位置与地图不符 | updateTf | 检查 map→base_footprint tf | 修复定位 |

代码证据：JState key `health_info.hpp:107`，触发 `qrcode_servo.cc:356`

```yaml
playbook:
  meta: {error_code: "615020", error_name: "current_pose_no_qrcode_data", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "5991|current pose no qrcode data"
          on_match: {goto: diagnose}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "getStartPose|can't get current location|can't find closest pose"; priority: P1
          on_match: {conclusion: "定位或附近无有效点", continue: true}
        - type: grep_log; module: nav-net; pattern: "5991|current pose no qrcode data"; priority: P1; context_lines: 10
          on_match: {conclusion: "当前位姿无关联二维码", root_cause: "当前位置不在二维码覆盖范围内"}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "5991|current pose no qrcode data"; watch_duration_sec: 60
```
