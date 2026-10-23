# Loop Agent 架构宪章（Architecture Charter）

> **本文是架构与新建设的唯一真源。**  
> 产品边界、分层、原语、重构阶段、Goal/Preset/Model Registry 等，**一律以本文为准**。  
> **交付阶段与排期：** [`agent-window-roadmap.md`](agent-window-roadmap.md)（A0–A4）。  
> **进度 Living：** [`foundation-status.md`](foundation-status.md)（收编表 + 验收勾选）。  
> 与路线图/进度文档冲突时 **以本文为准**。  
> **Pi 源码学习：** §2 吸收 M01–M10（主线完结）。

| 字段 | 值 |
|------|-----|
| **产品名** | Loop Agent |
| **最后更新** | 2026-09-02 |
| **状态** | Living — A0–A4 架构主轴已完成；穿插收编债 + 产品缺口（切支 UI 等） |
| **权威** | **唯一**架构 / 新建设裁判文档 |

---

## 0. 宪章裁判规则

1. **分层冲突** → 以本文 §1、§3 为准（谁能 import 谁、职责边界）。  
2. **产品体验冲突** → 以本文 §0.2 为准（好用优先；Goal / 审批为可选模式）。  
3. **与旧路线图 / Foundation 冲突** → **一律以本文为准**；旧文档不构成否决权。  
4. **实现细节冲突** → 以代码 + pytest 行为为准；宪章描述「目标态」，允许渐进迁移。

---

## 0.1 产品一句话

**Loop Agent = 可拆分的编码 Agent 外壳（Window + CLI）+ 薄而稳的 Agent 环 + 可选 Goal 模式 + Hermes 式可进化记忆（§3.5）。**

向 Pi 学 **整体感与分层**；向自家 Foundation 学 **Goal 质量环**（仅在 Goal 模式启用）；向 Hermes 学 **跨会话 USER.md 记忆**。  
整体功能可以比 Pi **更厚**（diff 审批、hunk、Skills、附件等保留），但 **依赖必须单向、职责必须一句话能说清**。

---

## 0.2 产品原则（2026-08 纠偏）

| 优先级 | 原则 | 含义 |
|--------|------|------|
| 1 | **好用** | 少摩擦、能收工；默认不折磨用户 |
| 2 | **环可靠** | 工具 batch 序正确、失败可解释、空响应有处理 |
| 3 | **可选 Goal** | 点「Goal」才进入死抱目标模式（见 §0.3） |
| 4 | **可选监督** | 审批 / Strict Preset 按需开，不是产品人格 |
| 5 | **记忆可进化** | 有界 curated + 冻结快照 + Preset（§3.5）；非无限堆历史 |
| 6 | **轨迹可回放** | Trace/Turn 事件真源（渐进落地） |

**不再作为首页叙事：** 「强审批门是核心差异化」。门控 **保留实现**，降级为 **Preset 策略**（YOLO / Trusted / Strict）。

---

## 0.3 Goal 模式（可选，非默认脊柱）

### 行为

| 状态 | UI | Runtime |
|------|-----|---------|
| **Goal OFF（默认）** | 输入区旁 Goal 按钮未亮 | 最简 Agent 环 + 观察瘦身 + 写盘诚实化；**不**注入 Turn Goal、**不**跑检查点/探索收敛 |
| **Goal ON** | Goal 按钮亮起；展示目标条 | 启用 F1/F2/F7 等：抽取/注入 Goal、进度检查点、探索收敛、触顶软着陆对照目标 |

### 与路线图的关系

路线图以 **A0–A4** 为交付主轴。Goal 模式四出口 / 质量环验收仅在 **Goal ON** 时适用（见路线图 §5.2）；**Goal OFF** 时适用路线图 §5.1「好用的环」。

### 实现归属

- **开关与展示：** `loop-window`（按钮、目标条、SSE）  
- **策略逻辑：** `loop-agent-core` 的 `LoopConfig` 钩子集（`GoalModeHooks` vs `DefaultHooks`）  
- **禁止：** 在 `routes.py` 或 `loop.py` 里用 scattered `if goal` 分叉；统一走 Config 切换

---

## 0.4 Preset 与审批（策略，非架构中心）

| Preset | 写盘 / Shell / Memory | 适用 |
|--------|------------------------|------|
| **YOLO** | 直接执行（或仅审计） | 默认推荐、本地可信工作区 |
| **Trusted** | 写操作需确认；读自动 | 日常结对 |
| **Strict** | 全门控 + hunk | 特殊场景 |

实现落点：`LoopConfig.beforeToolCall`（及 window 层等待 UI/CLI 决策）。**不得**在 tool 实现内部硬编码「必须审批」。

---

## 1. 目标分层（Loop 包模型）

### 1.1 四层 + 正交 UI

```text
loop-window          React + FastAPI + SQLite + CLI 适配
        ↑
loop-coding          fs / shell / edit / patch / skills / USER.md
        ↑
loop-agent-core      AgentLoop、LoopConfig、Trace/Turn、会话视图、Goal 策略
        ↑
loop-ai              Model Registry、OpenAI 兼容 Client、流式、错误归一
```

**正交：** Window UI 不反向定义 core 类型；core 不 import FastAPI/SQLAlchemy。

### 1.2 依赖规则（与 Pi M02 一致）

| 规则 | 说明 |
|------|------|
| **箭头只向上** | `loop-ai` 不知 core；core 不知 window |
| **允许跨层引用类型** | coding / core 可直接使用 `loop-ai` 的 `Message`、`Model` 等原子类型 |
| **禁止反向 import** | 底层不得 import 上层模块 |
| **功能可以厚** | 厚在 coding / window 与 **可插钩子**，不厚在 `loop.py` 单文件 |

### 1.3 现有代码映射（迁移前）

| 目标层 | 今天大致所在 | 首要剥离 |
|--------|--------------|----------|
| loop-ai | `services/provider.py`, `config.py` llm_* | 多档案 Registry；去掉「全局唯一网关」假设 |
| loop-agent-core | `agent/loop.py`, `goal.py`, `checkpoint.py`, `exploration.py` | 抽内核 + LoopConfig |
| loop-coding | `tools/*`, `services/patches.py`, `shell.py`, `memory.py`, `skills.py` | 审批等待回调化 |
| loop-window | `api/routes.py`, `models.py`, `src/components/*`, `cli/*` | Goal 按钮、Preset UI、Model 设置 |

**物理包名** 可渐进：`agent_window` → `loop_*` 与抽层同步，避免单独「全文替换 PR」。

---

## 2. Pi Agent 学习参考（M01–M10）

> 来源：[Pi Agent Book](https://dgzhuya.com/modules) M01–M10。  
> 格式：**Pi 意图 → Loop 缺口 → 借鉴动作 → 融合点**。

---

### 2.1 M01 · 开篇 — 哲学与边界

#### Pi 设计意图

| 要点 | 含义 |
|------|------|
| 三身份 | 好用工具 / 可学教材 / 可拆 SDK |
| 积木 ≠ 整车 | 缺省功能用扩展补，不焊进核心 |
| 减法 | 4 核心工具、极短系统提示；MCP/计划/子 Agent/审批弹窗默认不做 |
| 五根杠杆 | Extensions / Skills / Templates / Themes / Packages |
| 好用来自减 | TerminalBench 靠薄核心；加法是用户/扩展的选择 |
| YOLO 默认 | 审批 ~50 行扩展；安全边界靠容器而非弹窗疲劳 |
| 分层可独立用 | 可只用 ai；可用 core 自建产品 |

#### Loop 缺口

- 单体 `agent_window`：Window + loop + 门 + Goal 杂糅  
- Goal/检查点曾常开 → 违背「模式可选」  
- 路线图偏能力清单，缺架构脊柱文档（本文补位）  
- Hermes USER.md 未升格为「记忆杠杆」

#### 借鉴动作

1. 产品定位改为 **Loop Agent 外壳**，非 Chat 整车  
2. 宪章确立 **默认薄、模式显式打开**  
3. 路线图后续以 **架构阶段（A0–A4）** 为主轴，功能为挂件  

#### 融合点

| 保留 | 处理 |
|------|------|
| Foundation F1–F9 | 收编进 **Goal 模式钩子**，非删除 |
| 审批实现 | Preset 策略，非删除 |
| USER.md | **loop-coding 记忆子系统** + Preset 控制是否确认 |
| Window + CLI | 对标 `pi-tui` 正交层 |

---

### 2.2 M02 · 三层架构 — 骨骼

#### Pi 设计意图

| 包 | 一句话 |
|----|--------|
| pi-ai | 调模型：统一类型、流式、多供应商 |
| pi-agent-core | 跑环：状态、AgentLoop、事件、压缩/会话视图 |
| pi-coding-agent | 做产品：工具、CLI、扩展、会话持久化 |
| pi-tui | 只管显示，零 AI 依赖 |

**分层承诺：** 不是「只能调相邻层」，而是 **依赖方向单向** + **原子类型在一处定义**。

#### Loop 缺口

```text
routes / Settings / SQLite
     ↕ 双向
loop + goal + gates
     ↕
provider + tools + memory
```

无 import  lint；`loop.py` 直接 import patches、memory、provider。

#### 借鉴动作

1. 采用 §1 四层模型与依赖表  
2. **loop-ai** 第一刀：Model Registry（见 §3.4）  
3. 禁止 `loop-ai` import FastAPI；禁止 core import React  

#### 融合点

- 功能可比 Pi 厚：hunk diff、附件、Skills、审计 — **挂在正确层**  
- LiteLLM **降级为可选档案**（某条 Base URL 指向 LiteLLM 网关即可），不再是架构前提  

---

### 2.3 M03 · Agent Loop — 心脏

#### Pi 设计意图

**三种用法：** 直接调用 / Workflow / **Agent Loop**（模型驱动步骤）。

**Trace / Turn：**

```text
Trace（agent_start → agent_end）
├── Turn：一次 LLM + 该次触发的全部工具（turn_start → turn_end）
└── …
```

**停止规则：** 看 **有没有 tool call**（及工具 `terminate`），不是模型「说完成了」。

**内核 vs 叠加：**

```text
最简 Loop（~十几行概念）
  + getSteeringMessages      （内层：插队）
  + getFollowUpMessages      （外层：续命）
  + prepareNextTurn / shouldStopAfterTurn
  + beforeToolCall / afterToolCall
  + transformContext / convertToLlm
```

钩子为 **函数**，Loop 运行时拉取状态，与 Window 解耦。

#### Loop 缺口

| Pi | 今天 `run_agent_loop` |
|----|------------------------|
| 独立内核 | ~980 行单函数 |
| Turn 边界 | flat `for max_tool_iters` |
| followUp 外层环 | 无 |
| steering | 无 |
| convertToLlm | 裸 OpenAI dict |
| beforeToolCall | gate 逻辑焊在 loop 内 |
| agent/turn 事件 | 扁平 SSE；F6 无 turn 嵌套 |

#### 借鉴动作

1. **抽 `agent_loop` 内核**（1 LLM + 1 tool batch，直到无 tool_calls）  
2. 引入 **`LoopConfig`**（§3.2）  
3. **Goal 模式** = 换 Config 钩子集  
4. **Preset** = `beforeToolCall` 实现  
5. 补 **Trace/Turn** 事件树（接 F6）  
6. 预留 **steering / followUp** 接口（v1 UI 可后做）

#### 融合点

| 现有 | 收编 |
|------|------|
| `max_tool_iters` + 软着陆 | `shouldStopAfterTurn` 的一种 |
| F3 gate 续环/结束 | `after_tool_call` + Preset |
| F7 探索收敛 | `after_tool_batch`；**整批 tool 后再 inject user**（已验证序） |
| F4 slim | `after_tool_call` |
| 写盘诚实化 | `on_final_reply` |
| Hermes「薄 loop」注释 | 薄 **内核**，厚 **钩子** |

#### 目标 Loop 形状（概念代码）

```python
# loop-agent-core — 目标态（非当前实现）
async def agent_loop(
    context: AgentContext,
    config: LoopConfig,
    emit: EventSink,
    signal: CancelSignal,
) -> list[AgentMessage]:
    emit("agent_start")
    pending = await config.get_steering_messages()
    while True:
        while has_tool_work or pending:
            emit("turn_start")
            pending = await inject_pending(context, pending)
            msg = await stream_assistant(context, config, signal)
            if hard_stop(msg):
                break
            if tool_calls(msg):
                await execute_tools(context, config, tool_calls, emit)
            emit("turn_end")
            if await config.should_stop_after_turn(context):
                break
        follow = await config.get_follow_up_messages()
        if not follow:
            break
        pending = follow
    emit("agent_end")
```

---

### 2.4 M04 · 模型调用 — loop-ai 的心脏

> 源：[dgzhuya.com/modules/ch04-model-call](https://dgzhuya.com/modules/ch04-model-call)

#### Pi 设计意图

Agent Loop 只写一行 `streamSimple(model, context)`；背后是 **三层 AI 抽象**：

```text
① 统一入口 stream()     查表：model.api → 翻译器，派活
② 事件协议（12 种）     翻译器必须吐出同一套 AssistantMessageEvent
③ 翻译器（StreamFunction） 请求方言 ↔ 统一事件；错误不 throw，推 error 事件
```

| 维度 | Provider 差异 | Pi 统一法 |
|------|---------------|-----------|
| 消息格式 | content[] / parts / tool role | 内部统一 → 翻译器出站 |
| 流式 | 原始 SSE vs SDK chunk | 一律 12 事件（start/delta/end × text|thinking|toolcall + done/error） |
| 思考模式 | budget_tokens / reasoning_effort / … | `ThinkingLevel` 枚举 + 每 Model 的 map + clamp |
| 缓存 | cache_control / cachePoint | 语义 `cacheRetention: none|short|long` |

**接入新模型 = 写翻译器 + registerApiProvider + 配 Model 元数据**；Loop **一行不改**。

**协议 > 继承：** 不搞 `BaseProvider` 大基类；约定 `StreamFunction` 签名 + 事件协议即可。

#### Loop 缺口

| Pi | 今天 `provider.py` |
|----|---------------------|
| 多 API 翻译器注册表 | 单一 OpenAI 兼容 `AsyncOpenAI` + 全局 base_url/key |
| 12 事件流协议 | 非流式 `chat_complete` 为主；SSE 在 window 另拼 |
| Model 自带 api/thinkingMap | Settings 单组 URL + model 字符串 |
| 错误进流（永不抛断环） | 异常上抛 / humanize 字符串 |
| streamSimple 思考级别 | 无统一 ThinkingLevel |

**已有半成品：** OpenAI 兼容客户端、Settings 改 URL/Key、错误中文化 — 适合当 **第一版唯一翻译器**（`openai-completions`），再演进 Registry。

#### 借鉴动作

1. **loop-ai** 立事件协议（哪怕首版只实现 text + toolcall + done/error）  
2. **Model Registry**（§3.4）：档案 = base_url + key + model_id + `api`  
3. 首版只注册 **一个** OpenAI 兼容翻译器；国内站 / LiteLLM / vLLM 全走此方言  
4. core 只消费统一事件 / `chat` 结果，**禁止**直接 new OpenAI client  
5. 错误：翻译器层归一为 `error` 事件或结构化 `ProviderError`，环不因裸异常撕裂  

#### 融合点

| 决策 | 说明 |
|------|------|
| **不做 30 家原生 SDK** | Cursor 式多档案 + OpenAI 兼容覆盖主路径；原生 Anthropic/Google 后置 |
| **LiteLLM** | 可选档案的 Base URL，非架构中心 |
| **流式** | Window 已有 SSE；目标态由 loop-ai 吐统一事件，window 只映射 UI |
| **与 A2 对齐** | 重构阶段 A2 = Registry + 单翻译器 + 按会话选档案 |

---

### 2.5 M05 · 工具系统 — 手脚怎么被管住

> 源：[dgzhuya.com/modules/ch05-tools](https://dgzhuya.com/modules/ch05-tools)

#### Pi 设计意图

**三层工具类型（跟包分层对齐）：**

| 层 | 类型 | 职责 |
|----|------|------|
| pi-ai | `Tool` | 名片：name / description / parameters（给模型） |
| pi-agent-core | `AgentTool` | + execute / prepareArguments / executionMode / label |
| pi-coding-agent | `ToolDefinition` | + ctx / render / promptSnippet；`wrapToolDefinition` 注入上下文 |

**五步管道（永不打断环）：**

```text
prepareArguments → validate Schema → beforeToolCall
    → execute (+ onUpdate 进度)
    → afterToolCall
→ 始终产出 ToolResultMessage（失败则 isError: true）
```

| 钩子 | 作用 |
|------|------|
| `beforeToolCall` | 可 `{ block, reason }` — 审批 / 安全拦截的挂点 |
| `afterToolCall` | 改结果 / 脱敏 / 审计 / `{ terminate: true }` 早停 |
| `onUpdate` | 长任务进度；execute settle 后关闸，防孤儿回调 |

**并行：** 一批 tool call 中任一工具声明 `sequential` → 整批串行（一票否决）；并行时准备阶段仍顺序，仅 execute 并行，结果按调用序回灌。

**错误哲学：** 错误是给模型的反馈，不是给框架的终止信号；工具内部应抛**具体**错误文案。

#### Loop 缺口

| Pi | 今天 |
|----|------|
| 三层 Tool 类型 | 扁平 `ToolSpec`（name/desc/params/handler） |
| 五步管道 | `handle_function_call` 直调 handler；无 prepare/validate/before/after |
| beforeToolCall | 审批焊在 `loop.py`（AWAIT_* + wait_for_*） |
| afterToolCall | `slim_tool_result` 在 loop 内；无统一钩子 |
| onUpdate 进度 | 基本无（gate 有 SSE，工具本身黑盒） |
| 并行调度 | 整批顺序 for 循环 |
| 错误→tool 消息 | 有（handler 异常 → JSON error）但文案质量不一 |

#### 借鉴动作

1. core 立 **五步管道**（哪怕 validate 先做 JSON Schema 子集）  
2. **Preset / 审批 = `beforeToolCall`**，从 loop 内拔出  
3. **slim / gate 续环 hint / 审计 = `afterToolCall`**  
4. coding 层工具只实现 `execute`（+ 可选 prepareArguments）；不 await UI  
5. 保留「未知工具 / 异常 → tool 结果字符串」；强化具体错误文案纪律  

#### 融合点

| 现有 | 收编 |
|------|------|
| `propose_*` + AWAIT_* | 工具返回「需批准」意图；**beforeToolCall** 按 Preset 决定直通 / wait / block |
| YOLO / Trusted / Strict | beforeToolCall 三种策略，非三套 loop |
| F4 slim | afterToolCall 默认实现 |
| F3 Reject 结束 / timeout 续 1 次 | afterToolCall 返回 continue 语义或 terminate |
| hunk 部分应用 | coding 的 edit 能力；管道不感知 |
| 顺序执行 | 首版可保持顺序；并行作 A 阶段增强项 |

---

### 2.6 M06 · 消息系统 — 内富外严

> 源：[dgzhuya.com/modules/ch06-messages](https://dgzhuya.com/modules/ch06-messages)

#### Pi 设计意图

**两层消息：**

| 层 | 类型 | 读者 |
|----|------|------|
| 内层 | `AgentMessage` = 标准 Message ∪ 自定义 | UI / 持久化 / 环状态 |
| 外层 | `Message` = user \| assistant \| toolResult | **仅 LLM** |

自定义例：`BashExecution` / `CompactionSummary` / `BranchSummary` / `Custom` — 结构化字段给 UI；送模前经 **`convertToLlm`** 拍扁（通常变成 `user`）。

**送模前两步管道（职责分离）：**

```text
AgentMessage[]
  → transformContext   （同层：裁剪/压缩/注入，类型不变）
  → convertToLlm       （跨层：自定义 → 标准 Message[]）
  → loop-ai stream
```

**可见性：** `excludeFromContext=true` → UI 可见、LLM 隐身（数据不删）。

**核心洞察：** 不为 LLM 提前拍扁存储；翻译是最后一刻、有损、单向。Provider 方言翻译在 **loop-ai**（M04），与 convertToLlm **正交**。

#### Loop 缺口

| Pi | 今天 |
|----|------|
| AgentMessage | 无；全程 OpenAI `dict`（role/content/tool_calls） |
| convertToLlm | 无；Goal/检查点/探索收敛直接 `working.append(user)` |
| transformContext | 压缩在 routes 拼好再进 loop；环内无钩子 |
| excludeFromContext | 无（附件/审计/TurnEvent 另库，未进统一消息模型） |
| 自定义消息 | Goal/checkpoint 伪装成 user → UI 难区分、易乱序（F7） |
| DB `Message` | 线性 role+content+sequence；无 parent_id / 类型扩展 |

#### 借鉴动作

1. core 引入 **AgentMessage**（Python：TypedDict / dataclass 联合 + role 判别）  
2. **`convert_to_llm` 为 LoopConfig 必填钩子**；Goal/检查点/收敛改为自定义 role，再翻译  
3. **`transform_context` 单独钩子**（压缩、Goal 注入时机）  
4. TurnEvent / gate 卡片：优先「自定义消息 + UI 渲染」，少伪装 user  
5. `exclude_from_context` 留给敏感 shell / 仅展示附件元数据  

#### 融合点

| 现有 | 收编为 AgentMessage role（示意） |
|------|----------------------------------|
| Turn Goal 注入 | `goal` / 或 transform 注入，不永久污染历史为假 user |
| progress_checkpoint | `checkpoint` → convert 成短 user 提示 |
| 探索收敛 | `exploration_converge` |
| Compaction 摘要 | `compaction_summary`（接 M09） |
| Branch 摘要 | `branch_summary`（接 M10） |
| USER.md / 附件 | coding/window 自定义；convert 时决定是否入模 |
| OpenAI tool 序 | convert 后仍须遵守 tool_calls ↔ tool 成对（F7 纪律不变） |

**与 A4 对齐：** Session Tree + convert_to_llm 同阶段落地最省事；可先在 A0/A1 引入最小 AgentMessage（标准三种 + goal/checkpoint），A4 再扩树相关类型。

---

### 2.7 M07 · 事件驱动 — 神经系统（双管道）

> 源：[dgzhuya.com/modules/ch07-event-driven](https://dgzhuya.com/modules/ch07-event-driven)

#### Pi 设计意图

**一句话：** 两套并行监听，共享事件源；分水岭是 **Agent 等不等你**。

| 管道 | API | Agent 是否等待 | 能力 | 典型用途 |
|------|-----|----------------|------|----------|
| **A** | `session.subscribe` | **不等**；返回值丢弃 | 只读观察 | UI/SSE、日志、落库、统计 |
| **B** | 扩展 `pi.on` | **等**；读返回值 | 可拦截/改写 | 审批、改上下文、换系统提示 |

**内核事件源（10 种，4 层嵌套）：**

```text
agent_start/end
  turn_start/end
    message_start/update/end
    tool_execution_start/update/end
```

**管道 B 独占决策点（A 收不到）：** `tool_call`（执行前安检）/ `tool_result` / `input` / `before_agent_start` / `context`  
注意：`tool_call` ≠ `tool_execution_start`（后者已开跑，拦不住）。

判断口诀：要不要改 Agent 行为？要 → B；不要 → A。

#### Loop 缺口

| Pi | 今天 |
|----|------|
| 管道 A（不等） | `run_agent_loop` **yield 扁平 dict** → routes 转 SSE；无 subscribe 总线 |
| 管道 B（等） | **不存在**；审批/Goal 硬焊在 loop（伪 B） |
| 10 种嵌套事件 | 无 agent/turn 边界；F6 TurnEvent 是扁平子集 |
| tool_call vs tool_execution_start | 混在 loop 的 await gate 里 |
| 扩展点 | 无；加策略 = 改 loop.py |

**半成品：** SSE 转发 ≈ 管道 A 的消费端；`beforeToolCall`（M05）≈ 管道 B 的 `tool_call`；F6 落库应挂在 A，勿阻塞环。

#### 借鉴动作

1. core **EventSink**：环内 emit 嵌套生命周期事件（先对齐 agent/turn/tool）  
2. **管道 A**：window 订阅 → SSE / TurnEvent 落库 / audit（fire-and-forget）  
3. **管道 B**：即 LoopConfig 钩子（before/after_tool_call、transform_context）— Agent **await**  
4. 禁止再在 loop 里直接 `wait_for_decision`；B 返回 block/wait，window 实现等待 UI  
5. 整轮收尾信号对齐 `agent_end` / settled（勿用多次 message_end 当 done）  

#### 融合点

| 现有 | 归属 |
|------|------|
| SSE `token` / `tool_*` / `done` | 管道 A 映射 |
| F6 TurnEvent 落库 | 管道 A（不 await I/O） |
| Preset / 审批 | 管道 B = beforeToolCall |
| Goal 检查点注入 | 管道 B（after_tool_batch / transform）或自定义消息 |
| CLI 同 Runtime | CLI 也订 A；approve 走 B 决策回调 |
| 扩展系统（远期） | 管道 B 可演进为插件；首版 Config 钩子够用 |

**与 A3 对齐：** Trace/Turn 事件树 + steering 口 = 本章落地；A1 先把伪 B（gate）收成真钩子。

---

### 2.8 M08 · 上下文工程 — 有限窗口装无限对话

> 源：[dgzhuya.com/modules/ch08-context-engineering](https://dgzhuya.com/modules/ch08-context-engineering)

#### Pi 设计意图

**四道防线，两层：**

```text
输入侧（每次工具 / 每轮 prompt）
  ① 工具输出截断   行数+字节双限；read 保头 / bash 保尾；逃生通道（full 落盘）
  ② 系统提示组装   AGENTS.md/CLAUDE.md 向上递归 + Skills **拉模式**（清单进 prompt，全文按需 read）

历史侧（长对话 / 分叉）
  ③ Compaction     阈值触发 → 结构化摘要（详 M09）
  ④ 分支摘要       换叶时对被弃分支做摘要（接 M10）
```

| # | 问题 | 频率 |
|---|------|------|
| ① | 单次工具太大 | 每次工具 |
| ② | 项目规范进上下文 | 每轮 prompt |
| ③ | 线性历史超窗 | 阈值 |
| ④ | 分叉后旧探索不丢 | 切换分支 |

**设计模式：** 截断要诚实（告诉模型被截 + full 路径）；Skills 用工具做按需加载，不推全文。

#### Loop 缺口

| Pi | 今天 |
|----|------|
| ① 统一 truncateHead/Tail | `observation.slim_tool_result` + 大输出 `data_path` — **有雏形，未成统一 truncate 契约** |
| ② 递归 AGENTS.md + Skills 拉模式 | AGENTS.md 有；Skills 偏 **推/激活列表**，非清单+按需 read |
| ③ Compaction | `compress.py` MVP + preserve_goal；非 6-section / CompactionEntry |
| ④ 分支摘要 | 无树 → 无 |
| 挂点 | transformContext / afterToolCall | 压缩在 routes；slim 在 loop |

#### 借鉴动作

1. coding：**统一 truncate 策略**（头/尾 + 行/字节 + full 落盘提示）挂 after_tool_call  
2. Skills：**拉模式** — system 只放清单；模型用 read/skill 工具取全文  
3. 压缩进 **transform_context**（环内可触发），摘要为 AgentMessage（M06）  
4. 分支摘要等 Session Tree（M10）一并做  
5. 系统提示组装属 **coding/window**，core 只吃拼好的 system + transform  

#### 融合点

| 现有 | 收编 |
|------|------|
| F4 slim + data_path | = ① 的 Loop 版；对齐 head/tail 语义 |
| preserve_goal 压缩 | Goal 模式 ON 时进 transform；摘要消息不毁 Goal |
| USER.md（Hermes） | 长期记忆块进 system；与 AGENTS 递归并列，勿塞满每轮 |
| active_skills | 改为「可用清单」；全文不默认注入 |
| auto_compress 设置 | 保留开关；算法升格见 M09 |

---

### 2.9 M09 · 上下文压缩 — Compaction 算法

> 源：[dgzhuya.com/modules/ch09-compaction](https://dgzhuya.com/modules/ch09-compaction)

#### Pi 设计意图

**时序：** 压缩发生在 **两轮之间**（`agent_end` 后检查），不是 Turn 中途。

**流水线：**

```text
shouldCompact(tokens > window - reserve)
  → findCutPoint（从后往前攒 keepRecentTokens；切点只能是 user/assistant，禁 toolResult）
  → 序列化 + LLM → 6-section 结构化摘要（可增量 previousSummary）
  → 可选 turnPrefix（切在 assistant 时补半 Turn）
  → 写 CompactionEntry（firstKeptEntryId + files 跟踪）
  → 下次 buildSessionContext：摘要消息 + 保留段
```

**6 section：** Goal / Constraints / Progress / Key Decisions / Next Steps / Critical Context  
外加 `<read-files>` / `<modified-files>` 跨次累积。

**双触发：** 预防性（阈值）+ 应急性（API overflow 后压缩再试）。

**关键：** 压缩是 **树/路径上的视图节点**，不是删盘毁证据；摘要经 convertToLlm 变 user。

#### Loop 缺口

| Pi | 今天 `compress.py` |
|----|---------------------|
| shouldCompact + reserve | `tokens > context_limit`；无 reserve 概念 |
| findCutPoint / Turn 完整 | 粗暴：留最近 4 条，older 拼 blob |
| 6-section 摘要 | 自由文本 summarize 或截断 |
| 增量 previousSummary | 无 |
| 文件跟踪 | 无 |
| CompactionEntry / 树 | 改 messages 数组；无 firstKeptEntryId |
| agent_end 后触发 | routes 进 loop **前**压缩 |
| turnPrefix | 无 |
| overflow 应急 | 无自动重试压缩 |

**已有优点：** `preserve_goal` 钉住 Goal；chars/4 估算与 Pi 同思路；auto_compress 开关。

#### 借鉴动作

1. 升格算法：有效切点 + keepRecent + 6-section prompt（Goal 模式可强制 Goal section）  
2. 摘要落为 **AgentMessage `compaction_summary`**，经 convert_to_llm  
3. 触发挂 **transform_context / agent_end 后**（管道 A 发 compaction_start/end）  
4. 中文场景：chars/4 低估 → 调估算或更早阈值  
5. 完整 CompactionEntry 等 Session Tree（M10）；线性期可先「摘要消息 + 截断数组」  

#### 融合点

| 现有 | 收编 |
|------|------|
| preserve_goal | 映射 6-section 的 Goal；Goal OFF 时 section 可弱化 |
| auto_compress / context_limit | 保留；加 reserveTokens |
| F4 data_path | 压缩前工具结果已瘦 → 摘要质量↑ |
| USER.md | 不进 Compaction（跨会话记忆另轨） |

---

### 2.10 M10 · 会话管理 — Session Tree

> 源：[dgzhuya.com/modules/ch10-session](https://dgzhuya.com/modules/ch10-session)

#### Pi 设计意图

**两个正交子问题：**

| 维度 | 一般 | Pi |
|------|------|-----|
| 存哪里 | MySQL 等 | JSONL（`SessionStorage` 可换） |
| 长什么样 | 线性数组 | **Session Tree**（append-only） |

**铁律：** 认父不认子（只有 `parentId`）；回退/分叉 = **移动 `leafId`**，旧分支永不删。

**操作：** `append` · `branch(id)` · `branchWithSummary()`（对被弃路径写 BranchSummaryEntry）。

**入口：** `buildSessionContext(leaf)` = leaf→root 走路径 → reverse → 类型分派；Compaction 用 `firstKeptEntryId` 跳过而不删盘。

**Entry 组：** 进 LLM（Message / Compaction / BranchSummary）· 影响参数（ModelChange）· 元数据（Label / SessionInfo）。

#### Loop 缺口

| Pi | 今天 |
|----|------|
| Session Tree + leafId | SQLite 线性 `messages.sequence` |
| regenerate = branch | 截断/重写线性历史；旁支丢失 |
| CompactionEntry on tree | compress 改数组 |
| buildSessionContext | routes 按 sequence 拼 `chat_messages` |
| ModelChange 节点 | 每轮请求带 model 字符串 |

#### 借鉴动作

1. MVP：`messages.parent_id` + session `leaf_id`；regenerate = branch(user) + append  
2. `build_context(leaf)` 替代全表 sequence  
3. CompactionEntry / BranchSummary 挂同一棵树（M09/M08④）  
4. UI 树导航可后置；介质可继续 SQLite（结构 ⊥ 介质）  
5. 归属：core 定义 Entry/leaf；window 持久化  

#### 融合点

| 现有 | 收编 |
|------|------|
| regenerate UX | 产品意图已有；数据结构补树即「真分叉」 |
| Goal 模式 | Goal 可挂路径/回合元数据；切分支不丢 Goal 记录 |
| F6 TurnEvent | 可挂在当前路径节点上；旁支仍可回放 |
| A4 阶段 | Session Tree + convert_to_llm + CompactionEntry 同阶段最省 |

---

### 2.11 十章收束 → Loop 落地顺序

| 想学的 | 主要章节 | Loop 动作 |
|--------|----------|-----------|
| 分层拆包 | M01–M02 | §1 四层 + 依赖单向 |
| 减法 / 模式可选 | M01 | Goal / Preset 默认关或松 |
| 薄环 + 钩子 | M03 / M05 / M07 | 内核 + LoopConfig；A=观察 B=干预 |
| 消息内富外严 | M06 | AgentMessage + convert_to_llm |
| 模型多档案 | M04 | loop-ai Registry（OpenAI 兼容先行） |
| 上下文四防线 | M08–M09 | truncate / Skills 拉 / Compaction 升格 |
| 树状会话 | M10 | parent_id + leaf + build_context |
| Hermes 记忆 | （融合） | §3.5；USER.md ∈ coding；有界+冻结快照+Preset |

**推荐实现序（与 §5 对齐）：** A0 立层 → A1 管线/Preset/Goal 开关 → A2 Registry → A3 双管道事件 → A4 树 + convert + CompactionEntry。

---

## 3. 核心原语（M01–M10 合成）

### 3.1 LoopConfig 钩子

| 钩子 | 职责 | 默认 | Goal 模式 |
|------|------|------|-----------|
| `convert_to_llm` | AgentMessage → LLM 消息 | 必填；标准三种透传 | + goal/checkpoint/converge 翻译 |
| `transform_context` | 送模前同层变换 | 可选压缩 | 保留 Goal；裁剪旧消息 |
| `before_tool_call` | Preset / 审批 | YOLO 直通 | 同左 |
| `after_tool_call` | slim、gate 结果、错误归一 | slim | + 续环 hint |
| `after_tool_batch` | 批后 inject | 无 | 检查点、探索收敛 |
| `on_turn_start` | 每 Turn 开头 | 无 | 注入 Goal |
| `should_stop_after_turn` | 触顶/压缩 | max_iters | + Goal 软着陆 |
| `get_steering_messages` | 插队 | `[]` | 同左 |
| `get_follow_up_messages` | 外层续命 | `[]` | 同左 |
| `on_final_reply` | 最终文本 | 诚实化 | + Goal 文案 |

**工厂：**

```text
LoopConfig.default()           # Goal OFF + YOLO
LoopConfig.with_goal_mode(...) # Goal ON
LoopConfig.with_preset(...)    # 叠加 Strict/Trusted
```

### 3.2 Trace / Turn 事件与双管道

```text
管道 B（await 钩子）          管道 A（不等，subscribe）
before_tool_call / …    →    EventSink.emit → SSE / TurnEvent / audit
transform_context       →
```

**内核嵌套（目标态）：**

```text
agent_start
  turn_start
    message_*, tool_execution_*
  turn_end
agent_end
```

F6 `TurnEvent` = turn 内子事件落库（管道 A）；SSE 与 audit 对齐此树。

**纪律：** 不得在 assistant `tool_calls` 与未完成的 `tool` 消息之间插入 `user`（API 400；F7）。  
**纪律：** 管道 A 监听器异步错误必须自捕；落库勿阻塞环。  
**纪律：** 审批/拦截只走管道 B；勿在 A 里假扮拦截。

### 3.3 模式矩阵

| | Goal OFF | Goal ON |
|--|----------|---------|
| YOLO | **默认推荐** | 任务型结对 |
| Trusted | 日常写代码 | 长任务 + 对照目标 |
| Strict | 审计场景 | 高风险变更 |

### 3.4 loop-ai：Model Registry + 调用协议（M02 + M04）

**目标：** Settings 中 **多条** 供应商/模型档案（Cursor 式），非全局唯一 LiteLLM 网关；调用经 **统一入口 +（可扩展）翻译器**。

| 字段 | 说明 |
|------|------|
| `id` | 档案 id，会话/顶栏选择 |
| `label` | 展示名 |
| `base_url` | OpenAI 兼容 `/v1`（或其它方言端点） |
| `api_key` | 本地加密存储，UI 不回显 |
| `model_id` | 请求体 model 字段 |
| `api` | 首版固定 `openai-completions`；日后可扩 `anthropic-messages` 等 |
| `context_window` / `thinking_map` | 可选元数据（M04 ThinkingLevel 预留） |

**调用栈（目标态）：**

```text
agent-core: stream_assistant(model_handle, context)
    → loop-ai.stream(model) / stream_simple(...)
        → resolve_translator(model.api)
        → translator: 统一消息 → 私有请求 → 统一事件流
```

**首版事件子集（够 Loop 用）：** `text_delta` · `toolcall_start/delta/end` · `done` · `error`  
（thinking_* 等完整 12 事件可后补。）

**分层：** Registry + Client + 翻译器 ∈ `loop-ai`；Settings 表单 ∈ `loop-window`；core 只持 `ModelHandle`，不碰 Key、不拼 HTTP。

**LiteLLM：** 某条档案的 Base URL 即可，非必须组件。

---

### 3.5 可进化记忆（Hermes 参考 · loop-coding）

> **外部详解（只读参考，非本仓文件）：**  
> `\\wsl.localhost\openEuler-24.03\home\caapap\src\hermes-agent\docs\hermes-memory-system.md`  
> （本机路径：`/home/caapap/src/hermes-agent/docs/hermes-memory-system.md`）

Hermes 的主张：**记忆 ≠ 无限堆历史进 system prompt**；而是 **分层、有界、主要由 Agent 主动维护**。Loop 采纳其哲学，按本仓分层落地——**不整仓移植**。

#### 设计主张（可持续）

| 要 | 不要 |
|----|------|
| 跨会话记住偏好/环境 | 每轮塞满历史（贵、炸缓存、噪声） |
| 随使用「更懂你」 | 无限增长、过期事实污染 |
| Agent 自管记忆 | 静默截断用户内容 / 乱写 |

**可持续靠：** 硬字符上限 + **冻结快照（保 prefix cache）** + 明确分工 +（可选）后台回顾 + 写入跟 **Preset**——不是无监督堆积。

#### 四层分工（Loop 目标态）

```text
永远可见（会话开始冻结进 system / volatile）
  USER.md     —— 用户画像/偏好（有界）
  MEMORY.md   —— 环境/项目/教训（有界；可后补，先 USER）
  Skills 清单 —— 程序记忆目录（拉模式，正文按需）

每轮动态（可选，挂 user sidecar，不改 system）
  Provider.prefetch → <memory-context>…（外部语义召回，后置）

按需工具
  propose_memory / memory add|replace|remove
  session_search（全量 transcript 检索，后置）
  skill_view / read skill

自动落库但不 forever-inject
  会话 DB / audit / TurnEvent
```

| 存什么 | 进 forever-prompt？ | 谁写 |
|--------|---------------------|------|
| 长期事实/偏好 | 是（冻结、有上限） | Agent 工具 + Preset |
| 深度语义召回 | 否（每轮 prefetch） | 外部 Provider（后置） |
| 完整对话 | 否（工具检索） | 自动记 session |
| 「怎么做」 | 索引是；正文按需 | Skills |

**分工纪律（写入引导）：** 偏好/环境 → memory；短期进度/PR 号 → session_search（或 Goal 检查点）；流程 → skills。勿把祈使句塞进 USER（写成「User prefers…」）。

#### 双态模型（缓存友好 · 必学）

1. **会话开始** `load` → **冻结快照** → 注入 system  
2. **会话中途** 工具写入 → **立刻落盘 + live 状态**  
3. **本会话 system 不刷新** → prefix cache 稳定  
4. **下次会话**（或压缩 rebuild）才换新快照  

体感：「本轮工具已确认记住」；「下一会话起」才稳进身份侧上下文。

#### 有界增长

- 硬上限（Hermes 默认量级：MEMORY ~2200 / USER ~1375 chars，Loop 可自配）  
- **满了不静默截断** → 错误 + 要求同轮 replace/remove 再 add  
- 容量可见（可选：prompt 内显示占用比）  
- 写入跟 Preset：YOLO 可直写；Trusted/Strict 走确认  

#### 与本仓分层

| 落点 | 层 |
|------|-----|
| USER.md / MEMORY.md 读写、上限、冻结快照 | **loop-coding** |
| `propose_memory` / memory 工具 | coding；**beforeToolCall** = Preset |
| 注入 system 的时机与 snapshot | coding 组装；window/routes 调加载 |
| 不进 Compaction 正文毁记忆 | 记忆另轨（M09 已定） |
| session_search / 外部 Provider | **后置**；A0–A4 不阻塞 |

#### Loop 现状（诚实）

已有：`USER.md` + `MEMORY.md` + `propose_memory`（M0 整文件 + **M1** 条目 add/replace/remove / `operations`）+ 审批门 + Settings；**A1d** 硬字符上限 + 双轨冻结快照。  
缺口：无后台回顾、无 session_search、外部 Provider 仍后置。

**升格节奏：** A1 与 Preset 一起把写入策略理顺 + 字符上限（✅ A1d）；MEMORY.md M0 + 条目工具 M1 已完成；Provider / session_search 仍后置。

---

## 4. 现状 vs 目标（诚实快照）

> **勾选细节与收编表以 [`foundation-status.md`](foundation-status.md) 为准**；下表是宪章视角的摘要（2026-09-02 与 Living 对齐）。

| 能力 | 现状 | 目标层 | 迁移状态 |
|------|------|--------|----------|
| 机械 tool 环 | ✅ `run_agent_loop` + `_run_one_turn` | core 内核 | ✅ A0；物理包名仍 `agent_window` |
| Goal / 检查点 / F7 | ✅ `GoalModeHooks`（Goal OFF 可关） | core GoalModeHooks | ✅ 已收编 |
| F3 失败续环 | ✅ `agent/gate_policy.resolve_gate_outcome` | after_tool_call + Preset | ✅ 已收编（loop 委托） |
| 审批门 | ✅ prepare→before settle→apply；`before_tool_call` allow|wait|block | beforeToolCall + apply | ✅ Gate 深拆 Step1–3 |
| 工具五步管道 | ✅ prepare / before / settle|execute / after（gate 跳过二次 execute） | core 管线 | ✅ Step3；Schema validate 可后置 |
| 事件双管道 | ✅ EventSink + lifecycle；扁平 SSE 保留；gate≈Pipe B | A=观察 / B=钩子 | ✅ A3（M07） |
| TurnEvent 落库 | ✅ F6 + lifecycle 轻量；leaf 路径 | 管道 A 子事件 | ◐ 嵌套 Entry / 时间线 UI 可后置 |
| 工具输出截断 / slim | ✅ `ObservationResult` + head/tail + `file:` spill | after_tool_call 统一 truncate | ✅ F4 契约 Step1–3（与 F6 对齐） |
| Skills 拉模式 | ✅ system catalog（id/name/desc）；全文按需 read_file | system 清单 + 按需读 | ✅ A4（轻） |
| Compaction | ✅ 切点 + reserve + 6-section + compaction_summary + preserve_goal | transform_context + AgentMessage | ✅ A4（M09 MVP）；完整 CompactionEntry 可后置 |
| Session Tree | ✅ parent_id + leaf_id + build_path；UI 按 leaf 配对 | core + storage | ✅ A4 MVP；**切支导航 UI 后置** |
| 分支摘要 | ❌ | 弃枝 LLM 摘要（M10） | 未做（依赖切支 UI） |
| Model Registry | ✅ 多档案 + Settings；全局 active | loop-ai Registry | ✅ A2；会话级 profile 可后置 |
| steering / followUp | ✅ steer 队列+API；**产品 UI 已撤回**；followUp 未做 | core 接口 | ◐ A3（UI 停用；followUp 后置） |
| AgentMessage 层 | ✅ `core/messages.py` | core（M06） | ✅ A4 |
| convert_to_llm | ✅ `default_convert_to_llm`；LoopConfig 默认 | LoopConfig 必填有默认 | ✅ A4 |
| 可进化记忆 | ✅ USER+MEMORY + 双轨冻结 + 条目 ops（M0+M1） | coding §3.5 | ◐ Provider / session_search 后置 |
| F8 Goal 留痕 | ✅ 变更审计 + pin | Goal 模式留痕 | ✅ `goal_hooks` + `pinned_goal` |
| 软着陆 | ✅ `soft_land` SSE + 分节汇报 + UI「继续」 | 触顶诚实收口 | ✅（穿插交付） |

---

## 5. 重构阶段（绞杀式，禁止大爆炸）

| 阶段 | 主题 | 交付 | 行为要求 | 状态 |
|------|------|------|----------|------|
| **A0** | 立层 + LoopConfig 空壳 | 目录/import 规则；抽 `_run_one_turn` | pytest 全绿 | ✅ |
| **A1** | 五步工具管线 + Preset + Goal 开关 | before/afterToolCall；YOLO/Trusted；GoalModeHooks | 审批离开 loop 内联；Goal OFF 默认 | ✅ |
| **A2** | loop-ai Registry | 多档案 Model；按会话选模型 | Settings UI | ✅ |
| **A3** | 双管道事件 + steering 口 | EventSink；SSE/TurnEvent 订 A；steer 队列 | F6 对齐嵌套树 | ✅ |
| **A4** | 会话视图 + M06+ | parent_id/leaf；convert_to_llm | regenerate=branch | ✅ |

**原则：** 每阶段 **可运行 + 可测**；旧路径绞杀完成后删除旁路，不并行维护两套 loop。  
**A0–A4 完成后：** 不再开并行「A5 大阶段」；开新工按 Living 收编债 / 产品 backlog（切支 UI、Mem Provider、Gate 深拆等）。

---

## 6. Foundation 收编说明

Foundation（F1–F9）**不作废**，从「常开旁路」改为 **Goal 模式插件**：

| 项 | Goal OFF | Goal ON |
|----|----------|---------|
| F1 Turn Goal | 不注入 | 注入 + SSE |
| F2 检查点 | 不跑 | 跑 |
| F3 失败续环 | 简化（Preset 相关） | 完整 |
| F4 观察瘦身 | ✅ | ✅ |
| F5 环境默认 | ✅ | ✅ |
| F6 中间态 | ✅ | ✅ + turn 边界 |
| F7 探索收敛 | 不跑 | 跑 |
| F8 Goal 留痕 | 不适用 | ✅ |
| F9 狗粮 | Goal ON 剧本 | 可保留 OFF 轻量剧本 |

---

## 7. 刻意不照搬 Pi 的部分

| Pi | Loop 选择 |
|----|-----------|
| 极短系统提示 / 仅 4 工具 | 保留现有工具面与 Skills；通过 Preset 收面 |
| 默认 YOLO 无审计 | 默认 YOLO 可审计（事件落库），不强制弹窗 |
| JSONL 唯一存储 | SQLite + 可选导出；树用 parent_id |
| 整仓 TypeScript monorepo | Python backend 内逻辑分包先行的同构分层 |
| 放弃 Goal 质量环 | Goal 模式作为 **可选厚模式** |

---

## 8. 文档维护

| 时机 | 更新 |
|------|------|
| 分层/原语/产品原则变更 | **本文** |
| A0–A4 阶段定义变更 | `agent-window-roadmap.md` |
| 阶段进度 / 收编勾选 | `foundation-status.md` |
| Pi 实战篇 / 新决策 | 追加 §2.x 或改 §0–§1 |

**不改：** 本文不写具体排期周数（见路线图 §8）。

**废止权威：** 旧「死抱目标默认脊柱」叙事、F1–F9 占比裁判、冻结的 foundation-* 派生考古文 — 冲突时以本文为准。

**Pi 主线：** M01–M10 已吸收进 §2；附录 A 关闭。

---

## 附录 A.（已关闭）

M01–M10 主线已写入 §2.1–§2.11。后续若有实战篇（P01+）再开新节。


---

## 附录 B. 相关文档索引

| 文档 | 用途 | 权威 |
|------|------|------|
| **本文** `architecture-charter.md` | 架构与新建设 | **唯一真源** |
| [`agent-window-roadmap.md`](agent-window-roadmap.md) | A0–A4 交付与验收 | 服从宪章 |
| [`foundation-status.md`](foundation-status.md) | Living 进度 / 收编表 | 服从宪章 |
| [`archive/foundation-f4-f6-plan.md`](archive/foundation-f4-f6-plan.md) | 旧 F4/F6 方案 | 冻结考古 |
| [`research/pi-agent-ch06-messages.md`](research/pi-agent-ch06-messages.md) | M06 本地笔记 | 参考 |
| [`research/pi-agent-ch08-context-engineering.md`](research/pi-agent-ch08-context-engineering.md) | M08 本地笔记 | 参考 |
| [`layer-boundaries.md`](layer-boundaries.md) | 逻辑层与 import 规则（A0） | 服从宪章 §1 |
| [`README.md`](README.md) | docs 地图 / 归位索引 | 服从 AGENTS 分层 |
| Hermes `hermes-memory-system.md` | 可进化记忆详解 | 外部只读参考（见 §3.5） |
