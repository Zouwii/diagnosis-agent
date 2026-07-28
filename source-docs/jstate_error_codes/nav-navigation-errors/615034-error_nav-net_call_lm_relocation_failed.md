# JState 错误码 615034：调用反射板接口失败

> 当 `onRelocate()` 调用 `laser_mark_service->relocalization()` 抛出异常时触发，表示调用反射板重定位服务本身失败（非重定位结果失败）。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615034` |
| JState Key | `/jstate/error/nav-net/call_lm_relocation_failed` |
| 错误描述 | 调用反射板接口失败 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `onRelocate()` 中 `laser_mark_service->relocalization(result_pose, message)` 抛出 `std::exception` |
| 直接影响 | 反射板重定位中断，HTTP 返回 500 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：615034（调用失败/异常中断）与 615035（重定位结果失败）的区别：615034 是 `relocalization()` 本身抛异常（服务不可达或内部崩溃），615035 是正常返回但结果为失败。两者在 `onRelocate()` 中是互斥分支。

## 2 触发流程

```mermaid
flowchart TD
    A[onRelocate HTTP] --> B[loadLasermark]
    B -- 有反光板 --> C[laser_mark_service->relocalization]
    C --> D{是否抛异常?}
    D -- 异常 --> E[catch: message = e.what]
    E --> F[pubJ3State kCallLmRelocationFailed]
    F --> G[/route/error 615034]
    D -- 正常 --> H{lm_relocation_ok?}
    H -- false --> I[pubJ3State kLmRelocationFailed → 615035]
```

```text
onRelocate() @ position_recover.cc:248-293
  -> try: lm_relocation_ok = laser_mark_service->relocalization(...)
  -> catch: std::exception &e → pubJ3State(kCallLmRelocationFailed, 1, e.what())
```

## 3 排查

```bash
grep -E "call_lm_relocation|LaserMarkRelocalization|反光板" /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 异常信息 | e.what() 包含具体错误 | 无异常信息 | 检查 `relocalization` 服务状态 |
| 2 | 服务可用性 | LaserMarkRelocalization 服务可达 | 服务不可达或超时 | 修复 ROS service |

## 4 原因与方案

| 优先级 | 原因 | 负责链路 | 临时处置 | 根因修复 |
|---|---|---|---|---|
| P1 | ROS service 不可达 | LaserMarkRelocalizationClient | 重启服务 | 修复服务启动和通信 |
| P1 | 服务内部崩溃 | 反射板算法 | 重试 | 修复算法异常处理 |

代码证据：JState key `health_info.hpp:79`，触发 `position_recover.cc:269`

## 5 Playbook

```yaml
playbook:
  meta: {error_code: "615034", error_name: "call_lm_relocation_failed", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks:
        - type: grep_log; module: nav-net; pattern: "LaserMarkRelocalization|call_lm_relocation"
          on_match: {goto: diagnose}
        - type: on_no_match: {action: expand_time_window}
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "LaserMarkRelocalization"; priority: P1; context_lines: 10
          on_match: {conclusion: "服务调用异常", root_cause: "反射板重定位服务异常", goto: verify}
    - id: verify
      checks:
        - type: verify_fix; grep_pattern: "call_lm_relocation"; watch_duration_sec: 60
```
