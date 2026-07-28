# JState 错误码 615007：载货失败，货架偏移检测超时

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615007` |
| JState Key | `/jstate/error/nav-net/goods_detect_timeout` |
| 错误描述 | 货架偏移检测超时（启动检测 3000ms 内未收到 refer_ 更新） |
| 等级 | `level5`（ERROR） |
| 触发源码 | `goods_deviation_detect.cpp:244` |

**核心判断**：`GoodsDetect::start()` 启动检测后，调用 `checkStartFail()`。如果 `is_detecting_==true` 且 `is_refer_update_==false`（3000ms 内视觉 servo 未返回参照位姿），即触发超时并自动 `stop()`。

```mermaid
flowchart TD
    A[GoodsDetect::start] --> B[setCarrierGoodDetect true]
    B --> C[sleep 3000ms]
    C --> D[checkStartFail]
    D --> E{is_refer_update_?}
    E -- false --> F[pubJ3State kGoodsDetectTimeout, level5 + stop]
    F --> G[/route/error 615007 ERROR]
```

| P1 | 视觉 servo 未响应 | 视觉 servo、相机 | 检查 servo 状态 | 修复 servo |
| P1 | 货架码不可见 | 二维码、相机视野 | 检查码的可见性 | 调整码位置 |
| P2 | 时间不足 | kCheckStartFail=3000ms | 评估是否需延长 | 调整 |

代码证据：JState key `health_info.hpp:71`，触发 `goods_deviation_detect.cpp:244`

```yaml
playbook:
  meta: {error_code: "615007", error_name: "goods_detect_timeout", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "goodsDeviation detect timeout"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "goodsDeviation detect timeout"; priority: P1; context_lines: 10
          on_match: {conclusion: "3000ms 内未收到 refer_", root_cause: "视觉servo未响应或货架码不可见", goto: verify}
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "goodsDeviation detect timeout"; watch_duration_sec: 60}]
```
