# JState 错误码 615039：货架偏移检测未检测到货架码

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615039` |
| JState Key | `/jstate/error/nav-net/goods_undetect` |
| 错误描述 | 货架偏移检测未检测到货架码 |
| 等级 | `level3`（AUTO_ABN） |
| 触发源码 | `goods_deviation_detect.cpp:284` |

**核心判断**：`onLoop()` 1Hz 检查 `refer_time_`（上次视觉 servo 更新 refer_ 的时间）。若距超过 1s 且 `has_rotater_==false`，发布 615039。恢复：refer_ 重新更新后 5 帧内发布 `pubJ3StateFalse`。

```mermaid
flowchart TD
    A[onLoop 1Hz] --> B{refer_time_ > 1s ago?}
    B -- 是 --> C{has_rotater_?}
    C -- false --> D[pubJ3State kGoodsUndetect, level3]
    D --> E[/route/error 615039]
    C -- true --> F[carrier-rotater 负责]
    B -- 否 --> G[pubJ3StateFalse, 最多5次]
```

| P1 | 货架码离开视野 | 相机、安装位置 | 调整车辆位置 | 优化码安装 |
| P1 | 视觉 servo 停止更新 | servo 状态 | 检查 servo | 修复 |

代码证据：JState key `health_info.hpp:69`，触发 `goods_deviation_detect.cpp:284`，恢复 `:287`

```yaml
playbook:
  meta: {error_code: "615039", error_name: "goods_undetect", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "未检测到货架"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "未检测到货架"; priority: P1; context_lines: 5
          on_match: {conclusion: "refer_time_ 超过 1s 未更新", root_cause: "视觉servo停止更新"}
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "未检测到货架"; watch_duration_sec: 60}]
```
