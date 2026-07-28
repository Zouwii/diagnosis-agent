# JState 错误码 615019：地图信息读取错误

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615019` |
| JState Key | `/jstate/error/nav-net/get_map_info_failed` |
| 错误描述 | 地图信息读取错误 |
| 等级 | `level5`（ERROR）。触发态最多 3 次后静默 |
| 直接触发条件 | 三个触发点：1) `onToggleNav()` 中 `loadMapInfo(area_name)` 返回 false（读取地图文件失败）2) 同上，首次切换二维码区域 3) `getStartPose()` 中 `nodes_info_` 为空 |
| 触发源码 | `qrcode_servo.cc:371,381,963` |

```mermaid
flowchart TD
    A[onToggleNav: 二维码区域切换] --> B{loadMapInfo area_name 成功?}
    B -- 否 --> C[LOGE 地图读取错误]
    C --> D[pubJ3State kGetMapInfoFailed, level5]
    A2[getStartPose] --> E{nodes_info_ 为空?}
    E -- 是 --> F[LOGE get map info failed]
    F --> D
    D --> G[/route/error 615019 ERROR]
```

```text
触发点1&2: qrcode_servo.cc:371,381
  -> loadMapInfo(area_name) 返回 false
  -> pubJ3State(kGetMapInfoFailed, 5, "地图信息读取错误...")

触发点3: qrcode_servo.cc:963
  -> nodes_info_.empty()
  -> pubJ3State(kGetMapInfoFailed, 5, "地图点位为空...")
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 分支区分 | loadMapInfo 成功 | 地图文件读取失败 | 检查文件 |
| 2 | nodes_info_ | 非空 | 为空 | 重新加载地图 |

| P1 | 地图文件不可读 | loadMapInfo/地图存储 | 恢复地图文件 | 修复文件路径或格式 |
| P1 | nodes_info_ 未加载 | getNewMapData | 重新加载地图 | 修复加载逻辑 |

代码证据：JState key `health_info.hpp:109`，触发 `qrcode_servo.cc:371,381,963`

```yaml
playbook:
  meta: {error_code: "615019", error_name: "get_map_info_failed", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "地图读取错误|地图点位为空"
          on_match: {goto: diagnose}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "地图点位为空"; priority: P1
          on_match: {conclusion: "nodes_info_ 为空", root_cause: "地图数据未加载", goto: verify}
        - type: grep_log; module: nav-net; pattern: "地图读取错误"; priority: P1
          on_match: {conclusion: "地图文件加载失败", root_cause: "地图文件不可读", goto: verify}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "地图读取错误|地图点位为空"; watch_duration_sec: 60
```
