# JState 错误码 615006：检测到货架偏移超过阈值

## 1 错误结论
| 字段 | 内容 |
|---|---|
| 错误码 | `615006` |
| JState Key | `/jstate/error/nav-net/goods_deviated` |
| 错误描述 | 检测到货架偏移超过阈值 |
| 等级 | `level3`（AUTO_ABN）。持续触发（每 1s），恢复后 `pubJ3StateFalse` 发布 5 次停止 |
| 直接触发条件 | `GoodsDetect::onLoop()` 1Hz 循环中 `deviated_ == true && has_rotater_ == false` |
| 触发源码 | `goods_deviation_detect.cpp:292` |

**核心判断**：`deviated_` 由视觉 servo 检测设置（货架偏移量超过 `dxy`/`ddegree` 配置阈值）。`has_rotater_` 决定谁发布此错误：false 时由 nav-net 发布，true 时由 carrier-rotater 模块负责。

```mermaid
flowchart TD
    A[GoodsDetect::onLoop 1Hz] --> B{deviated_?}
    B -- true --> C{has_rotater_?}
    C -- false --> D[pubJ3State kGoodsDeviated, level3]
    D --> E[/route/error 615006]
    C -- true --> F[由 carrier-rotater 处理]
    B -- false --> G[pubJ3StateFalse 清除, 最多5次]
```

恢复：`deviated_` 变 false 后，最多 5 次 `pubJ3StateFalse` 发布 `trigger:false` 清除。

| 顺序 | 检查项 | 正常判据 | 异常判据 | 下一步 |
|---:|---|---|---|---|
| 1 | 偏移量 | `deviated_` 在阈值内 | 持续 true | 检查货架安装和载货状态 |
| 2 | has_rotater_ | 与 carrier-rotater 状态一致 | 配置错误 | 修正 |

| P1 | 货架实际偏移：安装松动或碰撞 | 货架物理安装 | 重新固定 | 修复安装 |
| P1 | 视觉检测误报：config dxy/ddegree 过严 | 视觉 servo | 放宽阈值 | 调整配置 |
| P2 | has_rotater_ 配置不一致 | 模块协调 | 统一配置 | 修正 |

代码证据：JState key `health_info.hpp:67`，触发 `goods_deviation_detect.cpp:292`，恢复 `:299`

```yaml
playbook:
  meta: {error_code: "615006", error_name: "goods_deviated", module: "nav-net", time_window: 60}
  steps:
    - id: classify
      checks: [{type: grep_log; module: nav-net; pattern: "检测到货架偏移超过阈值"; on_match: {goto: diagnose}}]
    - id: diagnose
      checks:
        - type: grep_log; module: nav-net; pattern: "deviated_|goodsdetect"; priority: P1
          on_match: {conclusion: "货架偏移检测持续触发"}
        - type: grep_log; module: nav-net; pattern: "未检测到货架|goodsUndetect"; priority: P2
          on_match: {conclusion: "先出现 goods_undetect，可能与偏移关联"}
    - id: verify
      checks: [{type: verify_fix; grep_pattern: "检测到货架偏移超过阈值"; watch_duration_sec: 60}]
```
