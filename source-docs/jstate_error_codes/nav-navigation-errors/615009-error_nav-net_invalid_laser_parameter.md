# JState 错误码 615009：无效激光参数类型

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615009` |
| JState Key | `/jstate/error/nav-net/invalid_laser_parameter` |
| 错误描述 | 无效激光参数类型 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `LaserView::hasBackNav()` 中 `ros::param::get("/j3/jzhw/model/laser")` 获取成功但类型不是 `TypeStruct` |
| 触发源码 | `laser_view.cc:672` |

**核心判断**：param 返回值类型非法（不是预期的结构体），说明参数配置格式有误。

```text
hasBackNav() @ laser_view.cc:665-672
  -> ros::param::get("/j3/jzhw/model/laser", param_data)
  -> 失败 → 615010 (no_laser_parameter)
  -> 成功但类型非 TypeStruct → 615009 (invalid_laser_parameter)
  -> have_back_laser_ = false
```

| P1 | 参数类型错误 | 机型配置 | 修正 JSON 格式 | 修复配置 |

代码证据：JState key `health_info.hpp:51`，触发 `laser_view.cc:672`

```yaml
playbook:
  meta: {error_code: "615009", error_name: "invalid_laser_parameter", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "Invalid parameter data type"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "Invalid parameter data type"; priority: P1; context_lines: 5; on_match: {conclusion: "param 类型非 TypeStruct", root_cause: "/j3/jzhw/model/laser 格式错误"}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "Invalid parameter data type"; watch_duration_sec: 60}]
```
