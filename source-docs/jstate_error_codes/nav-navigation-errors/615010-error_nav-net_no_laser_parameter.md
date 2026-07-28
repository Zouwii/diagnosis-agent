# JState 错误码 615010：无法获得激光参数信息

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615010` |
| JState Key | `/jstate/error/nav-net/no_laser_parameter` |
| 错误描述 | 无法获得激光参数信息 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `hasBackNav()` 中 `ros::param::get("/j3/jzhw/model/laser")` 返回失败（参数不存在） |
| 触发源码 | `laser_view.cc:665` |

**核心判断**：615009 和 615010 是 `hasBackNav()` 的互斥分支：参数获取失败→615010，参数存在但类型错误→615009。

```text
hasBackNav() @ laser_view.cc:655-672
  -> ros::param::get("/j3/jzhw/model/laser", param_data)
  -> 失败 → LOGE "Failed to get parameter data." → pubJ3State(kNoLaserParam)
```

| P1 | 参数缺失 | 机型配置 | 补充配置 | 修复配置下发 |

代码证据：JState key `health_info.hpp:49`，触发 `laser_view.cc:665`

```yaml
playbook:
  meta: {error_code: "615010", error_name: "no_laser_parameter", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "Failed to get parameter data"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "Failed to get parameter data"; priority: P1; on_match: {conclusion: "param 不存在", root_cause: "/j3/jzhw/model/laser 缺失"}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "Failed to get parameter data"; watch_duration_sec: 60}]
```
