# Loop Agent 演进路线图

> **架构与新建设真源：** [`architecture-charter.md`](architecture-charter.md)。  
> **本文职责：** 交付阶段、验收口径、排期弹性、远期愿景。与宪章冲突时 **以宪章为准**。  
> **进度 Living：** [`foundation-status.md`](foundation-status.md)（按 A0–A4 / 收编项追踪，不再以 F1–F9 为开新工主轴）。

| 字段 | 值 |
|------|-----|
| **产品名** | Loop Agent |
| **最后更新** | 2026-08-28 |
| **主轴** | 架构阶段 **A0–A4**（绞杀式抽层） |
| **产品原则** | 好用 → 环可靠 → 可选 Goal → 可选监督（Preset）→ 可进化记忆 |

---

## 0. 与宪章的关系

| 问题 | 去哪看 |
|------|--------|
| 分层、依赖、LoopConfig、双管道、Model Registry | **宪章** §1 / §3 |
| Goal 模式 / Preset 默认 | **宪章** §0.2–0.4 |
| Pi M01–M10 借鉴明细 | **宪章** §2 |
| 本季做什么、验收什么 | **本文** §1–§4 |
| 迁移进度、旧 F 项收编状态 | **foundation-status** |

**已废止作开新工依据：** 旧「死抱目标默认脊柱」；旧 Foundation F1–F9 清单式主线；「强审批 = 差异化」叙事。

---

## 1. 产品定位（一句话）

**Loop Agent = 可拆的编码 Agent 外壳（Window + CLI）+ 薄而稳的 Agent 环 + 可选 Goal 模式 + Hermes 式可进化记忆（宪章 §3.5）。**

- 向 Pi 学：**分层、减法、钩子、双管道、树会话、上下文工程**  
- 向自家已验证行为学：**Goal 质量环**（仅 Goal ON）、观察瘦身、失败续环、TurnEvent  
- 向 Hermes 学：**可进化用户记忆**（写入跟 Preset）

**北极星：** 日常工作流里有多少 **可靠的工具环闭环**（好用、少摩擦）；Goal ON 时额外衡量「对照目标收工」比例。

---

## 2. 阶段总览（架构主轴）

```text
A0 立层 / LoopConfig
  → A1 五步管线 + Preset + Goal 开关
  → A2 Model Registry（多档案）
  → A3 双管道事件 + Steering 口
  → A4 Session Tree + convert_to_llm + Compaction 升格
  → B* 产品层（Task / Project OS）仅建在 A0–A4 之上
```

| 阶段 | 主题 | 核心交付 | 成功标准（行为） |
|------|------|----------|------------------|
| **A0** | 立层 | 逻辑包边界；抽 `_run_one_turn`；空 `LoopConfig` | pytest 全绿；环外表不变 |
| **A1** | 可插管线 | before/afterToolCall；YOLO/Trusted；Goal 按钮 + GoalModeHooks | 审批离开 loop 内联；**Goal 默认 OFF** |
| **A2** | loop-ai | 多档案 Base URL/Key/model；按会话选模型 | Settings Cursor 式；LiteLLM 可选档案 |
| **A3** | 事件 | EventSink；SSE/TurnEvent 订管道 A；steer 队列接口 | 嵌套 agent/turn；F6 对齐 |
| **A4** | 会话视图 | parent_id + leaf；convert_to_llm；CompactionEntry 雏形 | regenerate = branch；摘要为 AgentMessage |
| **B\*** | 远期 | Task / Project OS / 多 Agent | **禁止**在 A0–A4 未稳时开干 |

---

## 3. 已完成能力 → 宪章收编（不做废，改挂点）

下列行为 **代码已有**；路线图认定它们是 **资产**，下一刀是 **收编进正确层/钩子**，不是重做一遍产品故事。

| 旧编号 | 行为（保留） | 宪章归属 | Goal OFF | Goal ON | 迁移债 |
|--------|--------------|----------|----------|---------|--------|
| F1 | Turn Goal 抽取/注入/展示 | GoalModeHooks / on_turn_start | 不注入 | 启用 | 焊在 loop；无 Goal 按钮 |
| F2 | 进度检查点 | after_tool_batch | 不跑 | 启用 | 同上 |
| F3 | Reject 结束；timeout/failed 续 1 | after_tool_call + Preset | 简化可用 | 完整 | gate await 在 loop |
| F4 | 观察 slim + data_path | after_tool_call 统一 truncate | ✅ | ✅ | 缺 head/tail 契约 |
| F5 | 裸 python → venv/python3 | coding 环境默认 | ✅ | ✅ | 面窄 |
| F6 | TurnEvent 落库 / 刷新恢复 | 管道 A 子事件 | ✅ | ✅ + turn 边界 | 无 agent/turn 嵌套 |
| F7 | 探索收敛 | after_tool_batch | 不跑 | 启用 | 焊在 loop；UI 未区分 |
| F8 | Goal 变更审计 | Goal 模式留痕 | n/a | 启用 | 无手动改 Goal |
| F9 | 狗粮剧本 | Goal ON 验收 | 可选轻量 | 主剧本 | — |
| — | Diff/Shell/Memory 门 + hunk | beforeToolCall + Preset | YOLO 直通目标 | 同左 | **A1c 默认 YOLO** |
| — | USER.md 记忆提案 | coding + Preset | 跟 Preset | 同左 | A1d：硬上限 + 冻结快照；MEMORY.md 后置 |
| — | 单组 LLM URL/Key | → A2 Registry | — | — | 非多档案 |
| — | compress + preserve_goal | transform_context（M09 升格） | ✅ | 强 Goal section | 粗切点 |
| — | CLI `loop` | window 同 Runtime | — | — | 命令已是 `loop`；Python 包名 `agent_window` 仍后置 |

**纪律：** Goal OFF 后，F1/F2/F7 **不得**再默认打扰用户；实现上必须能关掉（A1 交付点）。

---

## 4. 未做 / 下一刀（按宪章做）

### 4.1 A0 ✅

- [x] 文档与代码约定：逻辑层 + [`layer-boundaries.md`](layer-boundaries.md)；`agent_window.core`  
- [x] `LoopConfig` dataclass + `default` / `with_goal_mode` / `with_preset`  
- [x] 从 `run_agent_loop` 抽出 `_run_one_turn`（1 LLM + 1 tool batch；`TurnOutcome`）  
- [x] import 方向检查：`tests/test_layer_boundaries.py`  
- [x] pytest 全绿、行为不变（160→168，+8 表征用例）  

### 4.2 A1（当前建议开工）

切成可独立验收的竖切，**禁止**一次改 Goal+Preset+管线：

| 切片 | 内容 | 成功标准 |
|------|------|----------|
| **A1a** | `config.goal_mode` 闸门：OFF 不注入/不检查点/不探索收敛 | 新测；现有 Goal 测在 ON 下仍绿 |
| **A1b** | UI Goal 按钮 + session 持久化；产品默认 OFF | 人工点 + API；routes 不再写死 ON |
| **A1c** | 五步工具管线雏形 + `before_tool_call` 收门控 | gate 测仍绿；YOLO 可直通 |
| **A1d** | Preset Trusted/Strict + 记忆有界（§3.5 上限） | Preset 测；满则报错不截断 |

- [x] **A1a** Goal 闸门（loop 内）  
- [x] **A1b** Goal 按钮 + 默认 OFF  
- [x] **A1c** 五步管线 + Preset YOLO/Trusted（gate auto_apply）  
- [x] **A1d** 记忆上限 + 冻结快照  
- [x] GoalModeHooks 收编 F1/F2/F7/F8（F1/F2/F7 ✅；F8 可后置）  

### 4.3 A2

- [x] Model Registry 多档案（base_url / api_key / model_id）  
- [x] Settings UI（Cursor 式档案卡）；ModelPicker 列启用档案  
- [x] `ModelHandle`（无 key）；provider 按 active profile 解析凭证  
- [x] 会话级 `profile_id`（可选后置；全局 active 已够用）  
- [ ] core 全面经 Handle 调 ai（禁止旁路 new client）— 随调用点收紧  

### 4.4 A3

- [x] EventSink：agent/turn/tool 嵌套事件（lifecycle + 扁平 tool 仍保留）  
- [x] SSE + TurnEvent + audit = 管道 A（不等；routes 仍 note_sse 一次）  
- [x] Steering 队列接口；**产品 UI 已撤回**（仅保留 API/队列）  

### 4.5 A4

- [x] `parent_id` + `leaf_id`；regenerate = branch  
- [x] AgentMessage + `convert_to_llm`  
- [x] Compaction 升格（切点 + 6-section）；摘要消息类型  
- [x] Skills 拉模式（清单进 prompt）  

### 4.6 明确暂缓（非 A0–A4 阻塞项）

MCP、网页 fetch/search、PDF 抽取、多 Agent、Project OS 全阶段、Cordis/换皮、原生 Anthropic/Google 翻译器（OpenAI 兼容优先）。

---

## 5. Goal 模式验收（取代旧 §0.4「默认六条」）

### 5.1 Goal OFF（默认）— 「好用的环」

1. 工具环稳定：batch 序正确、失败/空响应可解释  
2. 观察不炸窗（slim / 大输出落盘）  
3. Preset 可运行；默认 YOLO 或 Trusted 不造成弹窗疲劳  
4. 写盘诚实化仍在  
5. 轨迹/中间态可见（TurnEvent 级即可）  

### 5.2 Goal ON — 「对照目标收工」

在 5.1 之上额外：

1. 显式 Goal 可展示、可注入  
2. 检查点能回答相对 Goal 的进度/阻塞  
3. 成功有产物或可核验结论；失败有阻塞 + 已得事实  
4. Reject / 环境失败按 F3 策略续或结束（不静默蒸发）  
5. 触顶软着陆对照 Goal  
6. Goal 变更可留痕  

---

## 6. 技术落点（相对仓库）

| 阶段 | window | core | coding | ai |
|------|--------|------|--------|-----|
| A0 | 少动 | LoopConfig + 抽 turn | — | — |
| A1 | Goal 按钮；Preset 切换 | 五步管线；GoalModeHooks | 工具只 execute | — |
| A2 | Models 设置多档案 | ModelHandle | — | Registry + Client |
| A3 | SSE 订 A；Steer 输入 | EventSink；steer 口 | — | 流式事件对齐 |
| A4 | 树导航（可简） | build_context；convert | — | — |

路径含空格：shell 必须加引号。后端 `backend/.venv`；前端 `npm run dev`。

---

## 7. 风险与纪律

1. **禁止大爆炸重写**；每阶段可运行 + pytest  
2. **禁止**再按旧 F 编号开并行旁路焊进 `loop.py`  
3. **禁止** Goal OFF 时仍强制检查点/探索收敛  
4. tool_calls 与 tool 消息之间 **禁止**插 user（F7 教训）  
5. 审批保留实现，默认走 Preset，不删门控代码  

---

## 8. 排期（弹性）

| 阶段 | 粗估 | 备注 |
|------|------|------|
| A0 | 1–2 周 | 纯结构，行为锁死 |
| A1 | 2–4 周 | 体验拐点（Goal 按钮 + YOLO） |
| A2 | 1–2 周 | 模型设置产品化 |
| A3 | 2–3 周 | 事件树 + steer 口 |
| A4 | 3–5 周 | 树 + 消息模型 + 压缩升格 |

---

## 9. 远期愿景（B\*，非当前主线）

Project OS / Task 卡 / 多 Agent = Goal 在更长周期上的形态；**必须**建在 A0–A4 稳之后。细节见历史讨论；本稿不展开阶段表，避免再次喧宾夺主。

---

## 10. 一句话路线

> **先按宪章把环抽进分层与钩子（A0–A1）→ 模型档案与事件真源（A2–A3）→ 树会话与消息边界（A4）→ 再谈 Task / Project OS。**  
> 已完成的 Foundation 行为全部保留，挂到 Goal 模式与 Preset 上，而不是默认焊死。

---

## 附录. 文档索引

| 文档 | 用途 |
|------|------|
| [`architecture-charter.md`](architecture-charter.md) | **架构真源** |
| [`foundation-status.md`](foundation-status.md) | A0–A4 与收编进度 |
| [`archive/foundation-f4-f6-plan.md`](archive/foundation-f4-f6-plan.md) | 历史 F4/F6 方案（已冻结） |
| [`README.md`](README.md) | docs 地图 |
| 调研/竞品旧文 | 仅背景，不指导开新工 |
