# Changelog

All notable changes to Hal Agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Dates are UTC+8.

---

## [Unreleased]

### Added
- **Session↔folder hard bind**：`sessions.workspace_root` 服务端落库；创建会话可带 root；前端 sync map + 切会话激活对应工作区
- **propose_delete**：审批门控删除文件（`is_delete` patch + Apply `unlink`）；系统提示禁止用 rm/脚本删文件
- **P1 真·链接附件**：`POST/GET /api/sessions/{id}/attachments` 落盘；消息存 `attachment_ids` 引用（不内联全文）；工具 `read_attachment`；UI 选文件即上传 chip + 气泡可点下载

### Changed
- 系统提示：仅附件 / 「（见附件）」且无明确指令时，默认只读 + 口头摘要；禁止自行 propose_edit/落盘/写提取脚本，除非用户明确要求写文件
- 目标 / 检查点 / 工具轨迹 / 回合 meta：字号加大、对比度提高；检查点与工具轨迹默认折叠；展开三角改侧边栏 chevron；轨迹状态改 SVG + 主题色（浅色可读），去掉竖连线
- 检查点：模型未写进度说明时 settled，UI 显示「无进度说明」不再卡在「等待说明」；摘要同一行对齐并去掉多余间隔点
- 工具轨迹状态图标与文案垂直居中对齐
- 移除侧边栏「移到未绑定工作区」；reclaim 仅 remap 孤儿 `proj_*`（不再扫 `__unbound__`）
- 会话 reclaim 策略收紧：只 remap 孤儿 `proj_*`，不再把 `__unbound__` 全量扫进磁盘项目
- 侧边栏「Projects」改为 Cursor 风格 **Workspaces**：右侧「Open Workspace」（文件夹+号）打开 Recents / On This PC 菜单；三道杠筛选暂不做
- 侧边栏项目行：展开用可旋转右/下箭头（200ms），文件夹开合改为更细的 Lucide 风格并交叉淡入
- 侧边栏改为 Cursor 风格项目树：This PC 绑定的真实目录显示为可展开项目；可同时展示多项目下的会话；顶部「New Chat」与项目行右侧「+」同效（在对应项目下新建对话）
- 路线图按 **Loop + 死抱目标** 重构（`docs/agent-window-roadmap.md`）：新增 §0 纠偏脊柱；插入 Foundation 主线（Goal/检查点/失败续环等）；Pi/DSH 原 §0.3 并入 §4 并映射到观察/Steer/Preset；现状基线按仓库实情纠偏；Project OS 明确为项目级死抱目标

### Fixed
- live tool timeline can expand spilled shell/tool output (#5)
- **F6 刷新/停止**：同步创建 assistant 占位；取消/错误时 `finalize_interrupted` 落库 trace + `turn_cancelled`；修复 `buildMessagePairs` 孤儿 user 配对导致空白页；停止后标 `failed` 并显示重试；刷新后从 API 恢复 ToolTimeline
- **F6 刷新续跑**：SSE 断开不再 `watch_disconnect` 取消 turn；agent 在后台继续写 DB，轮询追进度；重试按钮常显（非 hover）；停止后 API 竞态合并 `failed`
- 工具轮次上限从 8 提到默认 24（可配置 `max_tool_iters`，8–64；设置 → Agent）；达上限时先尝试无工具总结，避免任务直接中止无结果
- Shell / Diff 审批区：已完成命令与已应用改动默认折叠为摘要行；审批区限高可滚动，避免占满视口导致消息区无法浏览

### Added
- **#9 F8 Goal 变更留痕**：send/regenerate 对比上一 assistant 目标；变更时审计 `goal.change` 并在 SSE/trace `turn_goal` 带 `previous_goal`；消息旁目标条显示「目标 · 已变更」
- **#8 M6 审计 UI / 会话回放**：设置 → 审计 — 按会话/类型筛选、事件展开看 payload、「打开此会话回放」、导出 JSON；`GET /api/audit` 支持 `event_type`（含 `turn.` 前缀）；`GET /api/audit/sessions`；`GET /api/sessions/{id}/audit`
- **#7 M2 压缩保留 Goal**：`compress_messages_if_needed(preserve_goal=…)` — 摘要头钉住本轮目标、summarize 提示不得改写、压缩后重注入 `【本轮目标】`；send/regenerate 先抽 Goal 再压缩；设置文案同步
- **#5 大输出 data_path**：工具结果/参数 >8KB 时 spill 到 `session.data_path/turns/...`，TurnEvent `full_ref=file:…`；`GET /api/sessions/{id}/blobs?ref=`；ToolTimeline 展开时拉取全量
- **F2 可见检查点回复**：检查点后若模型先叙述进度再继续调工具，将该正文经 `progress_checkpoint.reply` SSE/trace 落到消息旁「检查点」条（有回复时默认展开）；终局纯文字收工不重复挂条
- **F9 Foundation 狗粮**：固定两轮剧本（ImportError 解释 → 「好的」深挖 + 对照 Goal 收工）；`dogfood/f9_scenario.py` 断言 helpers；`test_f9_dogfood.py` mock loop 集成；[`docs/f9-dogfood-script.md`](docs/f9-dogfood-script.md) 人工清单；2026-08-24 API 收口（Goal 继承须重启 uvicorn 后复验通过）
- Turn Goal 续写继承：「好的，…」前缀的长跟进仍继承上一轮实质目标（F9 / F1）
- 侧边栏右键菜单：Pin/Unpin、Rename、Mark as Read/Unread（未读蓝点）、Copy Agent ID / Copy Transcript、Delete；项目行 Remove from Sidebar；流式时在后台会话完成会标未读
- 侧边栏右键菜单与会话行视觉精修：Lucide 图标、elevated 浮层与入场动画、Copy 子菜单 hover 桥接；未读小蓝点 + 字重；移除 hover 铅笔/垃圾桶（统一右键操作）
- 菜单图标 16×16 栅格 + 细描边；未读蓝点改为径向渐变 + 柔光（Cursor 风格）
- **F4 观察瘦身（Foundation 中间档）**：`observation.slim_tool_result` — read_file / grep / list_dir / gate 四类 formatter；全局 6k 字符上限；失败结构化 `{status, error, hint}`；loop `working[]` 回灌 slim，SSE/F6 仍存 full
- **F6 中间态落库（Foundation）**：共用 `TurnEvent` schema；turn 开始即写占位 assistant；工具/gate/检查点事件增量落库 `messages.trace`；`GET /messages` 返回 trace；刷新后 ToolTimeline/检查点可恢复（轮询 active session）
- **进度检查点（Foundation F2）**：每 N 次工具或审批 gate 返回后，loop 注入对照 Turn Goal 的检查点消息；SSE `progress_checkpoint`；设置 → Agent 可配间隔（0 = 仅 gate）；消息旁「检查点」条
- **失败续环（Foundation F3，修订）**：用户 **Reject** / 部分应用 → 本轮结束并告知；**超时/失败** → 带 `continue_hint` 自动续环至多 1 次，再失败则结束并说明「已重试仍未成功」；仅 `cancelled` 中止
- **Turn Goal**：每轮从用户消息提取目标并注入 loop（短回复如「好的 / 继续」及「好的，…」续写继承上一实质目标）；SSE `meta`/`turn_goal`/`turn_meta.goal`；消息旁「目标」条；设置 → Agent 说明
- Shell 裸 `python` 自动改写为 backend `.venv` 解释器，否则 `python3`（审批卡片显示改写后命令）
- 路线图曾增 §0.3：Pi Agent / DeepSeek Harness 借鉴决策清单（现并入重构后的 §4）
- 写盘声明检测加强：正则补充「新建」「创建」「测试通过」「验证通过」「N passed」等模式；跟踪 shell gate；没走任何审批门但声称完成时强制挂警告
- 审批超时时间可配置：`APPROVAL_TIMEOUT_SEC` 环境变量，默认 300 秒
- 审批卡片出现时自动滚动到可见区域
- Shell 卡片命令可复制（点击复制按钮，确认变绿勾）
- LLM 错误提示分类：区分连接超时 / 地址不可达 / SSL 证书 / 401 / 403 / 404 / 429 / 500 / 502/503 / 模型不可用 / 响应超时 / 上下文超限

---

## [bbeaf28] — 2026-08-16

### Added
- **hunk 级部分应用（M1）**：Diff 卡片按 `@@` 分块渲染，每块一个 checkbox（默认全勾）
- 新端点 `POST /api/workspace/patches/{id}/apply-partial`，body `{ "hunk_ids": [0, 2] }`
- Patch 新状态 `PARTIAL`；loop 中 partial 有独立模板话术，不再被误判为超时
- 后端 diff 解析：`parse_hunks()` 拆分 unified diff 为块列表；`apply_hunks_to_content()` 只合成选中块
- 前端 `DiffPanel` 按块分组，顶栏「全选」+ 选中计数；部分勾时显示「Apply 选中 (N/M)」按钮
- 测试：`test_hunk_apply.py` 8 个用例覆盖解析、全选、不选、子集、空选报错、重复决定、partial 模板

---

## [3b75f80] — 2026-08-16

### Added
- `hal run --wait`：发任务后轮询 pending 审批，等清空或超时返回
- `--wait-timeout` 参数自定义等待上限（默认 300s）
- stdin 管道支持：`echo "..." | hal ask -` / `hal run -`
- 退出码：0 完成 / 2 出错 / 3 等待超时

---

## [5242c06] — 2026-08-16

### Added
- **CLI 审批门**：`hal status` / `hal approve` / `hal reject`
- `hal status` 显示工作区全局 pending patches/shells/memories；`--session-id` 可选显示会话状态
- `hal approve --patch-id|--shell-id|--memory-id <id>` 脚本式审批；无 id 时交互式逐项确认
- 非交互模式（`--no-input`）未带 id 时退出码 2，不静默批准
- CLI 配置文件 `~/.config/hal-agent/config.json` 支持 `base_url` / `timeout` / `default_model` / `auto_approve`
- **模型服务设置**：Window 设置页可直接修改 Base URL / API Key / 默认模型，保存写入 `backend/.env` 并立即生效
- 模型选择器支持手填模型 id（列表没有时）
- 测试：`test_cli_gates.py` 13 个、`test_cli_http_gates.py` 3 个、`test_llm_config.py` 4 个

### Fixed
- **pending 列表污染**：`GET /api/workspace/patches`（shell/memory 同理）只返回 `pending` 状态，不再混入 rejected/timeout/failed；新建会话面板干净

### Changed
- 项目更名：Agent Window → Hal Agent；CLI 命令 `agent` → `hal`
- 设置页「模型服务」替代旧「覆盖开关」模式，直接读写 `.env`

---

## [5f4f44a] — 2026-08-13

### Added
- **初始提交**：React + Vite 前端 + FastAPI + SQLite 后端 + LiteLLM 网关
- 工作区绑定（This PC）、会话 CRUD、流式对话
- **工具调用**：`read_file` / `list_dir` / `grep` / `propose_edit` / `propose_shell` / `propose_memory`
- **审批门**：写文件出 Diff 卡片 Apply/Reject；跑命令出 Shell 卡片 Run/Reject；写记忆出 Memory 卡片
- **Batch C**：Rejected Diff/Shell 保留可见 + Retry；工具步失败可重试；Skills 支持 `SKILL.md` + YAML frontmatter
- **Dogfood 修复**：Rejected retry 回到 pending；旧 rejected/failed 卡片重启后消失；工具步重试有错误反馈
- **Mini-patch**：拒绝后强制调工具；未验证写盘声明挂警告
- **V1-7 无头 CLI**：`hal ask` / `hal health` / `hal sessions` / `hal workspace` / `hal assets`
- 上下文压缩、turn_meta（模型/耗时/token）、审计事件、资产盘点
- 模型选择器从网关拉可用列表
- 脚本整理：`scripts/` 下分 smoke/debug 子目录

---

## 未提交 / 待做

- [ ] grep 工具异常（「Exit code 1, No matches」来源未确认，待复现）
- [ ] 会话标题自动生成优化（让模型生成更准确标题）
- [ ] v2 任务对象（任务卡片、验收标准、产物面板）
- [ ] 前端 UI 优化（用户提的需求，待细化）
