# 调研：Cursor 式 CoT / 活动时间线（Thought · Explored · Edited）

> **层：** L3 research（非 Living 真源）。  
> **日期：** 2026-09-04  
> **状态：** S0a–S0c + S1 已落地（聚合器、TurnActivity、Diff 联动、真 Thought 通道）；真流式 delta 属 S2。进度仍写 [`foundation-status.md`](../foundation-status.md)。  
> **产品决定：** 主界面去掉 ToolTimeline 与 Goal `progress_checkpoint` 卡片；分支树搁置；Mem 维持 M0/M1。

---

## 0. 本文修正了哪些先前说法

对话里曾混用或偏弱的点，以下为**定稿口径**：

| 议题 | 纠偏 |
|------|------|
| 「软着陆」vs「工具后空回复」 | **不是同一条路。** 软着陆 = `max_tool_iters` 触顶强制收口；工具后空回复 = 模型自己停且 `content` 为空，环合成兜底。Settings 条数狗粮主要是后者（探索空转 → 空停），不是触顶软着陆。 |
| 旧兜底文案 | 「工具调用已完成，但模型未给出文字说明…」是**旧** tools-only 模板。`loop_exit.synthesize_tools_only_reply` 已按编辑意图/是否见过写门做**诚实分支**；勿再当现状唯一文案。 |
| Thought | Cursor 是**推理通道流式、往往先于终稿**；不是事后用工具名拼假 CoT，也不是整轮结束再贴一块「总结思考」。 |
| 「不愿调 propose_edit」 | 产品定性应靠**环侧可观察事件**（从未 `propose_edit` / 催过仍无）；**不要**指望模型在 Thought 或终稿里自我招认。 |
| 空回复只能怪模型？ | **不能。** 模型空停常见，但缺诊断/缺可视/用客服腔填空是产品缺口；有环侧方案（见 §2）。 |
| 阶段顺序 | **先 Explored/Edited UI（不依赖推理 API）**，再真 Thought 流；Thought 流式是体验关键，但 Provider 未就绪时禁止假 Thought。 |

---

## 1. 目标体验（要对齐的形态）

每个用户回合一条可折叠「Agent 活动时间线」，事件按时间穿插：

```text
Worked for 3m 33s ▾
  Explored 2 files, 1 search ▾
    Read … · Grepped …
  Thought 18s ▾          ← 流式增量； ideally 在终稿之前可见
    （reasoning / thinking 原文或 summary）
  Edited 4 files, ran 2 commands  +179 −27 ▾
    Edited … · Ran …
  Thought briefly ▾
助手终稿 Markdown
```

**硬规则：**

1. Thought **只**来自模型 reasoning/thinking 通道（或厂商提供的 summary）；禁止用工具名/轨迹伪造 CoT。  
2. Explored/Edited 来自工具事件；**未 Apply 的 patch 不算「已 Edited」**（可用 Proposed/pending）。  
3. Trusted 下 Diff/Shell **审批卡保留**，不可藏进「已编辑」撒谎。  
4. 无推理模型：不渲染空 Thought 壳，或一行诚实提示「当前模型未提供思考块」；Explored/Edited 仍可用。  
5. 终稿气泡只放用户可见结论；中间旁白进 `note` 或忽略，避免与 Thought 重复。

---

## 2. 空回复、软着陆、诊断——与 CoT 的关系

### 2.1 空回复常见吗？

**在 tool-calling Agent 里常见。** 典型路径：

- 探索若干轮后突然停，且不再出文字；  
- 网关丢 content / 异常空包；  
- 上下文过长或模型策略回避（只读不写、不解释）；  
- 触顶软着陆后模型仍交空总结（环再合成）。

Settings 狗粮：只读工具 → 空停 → 环填模板；**根因是模型未 `propose_edit` + 无终稿**，不是 Diff 没 Apply。

### 2.2 「只有软着陆、没有原因」只能怪模型？

**否。** 责任分层：

| 层 | 责任 |
|----|------|
| 模型 | 空停、绕开、不调写工具（行为源） |
| 环 | 是否把可观察事实写成**短诊断 + 可选下一步**；是否误用「请说明下一步」客服腔掩盖「未编辑」 |
| UI | 是否让人立刻看见「只有 Explored、没有 Edited」 |

**软着陆**本意是预算用尽的诚实收口，**不适合**替代「编辑意图下空转结束」的诊断。后者应走 `edit_nudge` + `synthesize_tools_only_reply`（已部分落地），而不是软着陆话术。

### 2.3 还有哪些解决方案（不只怪模型）

按优先级（可与 CoT 并行）：

1. **环侧诊断文案（已部分有）**  
   - 编辑意图 + 无写门 + 空 content → 一发 `edit_nudge`，再空则诚实「从未 propose_edit」。  
   - 纯探索空停 → 说明「只查阅、无文字」；不逼 edit。  
   - 真软着陆 → 分节「未完成/建议下一步」；编辑意图时可注明从未写文件。

2. **活动时间线（本主题 S0）**  
   - 用户一眼看到 Explored 很多、Edited 为零 → 比任何车轱辘话更直接。

3. **流式 Thought（S1+）**  
   - 结果前看见「还在读 / 准备不改 / 缺信息」→ 更快理解卡点；  
   - **仍不能替代**环侧「未 propose_edit」定性。

4. **产品操作**  
   - 换推理/更听话档案、缩短任务、允许读一次再 edit、YOLO 小步验证。  

5. **明确不做**  
   - 无限催 `propose_edit`（死循环）；  
   - 用 LLM 事后编造「Thought」；  
   - 把所有空停都当成软着陆。

**结论：** 空回复常见 ≠ 只能怪模型；**环诊断 + 活动汇总 +（可选）真 Thought 流**才是完整解。CoT 让原因「可见」，环让结论「可断言」。

---

## 3. Cursor / 业界可确认事实

公开材料**没有**「Explored 2 files」的精确算法；可确认：

- Hooks 有 `afterAgentThought`（思考块结束后的聚合文本 + 可选时长）→ Thought 是一等公民，不是工具流水账。  
- 读写/编辑/Shell 在钩子层分类 → Explored/Edited 是**客户端信息设计**。  
- 「Thought briefly」≈ 极短思考的标签。  
- 真穿插依赖厂商 **interleaved thinking / reasoning 流**（Anthropic thinking + tool_use；OpenAI reasoning summaries；部分网关 `reasoning_content`）。  
- **非推理模型**在 Cursor 里也可以有 Explored/Edited，但没有真 Thought。

市场粗分：带 thinking API 的模型 vs 普通 chat；网关可能剥掉 `reasoning_content`——**档案层必须声明 `supports_reasoning`**。

---

## 4. Loop 现状缺口

| 能力 | 现状 |
|------|------|
| Provider | `chat_complete` 工具环；**无** thinking/reasoning 解析与流式通道 |
| SSE | `tool_*` / `diff` / `shell` / `token` / `progress_checkpoint` / `soft_land` / `edit_nudge`… |
| UI | `ToolTimeline` 逐条工具；Goal 检查点卡片；噪声大 |
| 结束态 | `loop_exit`：编辑意图 nudge + 诚实 tools-only / EMPTY_RESPONSE（与 CoT 互补） |
| 审批 | Diff/Shell 门可用；必须在新 UI 中保留 |

---

## 5. 架构（修订后）

```text
Provider → CompletionParts { thoughts[], content, tool_calls }
         （S1 起；S0 可无 thoughts）
    ↓ SSE：thought(start|delta|end) + 既有 tool/diff/shell/token
Loop → 按时间推进；工具分类；Anthropic 等需回传 thinking
    ↓
Frontend TurnActivity：合并同质段 + 穿插 Thought；终稿单独
```

**原则：** 事件发生顺序 = UI 顺序。流式 Thought 在终稿 `token` 之前渲染。

### 5.1 数据：`TurnActivityItem`

- `kind`: `thought` | `explore` | `edit` | `run` | `note`  
- `id`, `ts_start`, `duration_ms?`, `summary`, `detail`  
- 载荷按 kind：thinking 文本；read/grep 路径；edit `pending|applied|rejected` + +/-；run exit…

### 5.2 工具分桶

| 工具 | 桶 |
|------|-----|
| `list_dir`, `read_file`, `grep`, `read_attachment` | explore |
| `propose_edit`, `propose_delete` | edit |
| `propose_shell` | run |
| `propose_memory` | **note**（不进 Edited 文件统计） |

### 5.3 分组策略

- **默认 B：** 连续同质工具合并为「Explored N…」「Edited…」；中间 Thought 打断合并。  
- **可选 A：** 逐条展开（设置「详细」）。

### 5.4 模型档案（S1）

- `supports_reasoning`, `reasoning_mode`（`none` / anthropic / openai_compatible / …）  
- `reasoning_display`: `full` | `summary` | `hidden`

### 5.5 去掉 / 降级

- **S0：** UI 不渲染 ToolTimeline、不展示 `progress_checkpoint` 卡片。  
- **稍后：** 可关 Goal 检查点**注入**（先藏 UI，避免一次改环过大）。  
- 探索收敛注入可保留，但不做检查点卡片。

### 5.6 与结束态共存

- `edit_nudge` / 诚实合成 / 软着陆 → 可映射为时间线上的 `note`，**不得**标成 Thought。  
- EMPTY_RESPONSE → error，不假装 Worked。

---

## 6. 实现阶段与步骤

### 阶段 0 — Explored/Edited（不依赖推理 API）★ 开工切片

1. 定义前端 `TurnActivityItem` + 纯函数：SSE → activity（分类、合并、pending/applied）。  
2. Pytest/单测：合并被 Thought 打断（Thought 可先 mock）；pending 不计 Edited；memory 不进 Edited。  
3. `TurnActivity.tsx`：Worked for… + 折叠块。  
4. `MessagePairItem`：移除 ToolTimeline 与 checkpoint 展示；挂 TurnActivity；Diff/Shell 不变。  
5. `useMessagePairs` 灌流式 activity；刷新恢复若已有 trace 则从 trace 重建（可简化 MVP）。  
6. `tsc -b` + 人工狗粮：读改跑一轮，Trusted Apply 前后标题正确。

**交付：** 主界面不再是乱轨迹；能看见 Explored/Edited；无假 Thought。

### 阶段 1 — 真 Thought（可先整块，尽快流式）

1. Profile 字段；Provider 解析 `reasoning_content` / thinking 块等。  
2. Loop：`yield thought`；工具环按厂商回传 thinking。  
3. UI：Thought 块穿插；`Thought briefly` / `Thought Ns`。  
4. **流式：** `phase: start|delta|end`，在终稿前可见（产品目标；网关不支持则降级整块，UI 诚实）。  
5. 狗粮：推理模型有 Thought；非推理无假 Thought。

### 阶段 2 — 打磨

- 全链路 stream tool+thinking（大改，单独切片）。  
- 点击 Edited → 滚到 Diff；关检查点注入；可选服务端预聚合。  

### 阶段 3 — 明确不做进 MVP

- 文件 Checkpoint 回滚、Subagent 隔离、分支树 UI、事后 LLM 假 Thought。

### 切片开工序（推荐）

| 切片 | 内容 |
|------|------|
| **S0a** | 类型 + SSE→activity 纯函数 + 测试 |
| **S0b** | TurnActivity UI + 替换轨迹/检查点 |
| **S0c** | pending/applied 与 Diff 联动 |
| **S1a–c** | Profile / provider / loop emit / Thought UI（含流式尽力） |

---

## 7. 坑与纪律

1. YOLO → edit 立即 `applied`；Trusted → `pending` 至 Apply。  
2. Reject → 保留 `rejected`，不进绿汇总。  
3. +/- 从 unified_diff 计；仅 applied 进标题汇总。  
4. activity 上限（如 200）防炸。  
5. 终稿与 Thought 分轨；软着陆/nudge ≠ Thought。  
6. 改后端逻辑附 pytest；前端无自动化 → `tsc` + 人工点。

---

## 8. 验收清单（狗粮）

**完整可执行表（现行）：** [`../dogfood/cot-s1-product-checklist.md`](../dogfood/cot-s1-product-checklist.md)

精简对照：

- [ ] 无推理模型：有 Explored/Edited，无假 Thought。  
- [ ] 推理模型（网关真吐 reasoning）：Thought 在终稿前可见（流式或整块降级有说明）。  
- [ ] Trusted：Apply 前不虚增「已 Edited」。  
- [ ] 编辑意图空转：时间线 Edited=0 + 环诊断（非客服腔软着陆）。  
- [ ] 主界面无 ToolTimeline、无检查点卡片；Diff/Shell 仍可用。

---

## 9. 参考

- Cursor Agent Overview / Hooks（`afterAgentThought` 等）— 产品语义，非实现抄袭。  
- Anthropic extended thinking + interleaved tool use；OpenAI Responses reasoning；兼容网关 `reasoning_content`。  
- 本仓：`loop_exit.py`、`ToolTimeline.tsx`、`MessagePairItem.tsx`、`provider.py`、`foundation-status.md`。
