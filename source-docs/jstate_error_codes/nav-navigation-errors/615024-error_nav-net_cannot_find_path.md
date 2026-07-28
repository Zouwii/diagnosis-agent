# JState 错误码 615024：搜路结果为空

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615024` |
| JState Key | `/jstate/error/nav-net/cannot_find_path` |
| 错误描述 | 搜路结果为空 |
| 等级 | `level5`（ERROR） |
| 直接触发条件 | 二维码检码任务中 `check.data.size() == 0`——从当前点到目标点的路径规划返回空结果 |
| 触发源码 | `qrcode_servo.cc:593` |

**核心判断**：在二维码检码流程中，需要从当前位置规划到待检二维码的路径。如果 `check.data` 为空（搜路失败），直接报 ERROR。注意 `check` 来自二维码检码任务数据。

| P1 | 路径不可达 | 路径规划 | 检查起点到目标的可达性 | 修复地图连通性或路径规划 |
| P1 | 起点/目标无效 | check.data 输入 | 确认起点和目标点位 | 修复检码任务数据 |

代码证据：JState key `health_info.hpp:99`，触发 `qrcode_servo.cc:593`

```yaml
playbook:
  meta: {error_code: "615024", error_name: "cannot_find_path", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "搜路结果为空"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "搜路结果为空"; priority: P1; context_lines: 10; on_match: {conclusion: "路径规划返回空", root_cause: "路径不可达或输入无效", goto: verify}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "搜路结果为空"; watch_duration_sec: 60}]
```
