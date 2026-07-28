# JState 错误码 615013：指定恢复点位的pose无效

> 文档用途：当 AI Agent 在现场日志中发现 `615013` 时，用本文判断是地图节点数据中不存在该 ID 还是 `getPoseFromId` 查询逻辑问题。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615013` |
| JState Key | `/jstate/error/nav-net/invalid_recover_pose` |
| 错误描述 | 指定恢复点位的pose无效 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `usingPose(poseid, offset)` 中 `getPoseFromId(poseid)` 返回空 JSON（poseId 在地图数据中不存在） |
| 直接影响 | world_pose 为空，`usingPose` 最终返回 false（locate 失败），`location_valid_=false` |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：与 615012 不同——615012 是 poseId 本身为 0/非法，615013 是 poseId 合法但在地图数据 `nodes_info_` 中找不到对应的 pose。

## 2 错误触发的功能流程

```mermaid
flowchart TD
    A[usingPose poseid, offset] --> B{!poseid?}
    B -- false --> C[getPoseFromId poseid]
    C --> D{nodes_info_ 是否空?}
    D -- 是 --> E[return empty json]
    D -- 否 --> F{carly_system_ > 2?}
    F -- 是 --> G[find_if node_id == poseid]
    G -- 找不到 --> H[return empty json]
    H --> I[world_pose.empty]
    I --> J[LOGE 5989|usingPose, invalid worldPose]
    J --> K[pubJ3State kInvalidRecoverPose]
    K --> L[/route/error 615013]
```

```text
getPoseFromId(poseid)  @ position_recover.cc:366
  -> nodes_info_.empty() → return empty json
  -> carly_system_ > 2: find_if node_id == poseid
  -> 找不到 → return empty json
  -> pubJ3State(kInvalidRecoverPose, 1, "指定恢复点位的pose无效")
```

## 3 结合日志选择排查方向

```bash
grep -E "5989|usingPose, invalid worldPose|getPoseFromId|node_info is empty"   /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 直接触发 | `5989|usingPose, invalid worldPose,poseId:` | 找不到 | 扩大时间窗 |
| 2 | nodes_info 状态 | `nodes_info_` 非空 | `node_info is empty` 日志 | 地图数据未加载→`已确认`，修复地图加载 |
| 3 | poseId 存在性 | 地图数据中包含该 ID | 地图中查找不到 | 调度下发的 ID 和地图不一致→`已确认` |

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 地图数据中无该节点：poseId 在地图更新后已变化 | 地图更新、调度系统 | 使用地图中存在的新 ID | 同步调度系统和地图的节点 ID 数据 | 同 ID 恢复成功 |
| P1 | nodes_info_ 未加载：`node_info is empty` | 地图加载 getNewMapData | 等待地图加载完成 | 修复地图加载时序或数据 | nodes_info_ 非空 |
| P2 | carly_system_ <= 2 不查询 | 旧版系统 | 升级到 >2 或使用旧版恢复方式 | 统一版本 | 新版正常 |

## 5 修复验证与证据索引

```yaml
error_code: 615013
error_name: invalid_recover_pose
trigger_path: "usingPose() -> getPoseFromId()"
```

| 证据 | 位置 |
|---|---|
| JState key | `health_info.hpp:119` → `kInvalidRecoverPose` |
| 触发调用 | `position_recover.cc:308` |

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615013"
    error_name: "invalid_recover_pose"
    module: "nav-net"
    time_window: 60
  steps:
    - id: classify_trigger_chain
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "5989|usingPose, invalid worldPose"
          on_match:
            trigger_chain: "confirmed"
            goto: diagnose_invalid_recover_pose
        - type: on_no_match:
            action: expand_time_window
            time_window: 120
    - id: diagnose_invalid_recover_pose
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "node_info is empty"
          priority: P1
          on_match:
            conclusion: "nodes_info_ 为空，地图数据未加载"
            root_cause: "地图数据未加载"
            temp_fix: "等待地图加载完成后重试"
            goto: verify
        - type: grep_log
          module: "nav-net"
          pattern: "5989|usingPose, invalid worldPose"
          priority: P1
          context_lines: 5
          on_match:
            conclusion: "poseId 在地图中不存在"
            root_cause: "调度下发的 poseId 与地图数据不匹配"
            temp_fix: "使用地图中存在的点位 ID 重新下发"
            goto: verify
    - id: verify
      checks:
        - type: verify_fix
          grep_pattern: "5989|usingPose, invalid worldPose"
          watch_duration_sec: 60
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
