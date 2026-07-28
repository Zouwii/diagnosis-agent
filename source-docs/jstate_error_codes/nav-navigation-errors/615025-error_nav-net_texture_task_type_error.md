# JState 错误码 615025：任务类型错误

> 文档用途：当 AI Agent 在现场日志中发现 `615025` 时，用本文理解错误的注册信息和功能背景。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615025` |
| JState Key | `/jstate/error/nav-net/texture_task_type_error` |
| 错误描述 | 任务类型错误 |
| 等级 | `level5` |
| 直接触发条件 | **当前 nav-net 源码中未找到 pubJ3State 触发路径。** 该错误码在 health_info.hpp 中注册但无 .cc/.cpp 触发调用。 |
| 直接影响 | 未知。可能通过旧版 `set()`/`publish()` → `/agent/health/in` 或外部 HTTP API 触发。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 机器人运行版本包含 nav-net 模块 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`615025` 在 `health_info.hpp` 的 `HealthType` 和 `kHealthTypeMap` 中注册，但源码中无 `pubJ3State` 调用。可能通过旧版 `set()`+`publish()` 路径发布到 `/agent/health/in`，或通过 Drogon HTTP API 由外部服务触发。

## 2 注册信息

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |
| JState key 定义 | `nav-net/include/common/health_info.hpp` → `HealthType` |
| 错误码→key 映射 | `nav-net/include/common/health_info.hpp` → `kHealthTypeMap` |
| **触发调用** | **当前源码中未找到** |

## 3 结合日志选择排查方向

```bash
grep -E "texture_task_type_error" /opt/jz/log/nav-net.log | tail -n 300
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 错误来源 | 能从 /route/error 确认 key | 从未出现 | 可能是预留/废弃码 |
| 2 | nav-net 日志 | 有对应业务日志 | 无相关日志 | 外部 HTTP 触发 |
| 3 | /agent/health/in | 旧版路径有数据 | 无数据 | 确认真实路径 |

## 4 可能原因与解决方案

| 优先级 | 原因 | 负责链路 | 临时处置 | 根因修复 |
|---|---|---|---|---|
| P1 | 外部 HTTP API 触发 | nav-net HTTP controllers | 检查服务端调用日志 | 修复服务端逻辑 |
| P2 | 旧版 set()/publish() | /agent/health/in | 等待恢复或重启 | 迁移到 pubJ3State |
| P3 | 注册但未实现 | META 注册表 | 确认是否保留 | 移除或补充实现 |

## 5 修复验证与证据索引

```yaml
error_code: 615025
error_name: texture_task_type_error
analysis_status: 待确认
trigger_path: unknown
confirmed_facts:
  - "在 health_info.hpp 中注册但无 pubJ3State 触发路径"
missing_evidence:
  - "触发路径未在源码中找到"
next_action:
  - "确认现场是否真的出现此错误码"
verification:
  result: not_started
```

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615025"
    error_name: "texture_task_type_error"
    module: "nav-net"
    time_window: 60

  steps:
    - id: classify_trigger_chain
      description: "确认 texture_task_type_error 是否出现"
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "texture_task_type_error"
          on_match:
            trigger_chain: "texture_task_type_error_confirmed"
            conclusion: "命中 texture_task_type_error"
            goto: diagnose_texture_task_type_error
        - type: on_no_match
          conclusion: "未找到日志，可能外部触发或旧版路径"
          action: expand_time_window
          time_window: 120

    - id: diagnose_texture_task_type_error
      description: "排查可能的触发路径"
      evidence_boundary: true
      checks:
        - type: on_no_match
          conclusion: "源码未找到 pubJ3State，需检查 /agent/health/in 和 HTTP API"
          status: insufficient_data

    - id: verify
      description: "验证修复"
      checks:
        - type: verify_fix
          grep_pattern: "texture_task_type_error"
          watch_duration_sec: 60
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
