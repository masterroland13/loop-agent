# 前端窗口层职责地图（对照 coding / core）

> L3 调研，2026-11-04，对照当时 `main` 上的源码。  
> **只画边界与文件，不改产品。** 冲突时以 [`architecture-charter.md`](../../architecture-charter.md) §1 为准，落点表以 [`layer-boundaries.md`](../../layer-boundaries.md) 为准。  
> 物理包名仍是 `agent_window`。下文用逻辑层名。

## 四层里前端站在哪

```text
loop-window   前端 src/*  +  api/*、models.py、cli/*、会话库
     ↑
loop-coding   tools/*、补丁 / Shell / 记忆 / Skills / 工作区 / 压缩
     ↑
loop-agent-core   Agent 环、LoopConfig、Goal 钩子、Preset 钩子、Turn
     ↑
loop-ai       模型档案、OpenAI 兼容 Client
```

箭头只向上。前端整段 `src/` 都属于 **loop-window** 的显示半边。它画壳、把人的选择写成 HTTP、把 SSE 和列表画成气泡、目标条和门控卡。

| 层 | 这一层负责 | 前端不拿过来的事 |
|----|------------|------------------|
| **前端 window** | 布局、文案、本地外观、按钮状态、乐观更新后回滚 | 抽目标、跑检查点、决定审批、写工作区文件 |
| **window 后端**（同一逻辑层） | HTTP/SSE、SQLite 会话、`agent_settings.json`、拼系统提示、等 UI 决定 | 在 `routes.py` 里散落 `if goal` 策略 |
| **coding** | 工具执行、沙盒、记忆正文、Skills 目录、压缩算法 | 弹窗、Goal 按钮、主题 |
| **core** | `run_agent_loop`、`LoopConfig` 钩子、Turn 状态、Goal ON 时的注入/检查点/探索收敛 | import FastAPI / SQLAlchemy / React |

系统提示在 window 后端拼好再交给 core。core 只吃拼好的 system 和 `transform_context`。工具内部不写「必须审批」；Preset 在 `beforeToolCall` 里给出 allow / wait，等待发生在 window（页面或 CLI）。

## 三条竖切怎么分家

| 竖切 | 前端拥有 | coding 拥有 | core 拥有 |
|------|----------|-------------|-----------|
| **空会话英雄区** | 无消息时的居中列：图标、标题、高输入框、三颗胶囊 | 无 | 无 |
| **Goal** | 开关、钉住的句子、消息上的目标条 | 无 | `goal_mode` 为真时装上 F1/F2/F7 钩子；抽取与继承在 `agent/goal.py` |
| **Settings** | 11 个分区的面板；外观与快捷键只留在浏览器 | 记忆正文、Skills 目录、工具名录 | Preset 钩子、环的轮数/检查点/探索阈值（数字由 window 存好再传入） |

模型档案卡在 Settings 里，落点是 **loop-ai**（`services/model_registry.py`），不经 coding，也不进 core 类型。

---

## 空会话英雄区

当前会话还没有消息、不在流式输出、消息列表也已经灌完时，主列换成居中一屏。判定在 `App`：

```ts
const isEmpty = pairs.length === 0 && !isStreaming && !isPairsHydrating
```

`isPairsHydrating` 为真时继续留在对话布局，避免切会话时英雄区和底栏来回闪。

这一屏的结构（`App.tsx` 的 `isEmpty` 分支）：

1. `public/favicon.svg`，标题硬编码英文 `What can I help you with?`
2. 若已有待决门控，同屏挂 `DiffPanel` / `ShellPanel` / `MemoryPanel`（面板归门控，不归英雄区）
3. `ChatInput` `variant="center"`，占位符走 `app.emptyPlaceholder`
4. 三颗 `PillButton`：`Goal`（英文硬编码）、Multitask、Plan
5. 页脚硬编码英文 `Use ↑↓ arrows to navigate between messages`

有消息之后同一套输入能力改走底栏：`ChatInput` `variant="bottom"`，Goal / Multitask / Plan 收进 ⋮。两套壳调用 `App` 里同一组 `handleGoalModeToggle` / `handleMultitask` / `handlePlanIdea`。后两个只把 i18n 模板写进草稿并 toast，不调 core。

标题和页脚还没进 `src/i18n`。胶囊可见文字是硬编码的 `Goal`，悬停说明走 `appExtra.goalOn` / `goalOff`。占位符、Plan/Multitask 模板和 toast 已经进 i18n。

工作区还没绑定时，`App` 先整页挂 `SetupWizard`（填一个模型，再选或新建文件夹）。绑定之后才进入主列。英雄区只出现在主列里。

### 文件

| 文件 | 职责 |
|------|------|
| `src/App.tsx` | `isEmpty` 分支、`PillButton`、标题与页脚、三个点击处理 |
| `src/components/ChatInput.tsx` | `variant="center"` 为高输入框；底栏才渲染 ⋮。文件头注释写明 center = empty hero |
| `src/styles/index.css` | `.composer-shell`（空会话高盒子）、`.composer-chip`（胶囊） |
| `src/hooks/useMessagePairs.ts` | `isPairsHydrating`，挡住空列表闪屏 |
| `src/i18n/zh.ts`、`src/i18n/en.ts` | `app.emptyPlaceholder`、`appExtra.planTemplate`、`appExtra.multitaskTemplate`、`app.planFilled`、`app.multitaskFilled` |
| `public/favicon.svg` | 英雄区图标 |
| `src/components/SetupWizard.tsx` | 未绑定工作区的另一屏，先于主列 |

同屏但归属门控：`src/components/DiffPanel.tsx`、`ShellPanel.tsx`、`MemoryPanel.tsx`。

coding / core：这条竖切没有对应文件。门控卡点下去之后，执行仍在 coding（`services/patches.py`、`services/shell.py`、`services/memory.py`），等不等待由 core 的 Preset 钩子决定。

---

## Goal

开关是**会话**字段，默认关。亮起之后这一会话才抽取/注入目标、跑检查点与探索收敛。关掉之后 SSE 的 `meta` 不再带 `goal` 键，消息上的目标条也就没有数据。

两条状态分开：

| 状态 | 存在哪 | 前端怎么用 |
|------|--------|------------|
| `session.goal_mode` | SQLite | 胶囊 / ⋮ 的按下态。`useSessions` 乐观写入，失败滚回 |
| `session.pinned_goal` | SQLite，最长在后端规范化 | Goal 亮时，输入框上方一行。失焦或 Enter 提交；清空则把钉住句子去掉 |
| 本轮 `meta.goal` | 该轮 SSE / 消息上的 turn meta | `MessagePairItem` 画目标条；与上一轮不同则标「已变更」 |

Settings 的 Agent 分区只有一段说明（`settings.turnGoal*`），没有开关。开关只在英雄区胶囊和底栏 ⋮。

前端到后端的写路径：

```text
Pill / ⋮  →  useSessions.setGoalMode
          →  PATCH 会话 { goal_mode }
          →  storage.update_session_goal_mode

钉住行    →  useSessions.setPinnedGoal
          →  PATCH 会话 { pinned_goal }
          →  agent/goal.normalize_pinned_goal
          →  storage.update_session_pinned_goal
```

发消息时 window 后端用会话上的两个字段调用 `core/goal_hooks.resolve_session_goal`，再 `LoopConfig.from_settings(goal_mode=..., preset=...)`。`with_goal_mode(True)` 装上注入、检查点、探索收敛；`False` 清掉这些钩子槽，`loop.py` 里不再为这三件事散落 `if goal_mode`。F8 变更审计在 routes 里记，不在环中途记。

软着陆仍可能读到环内的 `turn_goal`；Goal OFF 时传给环的有效目标是空。这篇只记这个缝，不改环。

### 文件（前端）

| 文件 | 职责 |
|------|------|
| `src/App.tsx` | `handleGoalModeToggle`；英雄区胶囊；`inputToolbar` 把开关和钉住回调传给底栏与展开的用户卡 |
| `src/components/ChatInput.tsx` | ⋮ 里的 Goal 项；`pinnedGoalRow`；Goal 亮着时底栏改成高盒子 |
| `src/components/MessageList.tsx` | 把 `inputToolbar` 上的 Goal 字段传到每一对 |
| `src/components/MessagePairItem.tsx` | 目标条（`pair.goal` 或 `turnMeta.goal`）和「已变更」 |
| `src/components/UserMessageCard.tsx` | 展开编辑时把 Goal 行交给里面的 `ChatInput`（`variant="card"`） |
| `src/hooks/useSessions.ts` | `goalMode` / `pinnedGoal` 派生；`setGoalMode` / `setPinnedGoal` |
| `src/api/agent.ts` | `updateSessionGoalMode`、`updateSessionPinnedGoal` |
| `src/components/SettingsPanel.tsx` | Agent 分区的说明文，不写 `goal_mode` |
| `src/components/AuditPanel.tsx` | `turn.*` 与事件名含 `goal` 的行用同一套摘要 |
| `src/i18n/zh.ts`、`src/i18n/en.ts` | `chat.goal`、`chat.pinnedGoal`、`message.goal`、`message.goalChanged`、`appExtra.goalOn` / `goalOff`、`settings.turnGoal*` |

### 对侧文件（不要搬进组件）

| 层 | 文件 | 职责 |
|----|------|------|
| window 后端 | `backend/src/agent_window/api/routes.py` | 改会话字段；拼 `LoopConfig`；Goal OFF 时 meta 省略 `goal` |
| window 后端 | `backend/src/agent_window/models.py` | `sessions.goal_mode`、`pinned_goal` |
| window 后端 | `backend/src/agent_window/services/storage.py` | `update_session_goal_mode`、`update_session_pinned_goal` |
| window 后端 | `backend/src/agent_window/schemas.py` | 会话补丁体 |
| core | `backend/src/agent_window/core/loop_config.py` | `from_settings` / `with_goal_mode` |
| core | `backend/src/agent_window/core/goal_hooks.py` | 按开关安装或清空 F1/F2/F7 |
| core | `backend/src/agent_window/core/tool_hooks.py` | 批次钩子只在 Goal ON 时注入 |
| core | `backend/src/agent_window/agent/goal.py` | 抽取、继承、钉住优先、`normalize_pinned_goal` |
| core | `backend/src/agent_window/agent/checkpoint.py` | 进度检查点 |
| core | `backend/src/agent_window/agent/exploration.py` | 探索收敛 |
| core | `backend/src/agent_window/agent/loop.py` | 跑环；有效目标在 Goal OFF 时为空 |

coding 没有 Goal 文件。

---

## Settings

面板由侧栏页脚打开，也由 `Ctrl+,` 打开（快捷键区把该键位写死在说明里）。`showSettings` 在 `App`。外观变更立刻 `applyTheme` / `applyFontSize`；其余键交给 `useSettings`。

存储切成两半：

| 键 | 存哪 | 谁消费 |
|----|------|--------|
| `theme`、`fontSize`、`language`、`enterToSend`、`shortcuts` | 浏览器 `localStorage` 键 `agent-chat:settings`（主题另有 `agent-chat:theme`） | 只影响壳。语言切换 `setApiErrorLocale`，不改变模型语言 |
| `autoCompress`、`confirmMemory`、`loopPreset`、`contextLimit`、`activeSkills`、`approvalTimeoutSec`、`maxToolIters`、`checkpointEveryNTools`、`explorationRepeatThreshold` | `PUT /api/settings` → 用户数据目录 `agent_settings.json` | window 后端读出后装进 `LoopConfig` 或 coding |
| 模型档案、温度、max tokens | `model_profiles.json`（loop-ai） | 发消息时按会话 `profile_id` 选 client |
| 记忆正文 | 用户数据目录里的 USER / 项目记忆文件 | coding `services/memory.py` |
| `disabled_tools` | 同一份 `agent_settings.json`；面板直接 `updateAgentSettings`，不经过 `useSettings` 的键集合 | `agent/loop.py` 组工具列表时滤掉。这是环在读窗口设置，地图只记录缝 |

「数据」分区的重置只删上述两个 `localStorage` 键然后刷新。`agent_settings.json` 和模型档案还在。导出设置下载的是浏览器里的 `SettingsState`，导出审计再拉 `/api` 的审计列表。

### 分区 → 层

| 分区 id | 面板在做什么 | 落点 |
|---------|----------------|------|
| `model` | 档案卡：预置、增删改、激活、测试、温度与 max tokens | loop-ai `services/model_registry.py`、`services/provider_presets.py`。密钥不进 `localStorage` |
| `preferences` | 主题 / 字号 / 语言 | 浏览器 |
| `agent` | 自动压缩、记忆确认、Preset 三档、上下文上限、审批超时、工具轮数、检查点间隔、探索阈值、停用工具、Turn Goal 说明 | JSON 设置。Preset → `core/preset_hooks.py`。轮数/检查点/探索阈值 → core 的 Turn / goal 钩子。`confirm_memory` 被 Preset 读取（strict 强制确认）。压缩算法在 coding `services/compress.py`，由 window 装进 `transform_context` |
| `skills` | 列出并勾选 | coding `services/skills.py`；勾选结果写入 `active_skills`。系统提示仍由 routes 拼 |
| `memory` | 编辑用户记忆与项目记忆 | coding `services/memory.py` |
| `cli` | 静态命令说明 | 无运行时写入 |
| `assets` | 只读：健康、会话数、工作区、当前设置摘要 | window 的 assets 接口 |
| `audit` | 内嵌 `AuditPanel` | window `services/audit.py` |
| `shortcuts` | Enter 发送、方向键导航开关；键位表是静态文案 | 浏览器。真正的 Ctrl+, 监听在 `App` |
| `data` | 导出、重置浏览器副本 | 见上 |
| `about` | 版本与文档路径文案 | 无运行时写入 |

相邻入口：`src/components/ModelPicker.tsx` 只改当前会话的 `model_id` / `profile_id`，不改档案卡。`src/components/SetupWizard.tsx` 在没有工作区时写第一份档案。

### 文件（前端）

| 文件 | 职责 |
|------|------|
| `src/components/SettingsPanel.tsx` | 面板、11 个分区、档案卡、记忆编辑、工具勾选 |
| `src/components/AuditPanel.tsx` | 审计分区 |
| `src/components/ChevronIcon.tsx` | 分区导航箭头（侧栏等处共用） |
| `src/hooks/useSettings.ts` | 默认值、`localStorage`、`AGENT_KEYS` 与 `/api/settings` 双向同步 |
| `src/hooks/useTheme.ts` | 把主题应用到文档 |
| `src/App.tsx` | 开关面板、`handleSettingChange`、挂载 `SettingsPanel` |
| `src/components/Sidebar.tsx` | 页脚设置按钮（展开与收起各一颗） |
| `src/api/agent.ts` | `fetchAgentSettings`、`updateAgentSettings`、档案、Skills、记忆、工具、assets、审计 |
| `src/i18n/zh.ts`、`src/i18n/en.ts`、`src/i18n/index.tsx` | `settings.*` 与壳层文案 |

### 对侧文件

| 层 | 文件 | 职责 |
|----|------|------|
| window 后端 | `backend/src/agent_window/services/agent_settings.py` | `agent_settings.json` 的默认值、夹紧、读写 |
| window 后端 | `backend/src/agent_window/api/routes.py` | `/api/settings`、档案、skills、memory、tools |
| window 后端 | `backend/src/agent_window/schemas.py` | `AgentSettings` 请求/响应 |
| core | `backend/src/agent_window/core/loop_config.py` | `from_settings(goal_mode, preset)` |
| core | `backend/src/agent_window/core/preset_hooks.py` | yolo / trusted / strict；`confirm_memory` |
| core | `backend/src/agent_window/agent/checkpoint.py` | 间隔夹紧（设置加载时调用） |
| core | `backend/src/agent_window/agent/exploration.py` | 重复阈值夹紧 |
| core | `backend/src/agent_window/agent/loop.py` | 读 `disabled_tools`、`max_tool_iters` 跑环 |
| coding | `backend/src/agent_window/services/memory.py` | USER / 项目记忆正文 |
| coding | `backend/src/agent_window/services/skills.py` | 技能目录与 `active_skills` |
| coding | `backend/src/agent_window/services/compress.py` | `auto_compress` 打开后的压缩 |
| coding | `backend/src/agent_window/tools/registry.py` | 工具名录；停用列表不在这里写死 |
| loop-ai | `backend/src/agent_window/services/model_registry.py` | 档案与密钥 |
| loop-ai | `backend/src/agent_window/services/provider_presets.py` | 设置页「从预置新建」 |
| loop-ai | `backend/src/agent_window/services/llm_config.py` | 旧的单组 URL/Key 适配 |

---

## 改界面时怎么用这张图

1. 英雄区、Goal 胶囊、Settings 分区：只动上表 `src/` 文件，外加已经存在的 HTTP。  
2. 抽取目标、检查点、探索收敛、Preset 的 allow/wait：改 core 钩子，让 `loop.py` 继续只调用钩子。  
3. 写盘、Shell、记忆正文、Skills 目录、压缩：改 coding。Settings 只保存开关和数字。  
4. 新调研继续放在 `docs/research/`。这篇不改 `foundation-status.md`。
