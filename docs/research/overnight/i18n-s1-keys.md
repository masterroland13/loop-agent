# 空态与 Settings S1 缺键（建议中英）

> L3 调研。只列缺键和建议文案，供以后接线时粘贴。  
> **本页不改** `src/i18n/zh.ts`、`src/i18n/en.ts`，也不改产品代码。  
> 对照：`src/App.tsx` 空态、`src/components/SettingsPanel.tsx` Agent / About、`src/components/ChatInput.tsx`、`src/i18n/zh.ts` 与 `en.ts`。  
> 行为真源：`backend/src/agent_window/core/preset_hooks.py` 的 `decide_gate_preset`。产品口径：宪章 §0.2（审批是可选策略，默认 Goal 关、Preset 为 YOLO）。

两侧词条必须同键、同构。下面的中文是建议句，接线时可以磨语气，语义以矩阵与 `decide_gate_preset` 为准。

## 空态（empty hero）

落点：`src/App.tsx` 空会话块（logo、标题、居中输入、三颗 pill、底栏）。骨架保持不动。

| 键 | 现状 | 建议 en | 建议 zh |
|----|------|---------|---------|
| `app.emptyHeroTitle` | 两侧都没有。标题是字面量 `What can I help you with?` | What can I help you with? | 今天想做点什么？ |
| `app.emptyNavHint` | 两侧都没有。底栏是字面量 `Use ↑↓ arrows to navigate between messages` | Use ↑↓ arrows to navigate between messages | 用 ↑↓ 在消息间跳转 |

`app.emptyPlaceholder`、`chat.multitask`、`chat.planIdea`、`appExtra.goalOn`、`appExtra.goalOff` 已经有中英，空态输入框、后两颗 pill 和 Goal 的 title 已经在用。不要为它们再造键。

底栏用新建的 `app.emptyNavHint`。`settings.navShortcutsDesc` 现文是「↑/↓ 在消息间跳转，Esc 停止生成」/ “↑/↓ jump messages; Esc stops generation”，多了 Esc，不拿来当空态底栏。

### Goal pill 用 `chat.goal`

空态第一颗 pill 的 `label` 仍是字面量 `"Goal"`。词典里已有：

| 键 | zh | en | 谁在用 |
|----|----|----|--------|
| `chat.goal` | Goal | Goal | `ChatInput` 的 ⋮ 菜单已经 `t('chat.goal')` |
| `message.goal` | 目标 | Goal | 消息旁目标条，不是这颗芯片 |

空态 pill 的 label 接 `chat.goal`。产品词两边都保持 **Goal**，与「多任务 / 规划新想法」并列。

**不要新建 `app.goal`。** `app` 树里没有 `goal`。早先切片草稿里写过 `translate(..., 'app.goal')`，那是过时键名；仓库真键是 `chat.goal`。

## Settings S1（Preset / Goal 叙事）

落点：设置 → Agent 的三档 Choice、记忆确认开关说明、Turn Goal 三段，以及关于页 tagline。默认仍是 YOLO、Goal 关。矩阵只陈述 `decide_gate_preset` 已经做到的事：

| 档 | 写盘 / Shell | 记忆 |
|----|----------------|------|
| YOLO | 自动应用（`action=allow`） | 自动应用 |
| Trusted | 等待确认（`action=wait`） | 跟 `confirm_memory` 开关 |
| Strict | 等待确认 | 始终确认（`force_confirm_memory`，忽略开关为关） |

短标签里的「全程确认」只作按钮提示。细则以矩阵句为准。矩阵里不要写「Strict = 全门控」或「含 hunk」——那是愿景，不是当前差。

Choice 今天是硬编码 `YOLO` / `Trusted` / `Strict`（`SettingsPanel` Agent 区）。`Toggle` 已支持 `disabled`，记忆确认开关还没按档位灰显。

### 新建键

前缀都是 `settings.`。

| 键 | 建议 en | 建议 zh | 接到哪 |
|----|---------|---------|--------|
| `presetYoloLabel` | YOLO · Apply directly | YOLO · 直接应用 | Choice |
| `presetTrustedLabel` | Trusted · Confirm writes | Trusted · 写前确认 | Choice |
| `presetStrictLabel` | Strict · Always confirm | Strict · 全程确认 | Choice |
| `presetMatrixYolo` | Writes, shell, and memory apply automatically | 写盘 / Shell / 记忆均自动应用 | 三档下只读矩阵 |
| `presetMatrixTrusted` | Confirm writes and shell; memory follows the toggle | 写盘 / Shell 需确认；记忆跟随下方开关 | 同上 |
| `presetMatrixStrict` | Confirm writes and shell; memory always confirms | 写盘 / Shell 需确认；记忆始终确认 | 同上 |
| `confirmMemoryDescYolo` | Always auto under YOLO — this toggle has no effect | YOLO 下始终自动 · 此开关无效 | YOLO 时的说明，开关灰显 |
| `confirmMemoryDescTrusted` | Takes effect under Trusted | Trusted 下生效 | Trusted 时的说明，开关可点 |
| `confirmMemoryDescStrict` | Always confirm under Strict — this toggle has no effect | Strict 下始终确认 · 此开关无效 | Strict 时的说明，开关灰显 |

灰显时不要顺便 PATCH 把 `confirm_memory` 写成 false，否则从 Strict / YOLO 切回 Trusted 会丢掉用户原来的开关值。

三列按钮宜短。行为句子放矩阵，不要塞进 Choice。

### 已有键：改文案，不改键名

`settings.preset` 中文已经是「审批档位（Preset）」，英文是 “Approval preset”。标题保留，用来和模型区「从预置添加」（`settings.addPreset`）分开。本刀不改模型 API，也不改 `addPreset` 的文案。

`settings.presetDesc` 现在把三档挤在一句里。矩阵落地后改成指向矩阵：

| | 建议 |
|--|------|
| zh | 全局审批策略。三档行为见下方矩阵。与会话里的 Goal 芯片无关。 |
| en | Global approval policy. See the matrix below. Independent of the session Goal chip. |

`settings.confirmMemory`（「写入记忆前确认」/ “Confirm before writing memory”）标签保留。现在的 `settings.confirmMemoryDesc` 一句里藏了三档。接线时按 `loopPreset` 改用上面三个 Desc。旧键改成与 `confirmMemoryDescTrusted` 相同的句子，避免还有调用点时闪出过时的三档长句。

`settings.turnGoalTitle` / `turnGoalBody` / `turnGoalCheckpoint` 键名保留，正文重写。现在读起来像设置里有一个全局 Goal 开关，也没写它和 Preset 正交。设置只解释机制，不提供「打开 Goal」的开关。

`turnGoalTitle`

| | 建议 |
|--|------|
| zh | 本轮目标（Turn Goal）· 会话芯片 · 默认关 |
| en | Turn Goal · per-session chip · off by default |

`turnGoalBody`

| | 建议 |
|--|------|
| zh | 这是当前会话输入区上的 Goal 芯片，默认关闭。与全局审批档位无关：打开 Goal 时仍可以是 YOLO，写盘和命令不会因此弹出审批。每轮从用户消息抽取目标并注入 loop；短回复如「好的 / 继续」继承上一轮实质目标。消息旁显示目标条；目标变更写入审计并标「已变更」。 |
| en | The Goal chip on this session’s composer, off by default. It is independent of the global approval preset: Goal can be on while YOLO still applies writes and commands with no approval card. Each turn extracts a goal from the user message and injects it into the loop; short replies like “ok / continue” inherit the previous real goal. A Goal strip appears beside the message; changes are audited and marked “changed”. |

`turnGoalCheckpoint`

| | 建议 |
|--|------|
| zh | 检查点：每 N 次工具，或审批返回之后，模型说明相对目标的进度、阻塞和下一步，出现在消息旁可折叠的检查点条。这不是额外的审批。 |
| en | Checkpoints: every N tools, or after an approval returns, the model reports progress, blockers, and next steps on a collapsible strip beside the message. This is not an extra approval. |

`settings.aboutTagline` 现在是「可监督的 AI 编码工作台 · React + FastAPI + SQLite」/ “Supervised coding agent workbench · React + FastAPI + SQLite”。宪章把「可选监督」放在好用之后，关于页不再用「可监督 / Supervised」当产品人格。

| | 建议 |
|--|------|
| zh | 本地编码 Agent 工作台 · 可选 Goal 与审批档位 · React + FastAPI + SQLite |
| en | Local coding agent workbench · optional Goal and approval preset · React + FastAPI + SQLite |

## 接线时一起看的控件态

这些不是新键，和上面的句子绑在同一刀，否则文案会对不上手感：

- `confirmMemory`：`loopPreset` 为 `yolo` 或 `strict` 时 `disabled`；`trusted` 时可点。
- 设置里不放 Goal 总开关。开、关 Goal 仍只在会话芯片（空态 pill / `ChatInput` 菜单）。
- 空态 Goal 的 title 继续用已有的 `appExtra.goalOn` / `appExtra.goalOff`。正交那句放在重写后的 `turnGoalBody`。

## 本清单不收的字面量

模型卡上的 Base URL、API Key、Model ID、Temperature，以及厂商名、模型 id，中英界面都保持英文（见变更记录里「模型服务文案」那条）。上下文上限旁的 `tokens`、记忆用量的 `chars`、资产页的 `USER.md` / `Preset` 行、关闭按钮的无障碍名，都不在这刀。空态 logo 的紫色 `drop-shadow` 是样式，不是 i18n 键。
