# JState 错误码 615036：未知机型

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615036` |
| JState Key | `/jstate/error/nav-net/unknown_robot_type` |
| 错误描述 | 未知机型 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `RobotState` 初始化中 `kCarType.find(car_type) == kCarType.end()`——car_type 不在已知的车型列表中 |
| 触发源码 | `robot_state.cpp:124` |

```text
RobotState 初始化 @ robot_state.cpp:124
  -> car_type 从配置或硬件 ID 获取
  -> kCarType.find(car_type) 失败
  -> pubJ3State(kUnknownRobotType, 1, "未知机型")
```

| P1 | car_type 配置错误 | 机型配置 | 修正配置 | 修复 |
| P1 | 新机型未注册 | kCarType 映射表 | 添加映射 | 更新代码 |

代码证据：JState key `health_info.hpp:75`，触发 `robot_state.cpp:124`

```yaml
playbook:
  meta: {error_code: "615036", error_name: "unknown_robot_type", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "unknow robot type"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "unknow robot type"; priority: P1; context_lines: 5; on_match: {conclusion: "car_type 不在已知列表", root_cause: "机型配置错误或未注册"}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "unknow robot type"; watch_duration_sec: 60}]
```
