# JState 错误码 615018：获取任务剩余路线失败

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615018` |
| JState Key | `/jstate/error/nav-net/no_rest_path` |
| 错误描述 | 获取任务剩余路线失败 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `QrcodeServo::getRestPath()` 中查找 `dest_id` 对应的 `nodes_info_` 节点时抛出异常（nodes_info_ 数据异常或 dest_id 不存在） |
| 触发源码 | `qrcode_servo.cc:303` |

```mermaid
flowchart TD
    A[QrcodeServo::getRestPath] --> B[nodes_info_ 中 find_if dest_id]
    B -- 异常 --> C[LOGE 获取任务剩余路线失败 + e.what]
    C --> D[pubJ3State kNoRestPath]
    D --> E[/route/error 615018]
```

```text
getRestPath() @ qrcode_servo.cc:303
  -> find_if(node_info.id == dest_id)
  -> catch std::exception → pubJ3State(kNoRestPath, 1, "获取任务剩余路线失败")
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| P1 | nodes_info_ 异常 | 数据正确 | dest_id 不在列表中 | 检查地图和路径数据 |

代码证据：JState key `health_info.hpp:111`，触发 `qrcode_servo.cc:303`

```yaml
playbook:
  meta: {error_code: "615018", error_name: "no_rest_path", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "获取任务剩余路线失败"
          on_match: {goto: diagnose}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "获取任务剩余路线失败"; priority: P1; context_lines: 10
          on_match: {conclusion: "nodes_info_ 或 dest_id 异常", root_cause: "地图数据或任务路径不匹配"}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "获取任务剩余路线失败"; watch_duration_sec: 60
```
