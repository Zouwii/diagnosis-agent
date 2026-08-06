# onsite-top 高频问题知识库

> 日期：2026-08-06
> 说明：本目录存放现场 Top 高频问题的排查文档，供 diagnosis-agent 的 Playbook 引擎加载执行。

---

## 1. 目录总览

```
onsite-top/
├── README.md                               ← 本文件
├── 00-version-baseline.md                  ← 版本基线（建议升级版本对照）📋
├── 01-navigation-stuck.md                  ← 导航卡住（通用草稿，待补 Agent 版）
├── 02-illegal-rotation.md                  ← 非法旋转（通用草稿，待补 Agent 版）
├── 03-path-deviation.md                    ← 路径偏离（通用草稿，待补 Agent 版）
├── 06-arrival-precision-2412-agent.md      ← 到点精度异常 Agent 版 ✅
├── 07-nav-param-error-2412-agent.md        ← 导航运行参数异常 Agent 版 ✅
├── 08-navchecker-speed-confined-2412-agent.md ← nav-checker 外部限速 Agent 版 ✅
├── 09-speed-tracking-deviation-2412-agent.md  ← 速度跟踪偏差 Agent 版 ✅
└── scripts/                                ← 辅助分析脚本
```

---

## 2. 文档状态一览

| 编号 | 文件名 | 状态 | 级别 | 对应问题模式 | HealthMonitor 关键词 |
|---|---|---|---|---|---|
| 00 | `00-version-baseline.md` | 📋 参考 | — | `version_mismatch` | — |
| 01 | `01-navigation-stuck.md` | ⚠️ 草稿 | 通用 | `navigation_stuck` | 无专用码 |
| 02 | `02-illegal-rotation.md` | ⚠️ 草稿 | 通用 | `illegal_rotation` | `shelf_rotate_illegal` / `point_shelf_angle_invalid` / `path_shelf_angle_invalid` |
| 03 | `03-path-deviation.md` | ⚠️ 草稿 | 通用 | `path_deviation` | `dist_offtrack` / `angle_offtrack` |
| 06 | `06-arrival-precision-2412-agent.md` | ✅ Agent 版 | 2412 代码审计 | `arrival_precision_abnormal` | 无专用码（nav_base task result） |
| 07 | `07-nav-param-error-2412-agent.md` | ✅ Agent 版 | 2412 代码审计 | `nav_param_error` | `chassis_param_error` / `speed_param_error` / `calib_param_error` / `task_param_error` / `no_point_in_map` / `stitch_path_error` / `path_not_found` / `other_reason` |
| 08 | `08-navchecker-speed-confined-2412-agent.md` | ✅ Agent 版 | 2412 代码审计 | `speed_confined_by_navchecker` | `speed_confined` |
| 09 | `09-speed-tracking-deviation-2412-agent.md` | ✅ Agent 版 | 2412 代码审计 | `speed_tracking_deviation` | `cmd_invalid` / `cmd_oscillating` |

### 状态说明

| 状态 | 含义 |
|---|---|
| ⚠️ 草稿 | 概念级文档，未基于 2412 代码审计，缺少 Agent Playbook |
| ✅ Agent 版 | 基于 2412 代码审计的完整文档，含 §1-§5 知识底座 + §6 YAML Playbook，可被 diagnosis-agent 加载执行 |

---

## 3. 各文档说明

### 3.0 00-version-baseline.md — 子包版本基线

**用途**：诊断流程第一步——检查现场运行的各子包版本是否 ≥ 建议升级版本。版本不一致时标记为高风险因素。

**来源**：[钉钉文档 - 最新支持的导航版本建议升级指南](https://alidocs.dingtalk.com/i/nodes/QG53mjyd80RMlpD0CX90D4QnV6zbX04vh)

**覆盖子包**：nav-base、jz-motion-common、nav-net、nav-manager、speed-manager、jz-pnc、safe-perception。按 2409 / 2412 版本系分别列出。

**不作为 Playbook 加载**，由诊断流程在 evidence collection 阶段读取。

---

### 3.1 01-navigation-stuck.md — 导航卡住

**问题模式**：`navigation_stuck`

**现场现象**：Carly 显示"前进中"或"后退中"，机器人无实际移动；"准备移动"状态持续不动；从休息点无法离开。

**涉及链路**：nav-manager motion dispatch → move_base 路径执行 → 调度交管/停障信号。

**待补内容**：需要基于 2412 代码审计，补充精确的触发条件、代码位置、grep 模式、Playbook。涉及的关键代码包括 `hotstart_manager.cpp` 的 stop 检查、`nav_plugin.cpp` 的 execute 流程、move_base 反馈链。

---

### 3.2 02-illegal-rotation.md — 非法旋转

**问题模式**：`illegal_rotation`

**现场现象**：机器人在禁止旋转点位旋转；到达库位后异常旋转导致空间申请失败；原地左右旋转无法直行；不受道路属性限制旋转。

**涉及链路**：nav-manager `HealthChecker::validateRotation()` → `PrecisionManager::fillReachScene()` → `Pruner` 路径剪裁 → `SHELF_ROTATE_ILLEGAL` / `POINT_SHELF_ANGLE_INVALID` / `PATH_SHELF_ANGLE_INVALID`。

**待补内容**：需要基于 2412 代码审计，补充精确的触发条件、代码位置、grep 模式、Playbook。

---

### 3.3 03-path-deviation.md — 路径偏离

**问题模式**：`path_deviation`

**现场现象**：行驶中偏离规划路线（但定位未丢）；走曲线时直线穿过报错；导航走歪/走偏。

**涉及链路**：nav-base `OfftrackReverter` → nav-controller `HealthChecker::checkDistError()` + `checkAngleError()` → `DIST_OFFTRACK` / `ANGLE_OFFTRACK` ERROR 级。

**待补内容**：需要基于 2412 代码审计，补充精确的触发条件、代码位置、grep 模式、Playbook。代码位于 `health_checker.cpp:99-124` 和 nav-base 端的 `offtrack_reverter`。

---

### 3.4 06-arrival-precision-2412-agent.md — 到点精度异常

**问题模式**：`arrival_precision_abnormal`

**代码基线**：nav-manager `RC/1.2412.x @ a0b4f84`

**核心触发**：nav_base `TaskMaster::handlePostArrival()` 在控制器完成后执行 `isGoalPrecise()` / `isReachPrecise()` 检查。三类结果：高精度重试超限（ABORTED）、FINAL 距离超限（ABORTED）、普通异常到点（REACH_WITH_ERROR）。

**涉及模块**：nav-base (task_master.cpp, precision_keeper.cpp) + nav-manager (precision_manager.cpp, nav_plugin.cpp)

**生成方式**：从 `05-arrival-precision-2412.md`（人版）手工派生，添加 YAML Playbook。

---

### 3.5 07-nav-param-error-2412-agent.md — 导航运行参数异常

**问题模式**：`nav_param_error`

**代码基线**：nav-manager `RC/1.2412.x` @ manager + nav_core + nav_controller

**核心触发**：8 种子错误覆盖任务初始化阶段的所有参数校验失败点。分为两组：常驻校验（ChassisManager::validateParams → chassis/speed/calib）和按任务校验（stitch/transformGoal/fillPathNode/jzSearch）。

**涉及模块**：nav-controller (chassis_manager.cpp) + nav-manager (dispatch_preempt_processor.cpp, nav_plugin.cpp, health_monitor.cpp)

**8 种子错误**：
| 子类 | 触发条件 | 级别 |
|---|---|---|
| `chassis_param_error` | KinoTF 初始化失败 | ERROR |
| `speed_param_error` | max_linear_vel ≤ 0 或货架模板速度=0 | ERROR |
| `calib_param_error` | 标定延迟 ≤ 0 或差速轮系数无效 | ERROR |
| `task_param_error` | spare_json_str 为空或 YAML 解析失败 | ERROR |
| `no_point_in_map` | 调度点位在地图中不存在 | ERROR |
| `stitch_path_error` | 新调度路径与上一段无重合点 | ERROR |
| `path_not_found` | 自搜索无有效路径 | ERROR |
| `other_reason` | executeTask 兜底失败 | ERROR |

---

### 3.6 08-navchecker-speed-confined-2412-agent.md — nav-checker 外部限速

**问题模式**：`speed_confined_by_navchecker`

**代码基线**：nav-manager `RC/1.2412.x` @ nav-controller

**核心触发**：nav-checker（独立 ROS 节点）通过 `/nav_checker/max_speed` 下发速度上限 `{vx, vy, w}`，nav-controller 的 `SpeedPostProcessor::confineMaxSpeed()` 逐周期比较 `confined_cmd` 和实际 `center_cmd`，`ratio < 1.0` 时按比例缩放指令并设 `SPEED_CONFINED`（WARN 级别）。

**涉及模块**：nav-controller (speed_postprocessor.cpp, nav_controller.cpp, ros_datastore.cpp)

**关键区分**：WARN 级别，任务**不中断**只降速。需与偏轨自适应降速（confineOfftrackSpeed）和近点减速（adaptNearVel）区分。

---

### 3.7 09-speed-tracking-deviation-2412-agent.md — 速度跟踪偏差

**问题模式**：`speed_tracking_deviation`

**代码基线**：nav-manager `RC/1.2412.x` @ nav-controller

**核心触发**：`SpeedPostProcessor::reconcileCmd()` 比较反馈速度 `center_fb_` 与上一周期指令 `prev_center_cmd_`，偏差 > `deltav_max`（5 × delay_time_ × VAccMax）连续 10 周期触发 `is_speed_inconsistent` → speed_replan。另有两类相关异常：`CMD_INVALID`（指令含 NaN 或 > 2x 上限）和 `CMD_OSCILATING`（控制器振荡 30 周期）。

**涉及模块**：nav-controller (speed_postprocessor.cpp, health_checker.cpp, centroid_controller_interface.cpp)

---

## 4. 文档编号规则

- `0X` 编号表示该问题在 Q2 现场报表中的频率排名（01-03 为 TOP 3 草稿）
- `06-09` 编号继续 Q2 排名序列（06 到点精度 ≈ 排名 6），后续文档按生成顺序编号
- `-2412-agent` 后缀表示基于 2412 代码审计的 Agent 可执行版
- 无后缀的为通用概念版草稿

## 5. 维护说明

| 属性 | 说明 |
|---|---|
| **Agent 版（06-09）** | 基于 2412 代码审计，手工编写。每篇包含 §1-§5 知识底座 + §6 YAML Playbook。可被 `knowledge/playbook_loader.py` 加载 |
| **草稿版（01-03）** | 通用概念文档。后续应补做 2412 代码审计并添加 Playbook，完成后删除旧草稿 |
| **生成方式** | Agent 版当前全部手工派生。`docs/02-开发任务.md` 规划了自动生成脚本（待实现） |
| **代码基线** | `nav-manager` + `nav-base` `RC/1.2412.x` 分支 |
| **Playbook 加载** | `diagnosis-agent/knowledge/playbook_loader.py` 扫描 `source-docs/` 下所有 `*-agent.md`，提取 YAML playbook 段执行 |
