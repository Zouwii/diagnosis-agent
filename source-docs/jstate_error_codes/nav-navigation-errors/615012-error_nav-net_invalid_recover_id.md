# JState 错误码 615012：指定恢复点位的ID无效

> 文档用途：当 AI Agent 在现场日志中发现 `615012` 时，用本文确定是调度下发的 poseId 为 0/空，还是本地地图数据不包含该 ID。

## 1 错误结论

| 字段 | 内容 |
|---|---|
| 错误码 | `615012` |
| JState Key | `/jstate/error/nav-net/invalid_recover_id` |
| 错误描述 | 指定恢复点位的ID无效 |
| 等级 | `level1`（WARN） |
| 直接触发条件 | `usingPose(poseid, offset)` 中 `!poseid`（poseId 为 0 或非法值） |
| 直接影响 | `usingPose` 直接返回 false，定位恢复失败，`location_valid_=false`，容差降为 `kSafeTol=5` |
| 自动恢复条件 | 后续以有效 poseId 成功调用 `usingPose` |
| 本文验证基线 | `RC/1.2603.x @ 744cfcbe352b` |
| 适用前提 | 调度系统通过 `From` 非 lasermark 的导航请求下发恢复定位 |
| META 来源 | `机型3代状态数据-META大全.xlsx` → `异常状态s3` |

**核心判断**：`usingPose()` 第一个检查就是 `!poseid`——如果 poseId 是 0 或未从调度消息中解析到合法 ID，直接返回 false 而不尝试查找。`poseid` 来自调度下发的 `req_msg["PoseId"]`（默认值 -1），如果调未填或填 0，立即触发。

## 2 错误触发的功能流程

```mermaid
flowchart TD
    A[handleNavStarted] --> B{from == lasermark?}
    B -- 否 --> C{pose_ID > 0?}
    C -- 是 --> D[usingPose pose_ID, offset]
    C -- 否 --> E[usingLastPose]
    D --> F{!poseid?}
    F -- true --> G[LOGE 5995|invalid poseId]
    G --> H[pubJ3State kInvalidRecoverId]
    H --> I[/route/error 615012]
    H --> J[return false]
    J --> K[location_valid_=false, tol=kSafeTol]
```

```text
PositionRecover::usingPose(poseid, offset)  @ position_recover.cc:296
  -> if (!poseid) → LOGE "5995|invalid poseId"
  -> HDI->pubJ3State(kInvalidRecoverId, 1, "指定恢复点位的ID无效")
  -> return false
```

## 3 结合日志选择排查方向

```bash
grep -E "5995|invalid poseId|usingPose" /opt/jz/log/nav-net.log | tail -n 200
```

| 顺序 | 检查项 | 正常判据 | 异常判据 | 结论状态与下一步 |
|---:|---|---|---|---|
| 1 | 直接触发 | 出现 `5995|invalid poseId` | 找不到 | 扩大时间窗 |
| 2 | 上游调度 | 调度下发消息中 PoseId > 0 | PoseId 为 0 或缺失 | 修正调度消息 →`已确认` |
| 3 | from 字段 | from != "lasermark"（走 usingPose 分支） | from == "lasermark"（应走 lasermark 分支） | 调度下发模式错误 |

停止规则：命中 `5995` 后优先检查调度消息的 PoseId 字段。

## 4 可能原因与解决方案

| 优先级 | 原因与唯一特征 | 负责链路 | 临时处置 | 根因修复 | 修复验证 |
|---|---|---|---|---|---|
| P1 | 调度下发 PoseId=0/空：`req_msg["PoseId"]` 为 0 或不存在 | 调度系统 | 重新下发带有效 PoseId 的任务 | 修正调度系统中恢复定位的 PoseId 填充逻辑 | 同 PoseId 恢复成功 |
| P2 | API 调用错误：HTTP onPositionRecover 传入非法 poseId | 调用方 | 检查 API 参数 | 修正 API 调用 | 正常 poseId 不再触发 |

## 5 修复验证与证据索引

```yaml
error_code: 615012
error_name: invalid_recover_id
analysis_status: 待确认
trigger_path: "handleNavStarted() -> usingPose()"
```

| 证据 | 位置 |
|---|---|
| JState key | `nav-net/include/common/health_info.hpp:121` |
| 触发调用 | `position_recover.cc:301` |

## 6 Agent 自动排查 Playbook

```yaml
playbook:
  meta:
    error_code: "615012"
    error_name: "invalid_recover_id"
    module: "nav-net"
    time_window: 60
  steps:
    - id: classify_trigger_chain
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "5995|invalid poseId"
          on_match:
            trigger_chain: "confirmed"
            goto: diagnose_invalid_recover_id
        - type: on_no_match:
            action: expand_time_window
            time_window: 120
    - id: diagnose_invalid_recover_id
      checks:
        - type: grep_log
          module: "nav-net"
          pattern: "5995|invalid poseId"
          priority: P1
          context_lines: 10
          on_match:
            conclusion: "poseId 为 0 或非法"
            root_cause: "调度下发的 PoseId 无效"
            temp_fix: "重新下发带有效 PoseId 的任务"
            goto: verify
    - id: verify
      checks:
        - type: verify_fix
          grep_pattern: "5995|invalid poseId"
          watch_duration_sec: 60
          on_match:
            status: still_present
          on_no_match:
            status: verified
```
