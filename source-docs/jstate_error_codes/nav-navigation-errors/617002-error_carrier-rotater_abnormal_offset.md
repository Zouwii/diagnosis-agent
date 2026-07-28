# JState 错误码 617002：货架中心偏离

> 文档用途：当 AI Agent 在现场日志中发现 `617002` 时，用本文理解错误含义和所属模块，并根据同期日志选择排查方向。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `617002` |
| JState Key | `/jstate/error/carrier-rotater/abnormal_offset` |
| 错误描述 | 货架中心偏离 |
| 等级 | `level3`，nav-net（导航网络模块） 内部为 `AUTO_ABN` |
| 所属模块 | `abnormal_offset` |
| 直接触发条件 | **当前工作区缺少 abnormal_offset 源码**。META 描述：货架中心偏离。 |
| 直接影响 | 根据具体触发场景，可能影响当前导航任务或相关功能。 |
| 自动恢复条件 | 自动异常级别，自动恢复：置 false 后最多发布 3 次停止。 |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 机器人运行版本包含该错误码注册和 abnormal_offset 模块 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |
| META 描述（英文） | shelf center is off |
| META 外部说明 | [货架中心偏离](https://alidocs.dingtalk.com/i/nodes/7NkDwLng8ZM0kLDaczaERmONJKMEvZBY?utm_scene=team_space&utm_source=dingdoc_doc&utm_medium=dingdoc_doc_splitview) |

**核心判断**：`617002` 属于 `abnormal_offset` 模块的错误码。abnormal_offset 是独立仓库，源码不在当前 nav-manager 工作区中。基于 META 注册信息，该错误表示 **货架中心偏离**。缺少源码时，只能根据 META 描述和模块功能推断触发分支，不能确定具体代码路径。

本文使用以下证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | META 注册信息可直接证明 |
| `高可能` | 特征与某一原因高度吻合，但仍缺少源码侧直接证据 |
| `待确认` | 当前只能作为排查方向 |
| `已排除` | 正常判据或反向证据已经排除该原因 |

## 2 模块功能与触发流程

nav-net（导航网络模块） 的功能：负责机器人导航定位、路径规划、纹理建图、激光数据处理和货架偏移检测。在 nav-manager 上层运行，通过 ROS topic 和 service 与 nav-manager 通信。

该模块通过 ROS 与 nav-manager 通信。错误码通过 `/route/error` 发布，由 HealthMonitor 的 JState 映射机制对外暴露。

```text
推测调用链（源码不在本仓库）：
  abnormal_offset 模块内部业务逻辑
    -> 检测到异常条件（货架中心偏离）
    -> 调用 health_monitor 或直接发布 /route/error
    -> JState 映射为 617002

发布规则：
当 is_abnormal == true  → 持续发布 trigger:true（每 1 秒）
当 is_abnormal == false → 发布 trigger:false 最多 3 次后停止

因此：
  - WARN 类型持续上报直到异常清除
  - 任务重置时 exit() 统一清除所有非 BLIND_MOVING 状态
```

代码与数据证据：

| 证据 | 位置 |
|---|---|
| 数值码映射 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |
| JState key | `/jstate/error/carrier-rotater/abnormal_offset` |
| **模块源码** | **nav-net 仓库（不在当前 nav-manager 工作区） —— 证据边界** |

## 3 结合日志选择排查方向

先提取错误前后至少 60 秒的 abnormal_offset 日志：

```bash
grep -E "error_carrier-rotater_abnormal_offset|abnormal_offset|error" /opt/jz/log/nav-net.log | tail -n 300
```

按顺序执行：

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间与版本 | JState、日志和任务属于同一时间窗 | 时间、版本或日志不一致 | 标记`待确认`并重新取证 |
| 2 | 错误确认 | 能从 `/route/error` 确认 `error_carrier-rotater_abnormal_offset` 出现 | JState 中出现但日志中无对应事件 | 扩大时间窗或检查 abnormal_offset 日志级别 |
| 3 | 同模块关联错误 | 无其他 abnormal_offset 错误同时出现 | 多个 abnormal_offset 错误码同时出现 | 优先分析最早出现的错误或模块级异常 |
| 4 | 上游依赖 | 依赖的服务、topic 和数据源均正常 | topic 无发布者、服务不可达、数据异常 | 按数据中断链追因 |
| 5 | 当前任务上下文 | 任务正常执行中 | 任务在特定阶段反复触发 | 关联任务阶段和模块内部状态 |
| 6 | 复测 | 同一场景连续执行不再触发 | 复测仍触发 | 需要 abnormal_offset 源码排查具体失败分支 |

停止规则：

- 缺少 abnormal_offset 源码时，不能输出源码级根因。`
- 只有错误码没有同期日志时，只能解释 META 含义。`
- 修复后同场景连续多次不再触发方可闭环。`

现场确认命令：

```bash
# 确认 JState 原始上报
rostopic echo -n 1 /route/error

# 检查 abnormal_offset 相关节点
rosnode list | grep -E "abnormal_offset|nav"

# 查看错误前后的完整日志上下文
grep -B 30 -A 30 "error_carrier-rotater_abnormal_offset" /opt/jz/log/nav-net.log
```

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 模块内部逻辑触发：货架中心偏离 | abnormal_offset | 安全停止受影响任务，等待或重新触发 | 需 abnormal_offset 源码排查具体触发分支 | 同一场景不再触发 |
| P1 | 上游数据异常：模块依赖的输入数据不满足要求 | 数据生产者、ROS 通信 | 检查并恢复上游数据源 | 修复数据生产链路 | 数据持续正常，错误不再出现 |
| P2 | 配置或参数异常：abnormal_offset 的配置不匹配当前场景 | 配置管理、参数下发 | 核对并修正配置参数 | 修正配置模板或参数下发逻辑 | 配置修正后不再触发 |
| P2 | 模块初始化或运行态异常：进程启动时序或运行中状态异常 | abnormal_offset、系统管理 | 重启 abnormal_offset 模块 | 修复启动依赖和运行健康检查 | 多次启动不再触发 |

**重要约束**：由于缺少 abnormal_offset 源码，以上原因为基于 META 描述的推测。获取源码后可更新为精确的触发分支和判别特征。

## 5 修复验证与证据索引

闭环需要同时满足：

1. 已确认错误来源为 abnormal_offset 模块。
2. `//jstate/error/carrier-rotater/abnormal_offset` 不再上报 `trigger:true`。`
3. 同场景连续执行多次不再触发 `617002`。
4. 关联的上游数据和服务正常。

Agent 最少需要收集：

```text
错误时间及前后至少 60 秒的未过滤日志
/route/error 原始消息
abnormal_offset 同时间窗日志
相关 ROS topic 和服务状态
abnormal_offset 和 nav-manager 版本
修复后同场景复测结果
```

Agent 输出格式：

```yaml
error_code: 617002
error_name: abnormal_offset
analysis_status: 待确认  # 已确认 / 高可能 / 待确认 / 已排除
applicable_version:
  primary_module: "abnormal_offset"
  nav_manager: ""
trigger_path: unknown
trigger_stage: unknown
confirmed_facts:
  - "META 注册为 abnormal_offset 模块错误"
most_likely_cause:
  cause: ""
  confidence: low  # high / medium / low
  evidence:
    - ""
excluded_causes: []
missing_evidence:
  - "abnormal_offset 源码不在当前仓库，无法确认具体触发分支"
next_action:
  - ""
temporary_action: ""
root_fix: ""
verification:
  result: not_started  # passed / failed / not_started
  evidence:
    - ""
```

输出约束：

- 缺少 abnormal_offset 源码时，`trigger_path` 保持 `unknown`。
- 根因必须是经源码证实的，不得用 META 描述代替根因。
- 未执行同场景复测时，验证结果必须为 `not_started`。

## 6 Agent 自动排查 Playbook

> 本章供 diagnosis-orchestrator 的确定性分析器自动执行。由于缺少 abnormal_offset 源码，playbook 基于 META 注册信息和模块功能构建。

```yaml
playbook:
  meta:
    error_code: "617002"
    error_name: "abnormal_offset"
    module: "abnormal_offset"
    time_window: 60

  steps:
    - id: classify_trigger_chain
      description: "确认 error_carrier-rotater_abnormal_offset 是否在时间窗内出现"
      checks:
        - type: grep_log
          module: "abnormal_offset"
          pattern: "error_carrier-rotater_abnormal_offset"
          on_match:
            trigger_chain: "abnormal_offset_confirmed"
            conclusion: "命中 error_carrier-rotater_abnormal_offset，确认为 abnormal_offset 模块错误"
            goto: diagnose_abnormal_offset
        - type: on_no_match
          conclusion: "当前时间窗内未找到 error_carrier-rotater_abnormal_offset，扩大时间窗或检查 JState 原始消息"
          action: expand_time_window
          time_window: 120

    - id: diagnose_abnormal_offset
      description: "排查 error_carrier-rotater_abnormal_offset 的可能原因：关联错误 → 模块状态 → 上游依赖"
      evidence_boundary: true
      checks:
        - type: grep_log
          module: "abnormal_offset"
          pattern: "error|fail|timeout|invalid|not found"
          priority: P1
          on_match:
            conclusion: "abnormal_offset 模块存在异常日志，需逐条分析"
            continue: true
          on_no_match:
            conclusion: "无其他异常日志，error_carrier-rotater_abnormal_offset 可能是独立触发"
            continue: true
        - type: grep_log
          module: "abnormal_offset"
          pattern: "error_carrier-rotater_abnormal_offset"
          priority: P1
          context_lines: 10
          on_match:
            conclusion: "找到 error_carrier-rotater_abnormal_offset 日志上下文，检查触发前后的数据和状态"
            continue: true
          on_no_match:
            continue: true
        - type: on_no_match
          conclusion: "缺少 abnormal_offset 源码，无法进一步确定触发分支"
          status: insufficient_data
          action: "获取 abnormal_offset 源码后补充具体排查步骤"

    - id: verify
      description: "验证修复：连续 60 秒不再出现 error_carrier-rotater_abnormal_offset"
      checks:
        - type: verify_fix
          grep_pattern: "error_carrier-rotater_abnormal_offset"
          watch_duration_sec: 60
          on_match:
            status: still_present
            action: "错误仍然存在，需获取 abnormal_offset 源码深入排查"
          on_no_match:
            status: verified
            conclusion: "连续 60 秒未出现 error_carrier-rotater_abnormal_offset，错误已清除"
```
