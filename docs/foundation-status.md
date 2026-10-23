# Loop Agent 迁移与进度（Living）

> **架构真源：** [`architecture-charter.md`](architecture-charter.md)  
> **交付阶段定义：** [`agent-window-roadmap.md`](agent-window-roadmap.md)  
> **本文职责：** 追踪 A0–A4 进度、旧 Foundation 收编状态、验收勾选。  
> 开新工以宪章 + 路线图 §4 为准；**不再**用 F1–F9 占比当主裁判。

| 字段 | 值 |
|------|-----|
| **最后更新** | 2026-10-23 |
| **产品名** | Loop Agent |
| **当前焦点** | `loop uninstall` 只删程序文件；已安装的 `loop` 不能再当仓库来 install |
| **架构阶段** | **A0–A4 完成** |

---

## 如何维护

在以下时机更新本文（可与 `CHANGELOG.md` `[Unreleased]` 同批）：

1. 启动 / 完成 **A0–A4** 任一条交付  
2. 旧 F 项完成 **收编**（从 loop 旁路迁入钩子/层）或 Goal OFF 行为变更  
3. §3 验收勾选变化  

**不要**再维护「Foundation 整体 % / 中间路线 68%」类数字（已废止）。  
**不要**改冻结的 [`archive/foundation-f4-f6-plan.md`](archive/foundation-f4-f6-plan.md) 当进度源。

### 更新记录

| 日期 | 变更摘要 |
|------|----------|
| 2026-10-23 | **卸载：** `loop uninstall` 删除安装目录、命令行入口和桌面启动项，留下用户数据和工作区 |
| 2026-10-23 | **桌面启动项：** `loop install` 写入 `~/.local/share/applications/loop-agent.desktop`，Exec 是 `loop shell` 的绝对路径 |
| 2026-10-23 | **PATH 入口：** `loop install` 写入 `~/.local/bin/loop`，解释器是安装目录里的 Python |
| 2026-10-23 | **安装目录的后端：** `loop install` 拷入虚拟环境并换成实体包。`loop shell` 用这份环境开窗，工作目录是安装目录 |
| 2026-10-23 | **安装目录：** `~/.local/lib/loop-agent`。`loop install` 拷入界面和窗口程序；`loop shell` 用这份目录开窗，页面由后端托管 |
| 2026-10-23 | **首次向导：** 工作区未绑定时填模型，再选或新建文件夹。新建不绑定；桌面进程不读 `backend/.env` |
| 2026-10-23 | **桌面壳：** `loop shell` 开窗拉起 8765/8766，关窗停进程。数据目录是用户目录，不拷工作区 |
| 2026-10-23 | **运行时三个目录：** 宪章 §1.4。未设 `APP_DATA_DIR` 时数据进 `~/.local/share/loop-agent`，不绑定工作区。开发 `.env` 仍指向 `backend/data` |
| 2026-10-23 | **会话级模型档案：** §4 六步手测通过，路线图 §4.3 勾选。core 经 Handle 仍后置 |
| 2026-10-20 | **会话级模型档案：** 预置目录 + 会话两列 + 按档案 client。手测未做，路线图 §4.3 未勾 |
| 2026-09-29 | **Files 文档编辑：** .docx 预览/源码/保存；MD 工具栏保存与自动保存；Office 范围调研（Excel/PPT 暂缓） |
| 2026-09-16 | **切会话不断流 P2：** 切走保活 SSE；按会话 Map 归约；切回即时续 UI（少靠 poll） |
| 2026-09-16 | **切会话不断流 P1：** SSE abort 不再 cancel；侧栏 busy 用标题 text-shimmer；完成后未读 |
| 2026-09-12 | **Files MVP：** coding `read_text_file`/`write_text_file` + `/api/workspace/files/*` + FilesPanel/SurfaceHost；research 两篇（files / app packaging）；Agent read_file/门控未改 |
| 2026-09-11 | **CoT 密度：** 短 Thought 按序嵌 Explored/Edited；结束收 Worked for；信息不丢 |
| 2026-09-09 | **清 ToolTimeline 死代码：** 删组件 + retryToolStep 接线 + `getSessionBlob`；保留 toolTrace/blobs |
| 2026-09-09 | **产品 Backlog：** 多会话后台续跑（切会话不取消上一轮）；现状仍为 abort+cancel |
| 2026-09-09 | **Compaction Progress：** 无工具窗口写「未见工具结果」；禁虚假「尚未开始」/无工具「等待」；coerce + 测试 |
| 2026-09-09 | **狗粮收口：** §7.1–7.3 填通过；全表无阻断；Compaction handoff + 小节分工已落地；焦点转「可发版前核对 / 小清理」 |
| 2026-09-09 | **间距/CoT：** Goal·Worked for 统一 mb-3；去 CoT 开关（有 reasoning 才显示）；记忆 DUPLICATE 可读化 |
| 2026-09-09 | **狗粮修：** Goal 间距；Reasoning OFF 抑 Thought；memory 门不再误报未验证写盘；附件保存→edit 意图；§7 压缩剧本 |
| 2026-09-08 | **CoT 修复：** Apply/Reject→activity；done merge 保 Edited/Ran；hydrate `gate`/`full_ref`；diff/shell 持久化类型 |
| 2026-09-08 | **狗粮全表：** [`dogfood/cot-s1-product-checklist.md`](dogfood/cot-s1-product-checklist.md)；焦点改为按表验收再定 S2 |
| 2026-09-04 | **CoT S1：** reasoning 解析 + `thought` SSE + 档案 Reasoning 开关；Activity Thought |
| 2026-09-04 | **CoT S0c：** Activity Edited/Ran → Diff/Shell 卡片定位高亮 |
| 2026-09-04 | **CoT S0b：** TurnActivity UI；去主界面 ToolTimeline/检查点；SSE+hydrate activity |
| 2026-09-04 | **CoT S0a：** `agent/turn_activity.py` + TS `turnActivity.ts`；pytest +14；下一刀 S0b UI |
| 2026-09-04 | **CoT 调研收口：** [`research/cursor-cot-activity-timeline.md`](research/cursor-cot-activity-timeline.md)；纠偏软着陆≠空回复；开工 S0a |
| 2026-09-03 | **下一焦点：** Cursor 式 CoT（Thought + Explored/Edited 汇总）；弃工具轨迹/检查点 UI；分支搁置；Mem 收 |
| 2026-09-03 | **Loop 结束态：** edit 意图空停 → `edit_nudge` 一发；诚实合成 / EMPTY_RESPONSE；不误伤纯探索 |
| 2026-09-03 | **收口：** Living 焦点 → 产品狗粮；Mem 对齐 Hermes（不做近义去重）；session_search/Provider/review 后置 |
| 2026-09-02 | **Mem M1 加固：** 空行旧文件按条目解析；写入规范化 §；append→add；replace 拒重复段 |
| 2026-09-02 | **Mem M1：** entry add/replace/remove + operations 批处理；§ 分隔；拒重复 add |
| 2026-09-02 | **Mem M0：** MEMORY.md + target=user\|memory；双轨冻结；MEMORY_GUIDANCE；Settings 双轨 |
| 2026-09-02 | **Gate 深拆 Step 3：** propose_*=prepare；settle 在 before_tool_call；gate 工具不再二次 execute |
| 2026-09-02 | **Gate 深拆 Step 2：** `before_tool_call` action allow\|wait\|block；await 进 `tool_pipeline`；loop 不再 `resolve_await_marker` |
| 2026-09-02 | **Gate 深拆 Step 1：** `_handle_*_gate` / `wait_for_*` → `agent/gate_hooks.py`；loop `resolve_await_marker` |
| 2026-09-02 | **F8 收编：** Goal 留痕钩子化 + session `pinned_goal` + 输入区手动改 Goal |
| 2026-09-02 | **Preset 收编：** `core/preset_hooks`；Strict 强制记忆确认；分支树 UI 明确搁置 |
| 2026-09-02 | **宪章 §4/§5 对齐 Living：** 现状表刷到 A0–A4 完成 + F3/F4 收编；阶段表加状态列 |
| 2026-09-02 | **F4 契约 Step3：** spill→`file:` full_ref；模型 payload 带落盘 hint；F6 `event_from_sse` 复用避免双写 |
| 2026-09-02 | **F4 契约 Step2：** `truncate_head_tail`；列表头尾保留 + 省略计数；stdio/read/grep/list hint 诚实化 |
| 2026-09-02 | **F4 契约 Step1：** `ObservationResult`（model_payload / display_summary / full_ref / truncated） |
| 2026-09-02 | **F3/F4 收编：** gate 续环策略 → `agent/gate_policy.py`；F4 slim → `core/tool_hooks.slim_for_working`；loop 委托 |
| 2026-09-02 | **软着陆继续：** 末轮琥珀色条「继续」→ 结构化续跑（Goal + 未完成/下一步） |
| 2026-09-01 | **缺口收口：** UI 按 leaf 路径配对；`messages?view=active`；regenerate 后不再显示旧 sibling |
| 2026-08-30 | **docs 归位：** `docs/README.md` 地图；archive/research/design/dogfood；根残留进 scripts；AGENTS L0–L3 |
| 2026-08-29 | **长任务软着陆：** `soft_land` SSE + 分节汇报 prompt + 前置横幅 + UI `softLanded`；触顶不装完成 |
| 2026-08-29 | **收编表同步：** F1/F2/F7 → 已收编（GoalModeHooks） |
| 2026-08-29 | **撤回 Steering UI**：插队时灵时不灵，产品面去掉；保留后端 steer 口；停止按钮覆盖「打断」场景 |
| 2026-08-29 | **GoalModeHooks**：F1/F2/F7 收编到 `on_turn_start` / `after_tool_call` / `after_tool_batch`；插队续跑文案加固 |
| 2026-08-29 | **Steering UI**（已撤回）：流式中「插队」→ steer API |
| 2026-08-28 | **A4 完成**：Session Tree（parent_id/leaf_id）；regenerate=branch；AgentMessage + convert_to_llm；Compaction 切点+6-section；Skills catalog；焦点 → 穿插收编 |
| 2026-08-28 | **A3 完成**：EventSink + agent/turn lifecycle SSE；steering 队列 + `POST .../steer`；TurnEvent 轻量 lifecycle；pytest **206**（+8）；焦点 → A4 |
| 2026-08-28 | **A2 完成**：Model Registry 多档案（JSON 持久化）；`/api/model-profiles` CRUD/activate/test；`llm-config` 适配 active；Settings Cursor 式档案卡；密钥不回显；pytest **198**（+8）；焦点 → A3 |
| 2026-08-28 | **A1d 完成**：USER.md 硬上限 1375 + `MEMORY_FULL`；会话冻结快照；`user_md_char_limit`；`test_memory_bounds.py`；pytest **190**（+8）；焦点 → A2 |
| 2026-08-28 | **A1c 完成**：五步 `tool_pipeline`；`loop_preset` 默认 YOLO；gate `auto_apply`；Trusted/Strict 仍确认；设置 UI Preset；`test_preset_yolo.py`；pytest **182**（+6）；焦点 → A1d |
| 2026-08-28 | **A1b 完成**：session `goal_mode` 默认 OFF + PATCH；routes 读会话 flag；UI Goal 芯片；`test_goal_mode_session.py`；pytest **175**（+4）；人工：关=无质量 strip / 开=turn_goal / 刷新持久 |
| 2026-08-28 | **A1a 完成**：`config.goal_mode` 闸门（OFF 跳过 inject/checkpoint/exploration）；routes 临时 ON；`test_goal_mode.py`；pytest **171**（+3） |
| 2026-08-28 | **A0 完成**：`core/` + LoopConfig + `_run_one_turn` + layer 测试；pytest **168**（+8） |
| 2026-08-28 | **对齐宪章重写**：主轴改为 A0–A4；F1–F9 降为收编表；废止占比裁判 |
| 2026-08-26 | （历史）P2 / F7 狗粮收口；F7 消息序修复；pytest 160 — 见旧更新，行为资产仍有效 |

---

## 1. 架构阶段快照（A0–A4）

| 阶段 | 状态 | 说明 |
|------|------|------|
| **A0** 立层 + LoopConfig | ✅ 完成 | `agent_window.core`；`_run_one_turn`；见 [`layer-boundaries.md`](layer-boundaries.md) |
| **A1** 管线 + Preset + Goal 开关 | ✅ 完成 | **A1a–A1d ✅**；GoalModeHooks 收编可穿插 |
| **A2** Model Registry | ✅ 完成 | 多档案 + Settings UI；会话级 profile 已手测。core 经 Handle 仍后置 |
| **A3** 双管道事件 + Steer 口 | ✅ 完成 | EventSink；lifecycle SSE；steer API；F6 轻量落库 |
| **A4** Tree + convert + Compaction | ✅ 完成 | parent_id/leaf；regenerate=branch；convert_to_llm；6-section 摘要 |

---

## 2. 行为资产收编表（原 F1–F9 + 相关）

> 状态列：**已实现** = 代码有行为；**已收编** = 已挂到宪章钩子/层且 Goal OFF 可关。

| ID | 行为 | 已实现 | 已收编 | Goal OFF 目标 | 迁移债 / 下一步 |
|----|------|--------|--------|---------------|-----------------|
| F1 | Turn Goal | ✅ | ✅ | 不注入 | `GoalModeHooks.on_turn_start` |
| F2 | 进度检查点 | ✅ | ✅ | 不跑 | `after_tool_batch` |
| F3 | 失败续环 | ✅ | ✅ | 简化（Preset） | `agent/gate_policy.py` + loop 委托 |
| F4 | 观察瘦身 / data_path | ✅ | ✅ | 始终开 | `ObservationResult` + head/tail + spill 与 F6 对齐 |
| F5 | 环境默认 | ✅ | ◐ | 始终开 | coding；可增强 |
| F6 | TurnEvent 落库 | ✅ | ◐ | 始终开 | A3 lifecycle；树路径已有，嵌套 Entry 可后置 |
| F7 | 探索收敛 | ✅ | ✅ | 不跑 | `after_tool_call`；UI 区分 exploration 可后置 |
| F8 | Goal 留痕 | ✅ | ✅ | n/a | `resolve_session_goal` / `goal_change_audit_event`；`pinned_goal` 手动改 |
| F9 | 狗粮 | ✅ | ◐ | 可选轻量 | Goal ON 主剧本保留 |
| Gate | Diff/Shell/Memory + hunk | ✅ | ✅ | Preset | Step3：prepare→before settle→execute(非 gate)；深拆主路径完成 |
| Mem | USER.md + MEMORY.md + propose_memory | ✅ | ◐ | Preset | M0+M1 ✅（Hermes 对齐）；Provider / session_search / review 后置 |
| LLM | 多档案 Registry | ✅ | ◐ | — | **A2** 完成；会话级 profile 已手测。core 经 Handle 仍后置 |
| Cmp | compress + preserve_goal | ✅ | ◐ | 始终可压 | **A4+** handoff 六节 + 路径 Critical + Constraints/Key Decisions/Next 分工 + 反 Goal 回声；见 [`research/compaction-handoff-peers.md`](research/compaction-handoff-peers.md) |
| CLI | headless | ✅ | ◐ | — | 随分层改名 |
| Steer | mid-run 插队消息 | ✅ API | ◐ | 始终开 | **A3** 队列+API；**UI 已撤回**（停用产品面） |

**摘要：** Goal 质量环 F1/F2/F7/F8 **已收编**到 `GoalModeHooks`（Goal OFF 可关；F8 含 pin + audit）。F3/F4 **已收编**到 `gate_policy` / `tool_hooks`。Mem Provider 等仍有债。

---

## 3. 验收勾选

### 3.1 Goal OFF（默认）— 路线图 §5.1

| # | 标准 | 状态 |
|---|------|------|
| 1 | 工具环稳定（含 tool 消息序） | ✅（F7 序修复后） |
| 2 | 观察不炸窗 | ✅ F4 中间档 |
| 3 | Preset 可运行；默认不弹窗疲劳 | ✅ A1c 默认 YOLO |
| 4 | 写盘诚实化 | ✅ |
| 5 | 中间态可见 | ✅ F6 |

### 3.2 Goal ON — 路线图 §5.2（旧 §0.4 迁入）

| # | 标准 | 状态 |
|---|------|------|
| 1 | 显式 Goal | ✅ 实现；✅ 按钮 + 默认 OFF（A1b） |
| 2 | 检查点对照进度 | ✅ |
| 3 | 成功/失败可核验 | ◐ |
| 4 | Reject/失败续环策略 | ✅ F3 |
| 5 | 触顶软着陆 + Goal | ✅ 诚实分节 + 横幅 + `soft_land` SSE / UI + **继续**续跑 |
| 6 | Goal 留痕 | ✅ F8 |

**A1 完成定义补一条：** Goal OFF 时 §3.2 的 1/2/探索收敛 **不触发**（pytest + 狗粮）。

---

## 4. A4 完成清单

- [x] `parent_id` + `leaf_id` + backfill；list API 仍按 sequence 全量（含树字段）；`?view=active` = leaf 路径  
- [x] `build_path_from_session` / `build_llm_messages`；send 用 leaf 路径  
- [x] regenerate = branch（旧 assistant 不删；新 sibling；leaf 更新）  
- [x] **UI 按 leaf 路径配对**（不再 sequence 误挂旧 sibling）；切支导航 UI 仍后置  
- [x] `AgentMessage` + `default_convert_to_llm`；`LoopConfig.convert_to_llm` 默认  
- [x] Compaction：`find_cut_index` + reserve + 6-section prompt；`compaction_summary`  
- [x] Skills catalog 进 system（非全文 SKILL.md）  
- [x] `test_session_tree` / `test_convert_to_llm`；compress 切点/小节测  

**人工验证：** 连点两次 regenerate → DB 同 user 多 assistant、leaf=最新、**刷新后 UI 显示最新回答**（非旧 sibling）；长对话 auto_compress 摘要含六小节。

---

## 4a. A3 完成清单（已完成）

- [x] `core/event_sink.py`：subscribe / emit（subscriber 异常不打断 loop）  
- [x] loop 嵌套 lifecycle：`agent_start` → `turn_*` → `agent_end`；扁平 tool/token 仍 yield  
- [x] `core/steering.py`：push/drain/peek/clear；`bind_steering`；默认按 `session_id` drain  
- [x] `POST /api/sessions/{id}/steer`；chat/regenerate 传 `session_id`  
- [x] TurnEvent：`agent_*` / `turn_*` / `steer_inject` 轻量 summary  
- [x] `test_event_sink` / `test_steering` / `test_a3_lifecycle`  

**人工验证：** 长工具环中 `POST /api/sessions/{id}/steer`；下一 LLM turn 应见注入 user；SSE 可出现 lifecycle（UI 可忽略）。

---

## 4aa. A2 完成清单（已完成）

- [x] `services/model_registry.py`：profiles JSON；`ModelHandle`；migrate from settings  
- [x] REST：`/api/model-profiles` + activate/test；`/api/llm-config` 适配 active  
- [x] provider 从 active enabled profile 拉 URL/Key/model  
- [x] Settings Cursor 式档案卡（toggle / Base URL / Key / Model ID / Add profile）  
- [x] ModelPicker 优先列启用档案 `model_id`  
- [x] `test_model_registry.py`；pytest **198**  

**人工验证：** 设置 → 模型：多档案卡、密钥占位「Secret saved…」、Set active 后聊天走该档案 Base URL/Key；Add profile 可叠第二张卡。

---

## 4b. A1 开工清单（已完成）

按路线图 **A1a → A1d** 竖切（见 `agent-window-roadmap.md` §4.2）：

- [x] **A1a** `config.goal_mode`：OFF 跳过 inject / checkpoint / exploration；ON 保持现行为  
- [x] **A1b** UI Goal 按钮 + session 持久化；产品默认 OFF（routes 去掉临时 ON）  
- [x] **A1c** 五步工具管线 + Preset→gate `auto_apply`；YOLO 直通（默认）  
- [x] **A1d** USER.md 硬上限 + 冻结快照（§3.5）；Strict 若需再收紧  
- [x] 本文 §1 A1 → 完成；焦点 → A2；pytest 持续全绿  

**质量纪律：** 每切片先写失败/表征测 → 再改 → 全量 `pytest`；不并行大改 Goal+Preset+管线。

**A1b 人工验证：** 新对话 Goal 关 → 发消息无 turn_goal 质量 strip；开 Goal → 下一轮应注入；刷新后 `goal_mode` 仍在。

**A1c 人工验证：** 默认 YOLO → propose_edit 无 DiffPanel 等待（不再闪 pending 卡）；设置 → Trusted → 审批卡回来。

**A1d 人工验证：** 同会话 `propose_memory` 已 apply 后下一轮 system 仍可能是冻结旧 USER.md；新会话才见更新。超限应 `MEMORY_FULL` 而非截断。

---

## 5. Backlog（宪章序，非 F 编号）

| 优先级 | 项 | 阶段 |
|--------|-----|------|
| ✅ | LoopConfig + 抽 turn + layer 测 | A0 |
| ✅ | Goal 闸门（A1a）；routes 临时 ON | A1a |
| ✅ | 按钮默认 OFF（A1b）；session 持久化 | A1b |
| ✅ | beforeToolCall 管线 + YOLO/Trusted（A1c） | A1c |
| ✅ | 记忆有界 + 冻结快照（宪章 §3.5）（A1d） | A1d |
| ✅ | Model Registry 多档案 | A2 |
| ✅ | EventSink + turn 嵌套 + steer 口 | A3 |
| ✅ | Session Tree MVP + convert + Compaction 6-section + Skills catalog | A4 |
| ✅ | Hooks 收编 F1/F2/F7/F8；F3/F4；Preset before_tool_call | 穿插 |
| P1 | regenerate sibling 切支 UI | 产品（**搁置**：设计未定） |
| P1 | **多会话后台续跑** | 产品（**P1–P3 已落地**）：切会话不 cancel；P2 保活 SSE + `liveStreamsRef`；侧栏标题 `.text-shimmer`；完成后未读。**P3**：pending patch/shell/memory 带 `session_id`；`cancel_turn` / `list_*?session_id=` 按会话隔离（Stop A 不撤 B 的门）。 |
| P2 | Steering UI（已撤回，勿再开） | — |
| P2 | Gate 深拆（await → before_tool_call） | Step1–3 ✅ |
| P2 | Mem MEMORY.md / Provider | M0+M1 ✅（对齐 Hermes：精确去重，无近义消解）；Provider / session_search / 后台 review **后置** |
| — | MCP / 网页 / PDF / Project OS | 暂缓 |

---

## 6. 已知未覆盖（测试边界，仍有效）

- 前端无自动化；UI 靠 `tsc` + 人工  
- CRLF diff、文件末尾无换行、并发 propose_edit 同文件  
- 模型是否按需加载 Skill 不可测 → 需人工步骤  

---

## 7. 历史文档

| 文档 | 状态 |
|------|------|
| [`archive/foundation-f4-f6-plan.md`](archive/foundation-f4-f6-plan.md) | **冻结**；F4/F6 方案考古 |
| `archive/foundation-progress-and-f4-f6-plan.md` 等 | **冻结**；勿当进度源 |
| [`README.md`](README.md) | docs 地图 |
| 狗粮脚本 `f9-*` / `p2-f7-*` | Goal ON / 专项；**现行全表**见 [`dogfood/cot-s1-product-checklist.md`](dogfood/cot-s1-product-checklist.md) |
