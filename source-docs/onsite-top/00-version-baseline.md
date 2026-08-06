# 导航子包建议升级版本基线

> 用途：当 AI Agent 排查现场问题时，用本文对比现场运行的各子包版本与建议升级版本是否一致。版本不一致时标记为风险因素。
> 来源：[钉钉文档 - 最新支持的导航版本建议升级指南](https://alidocs.dingtalk.com/i/nodes/QG53mjyd80RMlpD0CX90D4QnV6zbX04vh)

---

## 基线版本快照

### 2409 版本系（`x.2409.x`）

> 从该版本开始，新老 Carly 均可直接升级。
> 信息更新时间：2026-06-08

| 子包 | 原始版本 | 建议升级版本 | 必更 |
|---|---|---|---|
| nav-base | 1.4.35 | 1.4.58 | ✅ |
| jz-motion-common | 0.6.22 | 0.6.35 | ✅ |
| nav-net | 0.3.24 | 0.3.37 | ✅ |
| nav-manager | 0.1.29 | 0.1.48 | ✅ |
| speed-manager | 0.0.9 | 0.0.21 | ✅ |

### 2412 版本系（`x.2412.x`）

> 信息更新时间：2026-06-08

| 子包 | 原始版本 | 建议升级版本 | 必更 |
|---|---|---|---|
| jz-motion-common | 1.2412.10 | 1.2412.20 | ✅ |
| nav-net | 1.2412.33 | 1.2412.52 | ✅ |
| nav-manager | 1.2412.120 | 1.2412.185 | ✅ |
| speed-manager | 1.2412.5 | 1.2412.11 | ✅ |
| jz-pnc | 0.2412.8 | 0.2412.12 | ✅ |
| safe-perception | 0.2.8 | 0.2.12 | ✅ |

---

## Agent 使用方式

### 检查子包版本是否匹配

在诊断流程中，应首先检查现场运行的各子包版本是否 ≥ 建议升级版本：

```bash
# 查询当前运行的子包版本（根据现场环境调整路径）
dpkg -l | grep -E "nav-base|jz-motion-common|nav-net|nav-manager|speed-manager|jz-pnc|safe-perception"
# 或
cat /opt/jz/version_manifest.json 2>/dev/null
# 或通过 jstate 查询
curl -s http://localhost:5002/api/bt/version 2>/dev/null
```

### 版本不一致时的处理

| 场景 | 判定 | 处置 |
|---|---|---|
| 运行版本 < 建议升级版本 | `version_mismatch` | 标记为高风险，优先建议升级 |
| 运行版本 ≥ 建议升级版本 | `version_ok` | 排除版本因素 |
| 无法获取版本信息 | `version_unknown` | 标记为证据缺失 |

### Agent 输出字段

```yaml
version_check:
  baseline_source: "钉钉文档 最新支持的导航版本建议升级指南"
  baseline_updated: "2026-06-08"
  version_series: ""          # 2409 / 2412 / unknown
  checks:
    nav_base: {running: "", recommended: "1.4.58", status: ok/mismatch/unknown}
    jz_motion_common: {running: "", recommended: "1.2412.20", status: ok/mismatch/unknown}
    nav_net: {running: "", recommended: "1.2412.52", status: ok/mismatch/unknown}
    nav_manager: {running: "", recommended: "1.2412.185", status: ok/mismatch/unknown}
    speed_manager: {running: "", recommended: "1.2412.11", status: ok/mismatch/unknown}
    jz_pnc: {running: "", recommended: "0.2412.12", status: ok/mismatch/unknown}
    safe_perception: {running: "", recommended: "0.2.12", status: ok/mismatch/unknown}
  any_mismatch: false
  recommendation: ""          # 升级建议文本
```

---

## 维护说明

| 属性 | 说明 |
|---|---|
| **更新方式** | 从钉钉文档手动同步最新版本号到此文件 |
| **更新频率** | 每次发布新版本建议时更新 |
| **关联知识库** | 钉钉知识库 [最新支持的导航版本建议升级指南](https://alidocs.dingtalk.com/i/nodes/QG53mjyd80RMlpD0CX90D4QnV6zbX04vh) |
| **Agent 加载** | 不作为 Playbook 加载；由诊断流程在 evidence collection 阶段读取版本对照 |
