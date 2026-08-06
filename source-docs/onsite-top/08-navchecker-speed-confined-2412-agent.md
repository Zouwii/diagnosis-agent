# 高频问题：导航被外部限速（2412）

> 文档用途：当 AI Agent 在任务结果或同期日志中观察到 `SPEED_CONFINED` / `speed_confined` 或机器人运行速度明显低于预期时，用本文判断限速来源（nav-checker 外部限速 vs 内部限速），并采集上游证据。

## 1 问题结论

| 字段 | 内容 |
|---|---|
| 问题模式 | `speed_confined_by_navchecker` |
| 用户可见提示 | HealthMonitor 上报 `speed_confined`（WARN 级别）；日志 `[NavChecker] speed_limit` 或 `[CMD] NavChecker` |
| JState 错误码 | 无独立数值码；由 HealthMonitor `AbnormalIds::SPEED_CONFINED` 标记，级别 `Lv::WARN` |
| 直接产生模块 | `nav-controller` `SpeedPostProcessor::confineMaxSpeed()` + `NavControllerImpl::publishHealthStatus()` |
| 直接触发条件 | `/nav_checker/max_speed` 下发的线速度/角速度低于当前控制指令原始目标值（ratio < 1.0） |
| 相关异常结果 | **任务不中断**，仅降速运行；该 WARN 是信息性的，不触发 ABORTED |
| 直接影响 | 机器人以低于规划速度的值运行，任务完成时间延长 |
| 恢复条件 | nav-checker 判定环境安全后提升 max_speed；当前任务持续受限，新任务重新判定 |
| 验证基线 | `nav-manager` `RC/1.2412.x` @ nav-controller: speed_postprocessor + nav_controller |
| 不适用条件 | nav-checker 节点未运行（此时 `confined_cmd` 默认 `{10,10,10}` 无实际限制）；内部限速（偏轨自适应降速、近点减速）不应归因于 nav-checker |

**核心判断**：`SPEED_CONFINED` 是 WARN 而非 ERROR。它只说明外部 nav-checker 下发了低于当前指令的速度上限，不能证明是障碍物、货架、传感器误报或配置问题。必须从降速比例和 nav-checker 输入源确认根因。

三类限速来源：

1. **nav-checker 外部限速**（本文主题）：`/nav_checker/max_speed` 下发 `{vx, vy, w}`，`ratio < 1.0` 时触发 `speed_confined`；
2. **偏轨自适应降速**：`SpeedPostProcessor::confineOfftrackSpeed()` 根据横向偏轨误差降速，启用条件为 `enable_offtrack_confine` 且非绕障状态；
3. **近点减速**：`SpeedPostProcessor::adaptNearVel()` 在终点附近根据剩余距离和加速度能力降速。

证据状态：

| 状态 | 含义 |
|---|---|
| `已确认` | 日志中同时有 nav-checker 降速日志、max_speed 值和当前指令值，ratio < 1.0 |
| `高可能` | 有降速日志但缺少 nav-checker 状态原文 |
| `待确认` | 只有 `SPEED_CONFINED` 上报或"机器人变慢"的描述 |
| `已排除` | max_speed 值与指令值相近（ratio ≈ 1.0），实为偏轨降速或近点减速 |
| `insufficient_data` | 缺少降速时刻的日志、max_speed 值或版本信息 |

## 2 问题触发的功能流程

前置条件：nav-controller 正常运行，nav-checker ROS 节点正在发布 `/nav_checker/max_speed`。

```mermaid
flowchart TD
    A[nav-checker 发布 /nav_checker/max_speed] --> B[RosDatastore::maxSpeed]
    B --> C{GET_AND_CHECKTIMEOUT}
    C -- 超时 200ms --> D[confined_cmd={10,10,10} 无限制]
    C -- 新鲜数据 --> E[confined_cmd = twist→CentroidCommand]
    E --> F[updateProcessorContainer]
    F --> G[SpeedPostProcessor::update]
    G --> H[setPubCommand 每周期]
    H --> I{confineMaxSpeed}
    I -- 旋转态 --> J[ratio = confined_cmd.w / center_cmd.w]
    I -- 跟踪态 --> K[ratio = calcRatio confined vs center]
    J --> L{ratio < 1.0?}
    K --> L
    L -- 否 --> M[is_speed_limited_externally_ = false]
    L -- 是 --> N[按 ratio 缩放 vx/vy/w]
    N --> O[is_speed_limited_externally_ = true]
    O --> P[publishHealthStatus]
    P --> Q[setStatus SPEED_CONFINED true]
    M --> R[正常速度输出]
```

调用链：

```text
NavControllerImpl::updateProcessorContainer()
  → ros_ds_->maxSpeed(confined_base_cmd, GET_AND_CHECKTIMEOUT)
     → RosDatastore::maxSpeed()
        → getRosSubMsg(MAX_SPEED, GET_AND_CHECKTIMEOUT, twist, 200ms)
        → confined_base_cmd.vx/vy/w = twist.linear/angular
  → motion_tf_->transformCmd(BASE_TO_CENTER, confined_base_cmd, confined_center_cmd)
  → speed_processor_->update(container)
     → SpeedPostProcessor::update()  [存储 confined_cmd 到 container_]

NavControllerImpl::setPubCommand()  [每控制周期]
  → speed_processor_->confineMaxSpeed(state_id, center_cmd)
     → SpeedPostProcessor::confineMaxSpeed()
        → ratio = clamp(confined_cmd.w / center_cmd.w)  [旋转]
        → ratio = calcRatio(confined_cmd, center_cmd)    [跟踪]
        → center_cmd *= ratio  [缩放指令]
        → is_speed_limited_externally_ = (ratio < 1.0)

NavControllerImpl::publishHealthStatus()
  → monitor_->setStatus(SPEED_CONFINED, speed_processor_->isExternallyConfined())
```

直接判据：

- 外部限速：日志有 `[NavChecker] speed_limit, max_w:X, raw_w:Y` 或 `[CMD] NavChecker, max_cmd:(vx, vy, w), confined_cmd:`；
- 未超时：`GET_AND_CHECKTIMEOUT` 在 200ms 内有新鲜数据，否则 `confined_cmd` 默认 `{10, 10, 10}` 不作限制；
- ratio 计算：旋转态 `fabs(confined_cmd.w / center_cmd.w)`，跟踪态 `min(vx_ratio, vy_ratio, w_ratio)`；
- 无限制时 `is_speed_limited_externally_ = false`，`SPEED_CONFINED` 设为 false。

注意：`SPEED_CONFINED` 是 WARN 级别而非 ERROR，不会导致 `fillMoveTaskResult` 或 `abnormalCheck` 触发任务失败。

## 3 结合日志选择排查方向

保留限速发生前后至少 30 秒的 nav-controller 日志，以及 nav-checker 节点日志（如有）：

```bash
grep -E "NavChecker|speed_limit|confined_cmd|speed_confined|SPEED_CONFINED|max_speed|is_speed_limited|confineMaxSpeed|updateProcessorContainer" \
  /opt/jz/log/nav-manager.log /opt/jz/log/nav-controller.log
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 时间、版本、节点 | 日志属于同一时间窗，可区分 nav-controller 和 nav-checker | 无法对齐 | 输出 `insufficient_data`，补版本、时间 |
| 2 | 是否真的被限速 | 日志中有 `NavChecker` 关键字，`ratio < 1.0` | 只有 `speed_confined` 上报无细节 | 标记`待确认`，补降速瞬间日志 |
| 3 | nav-checker 数据新鲜度 | 200ms 超时检查通过，max_speed 值有效 | 无 nav-checker 节点日志 | nav-checker 可能未运行，此时为非 nav-checker 限速 |
| 4 | 限速维度 | 区分线性速度 vx/vy 被限还是旋转 w 被限 | 缺少 confined_cmd 和 raw_cmd 对比 | 补 `[CMD] NavChecker` 日志 |
| 5 | 限速幅度 | `ratio` 值：0.3-0.7 为中度限速，< 0.3 为严重限速 | ratio 接近 1.0 | 实际为非 nav-checker 限速（偏轨/近点） |
| 6 | 持续时间 | 限速持续几个控制周期（100ms 级）还是秒级 | 无法判断 | 补 nav-checker 原始发布的 max_speed 时序 |
| 7 | 上游原因 | nav-checker 日志中有障碍物、货架、区域等具体原因 | 只有 nav-manager 单侧日志 | 需 nav-checker 源数据才能确认环境根因 |
| 8 | 任务影响 | 任务完成但耗时 > 预期 | 任务失败或中断 | 限速通常不导致失败——如失败需排查其他原因 |
| 9 | 复测 | 同路径同条件不再限速或限速减轻 | 仍然限速 | 核实 nav-checker 配置和环境 |

停止规则：

- 缺少 nav-checker 源数据时，只能确认"被限速"但不得确认根因；
- 仅 `SPEED_CONFINED` 上报、无降速日志时，不得判断为 nav-checker 限速；
- `ratio ≥ 0.95` 时，实际未经有意义的限速，停止归因；
- 限速为 WARN 级别，任务失败时必须优先排查 ERROR 级异常。

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | nav-checker 检测到障碍物进入安全区 | nav-checker→max_speed→speed_postprocessor | 保持限速运行，记录障碍物位置 | 清除障碍物或调整安全区域配置 | 同路段 nav-checker 不再降速 |
| P1 | nav-checker 货架状态异常导致全域限速 | nav-checker→shelf_states→max_speed | 记录货架状态原文 | 修正货架传感器或状态映射逻辑 | 货架状态正常后 max_speed 恢复 |
| P2 | nav-checker 传感器误报（激光/视觉噪点） | 传感器→nav-checker→max_speed | 记录同期传感器原始数据 | 排查传感器硬件或滤波参数 | 无噪点时 normal speed |
| P2 | nav-checker 配置的限速区域过保守 | nav-checker 区域配置 | 记录当前限速区域地图 | 调整区域边界或限速值 | 通过区域时限速符合设计预期 |
| P2 | nav-checker 节点重启或订阅丢失导致超时 | ros_datastore timeout→默认无限制 | 不回切——默认无限制反而是好的 | 修复 nav-checker 稳定性或网络 | nav-checker 持续发布 |
| P2 | 定位漂移导致机器人"进入"限制区域 | 定位→nav-checker | 记录定位跳变时刻 | 修复定位问题 | 定位稳定后限速解除 |

禁止擅自关闭 nav-checker 或提高 max_speed 天花板值，Agent 不执行参数写入。

## 5 修复验证与证据索引

闭环条件：

1. 已确认降速来源为 nav-checker（日志中有 `NavChecker` 关键字和 ratio）；
2. nav-checker 源数据（max_speed 值 + 触发原因）已采集；
3. 限速持续时间、幅度、维度已量化；
4. 上游根因（障碍物/货架/区域）已匹配同期 nav-checker 日志；
5. 同条件复测后限速消失或减轻；
6. 限速导致的额外耗时已记录。

Agent 最少证据：

```text
前后至少 30 秒的 nav-controller 日志
nav-checker 节点日志（如有）
confined_cmd 和 raw_cmd 对比值
max_speed 时序（至少 5 个周期）
同期定位位姿
任务 task_code 和时间区间
nav-checker 配置：限速区域、货架映射、安全距离
同路径复测结果
```

Agent 输出：

```yaml
problem_pattern: speed_confined_by_navchecker
analysis_status: insufficient_data  # 已确认/高可能/待确认/已排除/insufficient_data
applicable_version:
  nav_controller: ""
  nav_checker: ""
confine_detail:
  confined_by: unknown  # navchecker/offtrack/nearpoint/unknown
  dimension: ""         # linear/angular/both
  ratio: null           # 0.0 ~ 1.0
  duration_sec: null
  max_speed_raw: {vx: null, vy: null, w: null}
  center_cmd_raw: {vx: null, vy: null, w: null}
task_context:
  task_code: ""
  task_time: ""
  state_id: ""          # REACH/TRACKING/ROTATE
navchecker_status:
  node_running: unknown
  obstacle_detected: unknown
  shelf_state: ""
  region: ""
confirmed_facts: []
most_likely_cause: {cause: "", confidence: low, evidence: []}
excluded_causes: []
missing_evidence: []
next_action: []
temporary_action: ""
root_fix: ""
verification: {result: not_started, evidence: []}
```

输出约束：`confined_by` 必须区分 navchecker/offtrack/nearpoint；缺 nav-checker 源数据时不得确认障碍物或货架根因；WARN 级别不表述为"任务失败"。

| 证据 | 2412 位置 |
|---|---|
| updateProcessorContainer | `nav_controller/src/nav_controller.cpp:1014-1029` |
| setPubCommand confineMaxSpeed | `nav_controller/src/nav_controller.cpp:1031-1049` |
| publishHealthStatus SPEED_CONFINED | `nav_controller/src/nav_controller.cpp:257-258` |
| SpeedPostProcessor::confineMaxSpeed | `nav_controller/src/task_manager/speed_postprocessor.cpp:110-154` |
| SpeedPostProcessor::update | `nav_controller/src/task_manager/speed_postprocessor.cpp:89-96` |
| isExternallyConfined | `nav_controller/src/task_manager/speed_postprocessor.cpp:47-49` |
| isSpeedInconsistent | `nav_controller/src/task_manager/speed_postprocessor.cpp:50-52` |
| confineOfftrackSpeed（偏轨降速） | `nav_controller/src/task_manager/speed_postprocessor.cpp:98-108` |
| adaptNearVel（近点减速） | `nav_controller/src/task_manager/speed_postprocessor.cpp:192-216` |
| RosDatastore::maxSpeed | `nav_core/src/ros_datastore.cpp:173-181` |
| GET_AND_CHECKTIMEOUT | `nav_core/src/ros_datastore.cpp:80-93` |
| max_speed 订阅注册 | `nav_core/src/ros_datastore.cpp:120` |
| HealthMonitor SPEED_CONFINED 注册 | `nav_core/src/health_monitor.cpp:65` |
| AbnormalIds::SPEED_CONFINED | `nav_core/include/nav_core/struct/abnormal_ids.h:13` |
| PostProcessorContainer::confined_cmd | `nav_controller/include/nav_controller/task_manager/speed_postprocessor.h:14` |

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    problem_pattern: "speed_confined_by_navchecker"
    baseline: "nav-manager RC/1.2412.x @ nav-controller"
    modules: ["nav-controller", "nav-checker"]
    time_window_sec: 30
    read_only: true
  steps:
    - id: classify_confine_source
      description: "区分外部限速、偏轨降速和近点减速"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "NavChecker|speed_limit|confined_cmd"
          on_match: {conclusion: "nav-checker 外部限速", priority: P1, goto: quantify_confine}
          on_no_match: {conclusion: "非 nav-checker 限速，检查偏轨和近点", goto: check_internal_confine}

    - id: check_internal_confine
      description: "检查偏轨降速和近点减速"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "offtrack|confineOfftrack|adaptNearVel|should.*adjust.*near_v|near.*vel"
          on_match: {conclusion: "内部限速（偏轨/近点），非 nav-checker 问题", priority: P2, goto: fallback}
          on_no_match: {conclusion: "仅有 speed_confined 上报，无详细日志", goto: check_health_monitor_only}

    - id: check_health_monitor_only
      description: "仅 HealthMonitor 上报 speed_confined 的情况"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "speed_confined|SPEED_CONFINED"
          on_match: {conclusion: "HealthMonitor 有上报但无降速细节日志", priority: P2, goto: fallback}
          on_no_match: {conclusion: "无任何限速证据", goto: fallback}

    - id: quantify_confine
      description: "量化降速维度、幅度和持续时间"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "NavChecker.*max_w|NavChecker.*max_cmd|confined_cmd"
          on_match: {conclusion: "提取 max_speed 和 raw_cmd，计算 ratio", priority: P1, goto: check_navchecker_freshness}
          on_no_match: {conclusion: "有 NavChecker 关键字但无详细值", goto: fallback}

    - id: check_navchecker_freshness
      description: "检查 nav-checker 数据是否新鲜"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "maxSpeed|GET_AND_CHECKTIMEOUT|ros_ds.*max"
          on_match: {conclusion: "nav-checker 数据路径存在", priority: P1, goto: diagnose_navchecker_cause}
          on_no_match: {conclusion: "nav-checker 可能停服或网络异常", goto: fallback}

    - id: diagnose_navchecker_cause
      description: "排查 nav-checker 限速原因"
      checks:
        - type: grep_log
          module: "nav-checker"
          pattern: "obstacle|shelf|region|zone|footprint|collision|safety"
          on_match: {conclusion: "提取障碍物/货架/区域信息", priority: P1, goto: check_task_impact}
          on_no_match: {conclusion: "缺 nav-checker 节点日志，只能确认'被限速'", goto: check_task_impact}

    - id: check_task_impact
      description: "评估限速对任务的影响"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "fillMoveTaskResult|abnormalCheck|task.*finish|task.*success|task_code"
          on_match: {conclusion: "确认任务是否完成及耗时", priority: P1, goto: verify}
          on_no_match: {conclusion: "任务状态未知", goto: fallback}

    - id: verify
      description: "复测检查"
      checks:
        - type: verify_fix
          grep_pattern: "NavChecker.*speed_limit|speed_confined|SPEED_CONFINED"
          watch_duration_sec: 30
          on_match: {conclusion: "复测仍有限速", priority: P1, goto: fallback}
          on_no_match: {conclusion: "未再命中；需同路径成功复测确认", goto: verify_success}

    - id: verify_success
      description: "确认同路径正常速度通过"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "fillMoveTaskResult|task.*success|task_code"
          on_match: {conclusion: "复测成功，限速不再出现", priority: P1}
          on_no_match: {conclusion: "无成功复测证据", goto: fallback}

    - id: fallback
      description: "证据不足兜底"
      checks:
        - type: grep_log
          module: "nav-controller"
          pattern: "task_code|confineMaxSpeed|is_speed_limited|max_linear_vel"
          on_match: {conclusion: "analysis_status=insufficient_data，列出缺失的 nav-checker 数据或复测"}
          on_no_match: {conclusion: "补完整版本和问题前后 30 秒原始日志，analysis_status=insufficient_data"}
```
