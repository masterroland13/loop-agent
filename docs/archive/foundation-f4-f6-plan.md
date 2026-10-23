# Loop Agent Foundation：F4/F6 方案与决策（Stable Reference）

> ⚠️ **状态：冻结（2026-08-28）。**  
> **架构真源：** [`../architecture-charter.md`](../architecture-charter.md)。  
> **进度：** [`../foundation-status.md`](../foundation-status.md)（A0–A4 / 收编表）。  
> **交付阶段：** [`../agent-window-roadmap.md`](../agent-window-roadmap.md)。  
> 本文仅保留 F4/F6 三档方案考古价值；**不再**作为开新工或进度裁判。

> ~~本文档相对稳定…~~（旧说明废止）

---

## 文档分工（已过时 — 见宪章）

| 文档 | 现行职责 |
|------|----------|
| [`../architecture-charter.md`](../architecture-charter.md) | 架构真源 |
| [`../agent-window-roadmap.md`](../agent-window-roadmap.md) | 阶段交付 |
| [`../foundation-status.md`](../foundation-status.md) | Living 进度 |
| **本文** | 冻结考古 |

---

## 目录

1. [背景与决策摘要](#1-背景与决策摘要)
2. [F4 / F6 是什么](#2-f4--f6-是什么)
3. [完整版工作量与难度](#3-完整版工作量与难度)
4. [三档方案：MVP / 中间档 / 完整版](#4-三档方案mvp--中间档--完整版)
5. [已确认的产品决策（UI 等）](#5-已确认的产品决策ui-等)
6. [推荐执行顺序](#6-推荐执行顺序)

**Living：** [§5 全功能对照 · §6 最小完整 · §8 backlog · §0.4 验收](../foundation-status.md)

---

## 1. 背景与决策摘要

### 1.1 当前进度

→ 见 **[`../foundation-status.md` §1 快照](../foundation-status.md#1-快照foundation-f1f9)**（含 Foundation 整体占比与 F1–F9 表）。

### 1.2 已确认的决策

| 决策 | 内容 |
|------|------|
| **F4 + F6 都要做** | 对日常使用体验影响大 |
| **不一次上「双完整版」** | 约 11–12 人天，过重 |
| **采用中间路线 ★** | F6 中间 → F4 中间，约 7–8 人天，约完整版 **68%** 体验 |
| **不做双 MVP 当终点** | MVP 缺最明显痛点 |
| **User 消息展开发送** | 方案 **B**：新追问接在末尾，不改历史 |
| **展开时底部输入框** | 灰色禁用；卡片内为主 |

---

## 2. F4 / F6 是什么

### 2.1 在 Loop 脊柱中的位置

```text
                    死抱目标（Turn Goal）
                           │
     观察（Observe）◄─────┼─────► 决策（Decide）
           ▲               │               │
           │               ▼               ▼
      F4 瘦身回灌      F2 检查点        行动（Act）
           │               │               │
           └───────────────┴───────────────┘
                           │
                    F6 落库给人看
```

- **F4**：改「**模型下一拍看到什么**」（loop 内部质量）
- **F6**：改「**人这一拍看到什么**」（UI / 刷新 / 信任）
- 理想形态：**库里存 full，给模型喂 slim**

### 2.2 F4 — 观察结构化 / 截断

**问题：** 工具结果原样进 `working[]`；`compress.py` **不压** loop 内 tool 消息。

**完整版：** 统一 `slim_tool_result`；分工具策略；slim/full 双份；配置 + pytest + ToolTimeline 展开 full。

**验收：** 同任务 token↓；失败结构化 `{status, error, hint}`。

### 2.3 F6 — 中间态落库可见

**问题：** SSE 内存态 `toolTrace`；刷新丢失；turn 中 assistant 空白。

**完整版：** `TurnTrace` / `events[]`；turn 初占位 + 增量写；API 灌回；流中刷新合并；CLI。

**验收：** §0.4 第 6 条；无空白轮。

---

## 3. 完整版工作量与难度

| 阶段 | 人天 | 难度 |
|------|------|------|
| 共用 TurnEvent schema | 1–1.5 | 中 |
| F6 完整（后端+前端） | 4–5.5 | **中高** |
| F4 完整 | 2–3 | 中 |
| 测试 + F9 + 联调 | 2–3.5 | 中～中高 |

**合计约 9–12 人天。**

**难点：** F6 占位+增量时序；F4 分工具规则防截错。

---

## 4. 三档方案：MVP / 中间档 / 完整版

### 4.1 F4

| 档位 | 人天 | ≈完整版 |
|------|------|---------|
| MVP | 1–1.5 | ~25% |
| **中间档 ★** | 累计 ~3 | **~65%** |
| 完整版 | 累计 ~5 | 100% |

中间档：4 类工具 formatter + 全局上限 + gate 摘要。

### 4.2 F6

| 档位 | 人天 | ≈完整版 |
|------|------|---------|
| MVP | 1.5–2 | ~30% |
| **中间档 ★** | 累计 ~4–5 | **~70%** |
| 完整版 | 累计 ~6–7 | 100% |

中间档：占位 + 增量 events + 刷新恢复。

### 4.3 组合

| 组合 | 人天 | ≈完整版能力 |
|------|------|-------------|
| 双 MVP | ~3–3.5 | ~28% |
| **双中间档 ★** | **~7–8** | **~68%** |
| 双完整 | ~11–12 | 100% |

### 4.4 共用数据结构（Day 0）

```typescript
TurnEvent {
  type: 'tool_start' | 'tool_result' | 'progress_checkpoint' | 'gate' | ...
  ts: number
  tool?: string
  status?: string
  summary: string      // UI + F4 → 模型
  full_ref?: string    // 中间档 inline ≤8KB；完整版 → data_path
}
```

---

## 5. 已确认的产品决策（UI 等）

### 5.1 User 消息卡片

| 行为 | 决策 |
|------|------|
| 压缩对象 | 仅 **user** 消息 |
| 默认 | 最多 **4 行** |
| 展开 | 可编辑 + ChatInput 工具栏 |
| 发送 | **B**：新追问接末尾 |
| 底部输入 | 展开时灰色禁用 |
| 收起 | 点击页面其它区域 / Esc |

### 5.2 输入草稿

按 session 存；删 session 清草稿；新建 session 为空。

---

## 6. 推荐执行顺序

```text
Day 0     TurnEvent schema
   ↓
F6 中间   信任感（刷新可恢复）
   ↓
F4 中间   loop 质量（token↓）
   ↓
F9 狗粮   证明能用
   ↓
按需增量  → 完整版边角
   ↓
v1        Steer + 时间线（吃 F6 真源）
```

**不建议：** 双 MVP 终点；跳过 F6 先做 F4；F6 未完成就做 v1 时间线 UI。

---

*稳定参考，2026-08-22 起稿。进度见 [`../foundation-status.md`](../foundation-status.md)。*
