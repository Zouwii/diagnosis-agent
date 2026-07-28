# JState 错误码 615037：当前输入无法定位

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615037` |
| JState Key | `/jstate/error/nav-net/req_locate_failed` |
| 错误描述 | 当前输入无法定位 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `RobotState::reqLocate()` 中 `initial_pose` 调用返回失败（`is_succeed == false`），即导航系统拒绝当前的初始位姿请求 |
| 触发源码 | `robot_state.cpp:226` |

```text
reqLocate() @ robot_state.cpp:226
  -> 调用导航系统的 initial_pose
  -> is_succeed == false
  -> LOGE "5109|当前输入无法定位"
  -> pubJ3State(kReqLocateFailed, 1, "当前输入无法定位")
```

| P1 | 输入位姿异常 | 调用方 | 检查位姿参数 | 修复输入 |
| P1 | 定位系统拒绝 | 导航定位 | 检查定位状态 | 修复定位系统 |

代码证据：JState key `health_info.hpp:73`，触发 `robot_state.cpp:226`

```yaml
playbook:
  meta: {error_code: "615037", error_name: "req_locate_failed", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "5109|当前输入无法定位"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks: [{type: grep_log; module: nav-net; pattern: "5109|当前输入无法定位"; priority: P1; context_lines: 10; on_match: {conclusion: "initial_pose 调用失败", root_cause: "导航系统拒绝初始位姿"}}]
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "5109|当前输入无法定位"; watch_duration_sec: 60}]
```
