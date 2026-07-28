# JState 错误码 615022：无法找到最近的点位

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615022` |
| JState Key | `/jstate/error/nav-net/cannot_find_closest_pose` |
| 错误描述 | 无法找到最近的点位 |
| 等级 | `level5`（ERROR） |
| 直接触发条件 | `getStartPose()` 中剩余路径无 qrcode_ID≥0 的点后，兜底调用 `nearbyPose()` 在 2m 范围内搜索失败 |
| 触发源码 | `qrcode_servo.cc:1009` |

**核心判断**：`getStartPose()` 两步策略：先查剩余路径中有二维码的节点 → 都失败则 `nearbyPose(limit=true, distance=2)` 搜 2m 内最近点 → 仍失败触发此错误。需要在 2m 内存在一个已注册二维码的地图节点。

```mermaid
flowchart TD
    A[getStartPose] --> B[遍历 rest_path 找 qrcode_ID>=0]
    B -- 全部不满足 --> C[nearbyPose limit=true distance=2m]
    C -- 失败 --> D[LOGE 5994|can't find closest pose]
    D --> E[pubJ3State kCannotFindClosestPose, level5]
```

| P1 | 2m 内无地图节点 | 地图覆盖 | 移动机器人 | 扩展地图覆盖 |
| P1 | 地图数据未加载 | getNewMapData | 重新加载地图 | 修复加载 |

代码证据：JState key `health_info.hpp:103`，触发 `qrcode_servo.cc:1009`

```yaml
playbook:
  meta: {error_code: "615022", error_name: "cannot_find_closest_pose", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "5994|can't find closest pose"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "5994|can't find closest pose"; priority: P1; context_lines: 10; on_match: {conclusion: "nearbyPose 2m 內无节点", root_cause: "附近无地图节点", goto: verify}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "5994|can't find closest pose"; watch_duration_sec: 60}]
```
