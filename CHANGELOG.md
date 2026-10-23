# Changelog

All notable changes to Loop Agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Dates are UTC+8.

---

## [Unreleased]

### Added
- **首次向导：** 工作区还没绑定时，窗口先让用户填一个模型（Base URL / API Key / Model ID，可从带地址的预置填入），再选已有文件夹或在当前位置新建。新建只建子文件夹，点「使用此文件夹」才绑定。只有一份空档案时会补全并激活它。新建接口拒绝相对父路径，避免落到进程当前目录。已绑定工作区的开发服务不会出现这一步。`loop shell` 拉起的后端不读 `backend/.env`。
- **安装目录：** `loop install` 把构建好的界面、窗口程序和一份后端虚拟环境放进 `~/.local/lib/loop-agent`，写入 `~/.local/bin/loop`（走安装目录里的解释器），并放一份桌面启动项（绝对路径开窗，不依赖当前 PATH）。`loop uninstall` 只删这些程序文件，用户数据和工作区留下。已经装好的 `loop` 再执行 `install` 会停下来，要从仓库跑。`loop shell` 用这份环境开窗，页面由同一个后端在 8765 托管，不再从仓库源码导入。用户数据仍在 `~/.local/share/loop-agent`。开发用的 8000 / 5173 不动。桌面进程保存模型时不把密钥写进 `.env`。
- **桌面壳：** `loop shell` 打开 Loop Agent 窗口，并拉起一份用 `~/.local/share/loop-agent` 的后端。关窗后这个进程停掉。8765 已被占用时不开第二份，避免接到别人的后端。`/health` 必须是 200 才算起来。父进程收到 SIGTERM / SIGHUP 会停掉子进程。WSLg 下关掉 WebKit 硬件加速，避免窗口全黑；网页铺满窗口。首次向导单独一页，不再盖在主界面上。窗口强制走 X11，避免 WSLg 的 Wayland 加速层把光标盖住。安装页用 fetch+eval 装入界面脚本，出错会写在页面上。打包时去掉 Markdown 邮箱识别里的 lookbehind，WebKitGTK 2.38 才能解析。这份数据目录不带工作区，也不动开发用的 `backend/data`。端口是 8765，避开正在跑的 8000 / 5173。
- **会话级模型档案：** 新会话抄当前档案；顶栏选择写入当前会话（`profile_id` + `model_id`）；并行会话各用各的网关 client。设置可从 Moonshot、DeepSeek、OpenRouter 等 OpenAI 兼容预置开卡。密钥存放说明见 [`docs/research/api-key-storage.md`](docs/research/api-key-storage.md)。§4 手测已通过。
- **界面语言 zh/en：** Settings「偏好」切换；侧栏/右键/设置/Files/审批卡/搜索/工作区/模型选择等壳层文案走 `src/i18n`；Agent 仍跟用户提问语言；`zh`/`en` 词条对齐（416）。
- **Files Word（.docx）：** mammoth/htmldocx 读写；预览 + HTML 源码编辑；调研报告 `docs/research/files-editor-office-scope.md`（Excel/PPT 暂缓）。
- **Files 编辑体感：** 工具栏保存（悬停提示 Ctrl+S）、磁盘变更提示；Markdown 预览+编辑、Word 预览可编辑；保存后保持编辑器打开。
- **Files 树右键菜单（二期）：** 添加到对话（`@path`）、资源管理器显示、剪切/复制/粘贴、递归删除非空文件夹（含统计确认）；后端 `copy` / `stats` / `reveal` + `delete?recursive=true`。
- **Files 树右键菜单（一期）：** 文件夹/文件上下文菜单（新建文件/文件夹、复制路径、重命名、删除）；复用 Sidebar `ContextMenu` 样式；后端 `mkdir` / `rename` / `delete` API + pytest。
- **docs 地图与归位：** [`docs/README.md`](docs/README.md)；`AGENTS.md` L0–L3 规则；冻结方案→`docs/archive/`，调研→`docs/research/`（含 Spec Kit 报告），设计→`docs/design/`，狗粮→`docs/dogfood/`；根残留脚本/报告→`scripts/` / `scripts/debug/` / `scripts/smoke/`
- **GET `/api/sessions/{id}`：** 返回单会话（含 `leaf_id` / `goal_mode` / `workspace_root`），避免只能 list；前端 `getSession()`。
- **压缩可观测性：** `context.compress` 审计带 `method`/`preview`/`older_count`；`turn_meta` 增加 `compress_method` / `compress_preview`。
- **GoalModeHooks 收编：** `core/goal_hooks.py`；`with_goal_mode(True)` 安装 F1/F2/F7 钩子；`loop.py` 经 `on_turn_start` / `after_tool_call` / `after_tool_batch` 调用，不再散落 `if goal_mode` 策略。
- **A4 Session Tree MVP + convert_to_llm + Compaction 升格：** `messages.parent_id` / `entry_type`、`sessions.leaf_id` + 线性 backfill；`core/session_tree` 建 leaf→root 路径；regenerate = 分支（旧 assistant 保留，新 sibling 更新 leaf）；`AgentMessage` + `default_convert_to_llm`（`compaction_summary`→带【对话压缩摘要】的 user）；`LoopConfig.convert_to_llm` 必填有默认；压缩切点 `find_cut_index` + 六小节摘要 prompt + reserve；Skills system 仅 catalog。人工：连点两次 regenerate，DB 同 user 下多 assistant、leaf 指向最新、上下文只走 leaf 路径；长对话 auto_compress 摘要含 Goal/Constraints/Progress/Key Decisions/Next Steps/Critical Context。pytest **217**（+11）
- **A3 双管道事件 + Steering：** `EventSink`（Pipe A fire-and-forget）；loop 嵌套 `agent_start` / `turn_start` / `turn_end` / `agent_end`（保留原有扁平 SSE）；`steering` 进程内队列 + `POST /api/sessions/{id}/steer`；TurnEvent 轻量落库 lifecycle/steer_inject。人工：长工具环中 POST steer，下一 LLM turn 应见注入 user 消息。pytest **206**（+8）
- **A2 Model Registry（多档案）：** Settings → 模型为 Cursor 式档案卡（标题+enable 开关、灰字说明、Base URL / API Key / Model ID 行内卡片）；可 **Add profile** 纵向叠多张；**Set active** / Test / Save / Delete；密钥不回显（已配置时占位「Secret saved. Enter a new key to replace it.」）。聊天走 **active** 档案的 Base URL/Key/model；`model_profiles.json` 持久化；`/api/model-profiles` CRUD + activate + test；旧 `/api/llm-config` 适配 active。人工：设第二档案并激活后发消息应打到该网关。pytest **198**（+8）
- **F7 探索收敛（MVP）**：连续同类探索工具（list_dir / read_file / grep / read_attachment）达阈值时注入收敛提示 + `progress_checkpoint`（`reason: exploration`）；`exploration_repeat_threshold` 设置项（0=关，默认 6）
- **P2 图片多模态（MVP）**：有图附件时 user 消息注入 `image_url`（base64 data URL）；自动路由到 `vision_model` / `LLM_VISION_MODEL`；图片上限 5MiB；系统提示禁止对图调用 `read_attachment`；UI 图片 chip/气泡缩略图；PDF 抽取仍暂缓
- **Session↔folder hard bind**：`sessions.workspace_root` 服务端落库；创建会话可带 root；前端 sync map + 切会话激活对应工作区
- **propose_delete**：审批门控删除文件（`is_delete` patch + Apply `unlink`）；系统提示禁止用 rm/脚本删文件
- **P1 真·链接附件**：`POST/GET /api/sessions/{id}/attachments` 落盘；消息存 `attachment_ids` 引用（不内联全文）；工具 `read_attachment`；UI 选文件即上传 chip + 气泡可点下载
- **#9 F8 Goal 变更留痕**：send/regenerate 对比上一 assistant 目标；变更时审计 `goal.change` 并在 SSE/trace `turn_goal` 带 `previous_goal`；消息旁目标条显示「目标 · 已变更」
- **#8 M6 审计 UI / 会话回放**：设置 → 审计 — 按会话/类型筛选、事件展开看 payload、「打开此会话回放」、导出 JSON；`GET /api/audit` 支持 `event_type`（含 `turn.` 前缀）；`GET /api/audit/sessions`；`GET /api/sessions/{id}/audit`
- **#7 M2 压缩保留 Goal**：`compress_messages_if_needed(preserve_goal=…)` — 摘要头钉住本轮目标、summarize 提示不得改写、压缩后重注入 `【本轮目标】`；send/regenerate 先抽 Goal 再压缩；设置文案同步
- **#5 大输出 data_path**：工具结果/参数 >8KB 时 spill 到 `session.data_path/turns/...`，TurnEvent `full_ref=file:…`；`GET /api/sessions/{id}/blobs?ref=`；ToolTimeline 展开时拉取全量
- **F2 可见检查点回复**：检查点后若模型先叙述进度再继续调工具，将该正文经 `progress_checkpoint.reply` SSE/trace 落到消息旁「检查点」条（有回复时默认展开）；终局纯文字收工不重复挂条
- **F9 Foundation 狗粮**：固定两轮剧本（ImportError 解释 → 「好的」深挖 + 对照 Goal 收工）；`dogfood/f9_scenario.py` 断言 helpers；`test_f9_dogfood.py` mock loop 集成；[`docs/dogfood/f9-dogfood-script.md`](docs/dogfood/f9-dogfood-script.md) 人工清单；2026-08-24 API 收口（Goal 继承须重启 uvicorn 后复验通过）
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

### Changed
- **用户数据目录：** 没设 `APP_DATA_DIR` 时，会话和档案放到 `~/.local/share/loop-agent`，不再落到进程当前目录。开发在 `.env` 里写 `APP_DATA_DIR=./data` 仍用 `backend/data`。新目录不绑定工作区，也不自动搬旧数据。空白值回退到用户目录；以 `~` 开头的路径会展开成家目录。
- **仓库杂物：** 清掉根目录临时脚本、重启报告、pytest 输出和已入库的 `__pycache__`。重启报告改写到 `logs/`。
- **产品名：** 界面、关于页、文档和 CLI 从 Hal Agent / `hal` 改为 Loop Agent / `loop`。配置目录改为 `~/.config/loop-agent`，仍会读取旧的 `hal-agent`。浏览器里 `hal.recentModels` 和 `hal:files-auto-save` 会迁到 `loop.*`。Python 包名仍是 `agent_window`。
- **模型服务文案：** 中文界面下，档案卡的「当前 / 设为当前 / 测试 / 删除」、说明和密钥占位改为中文。说明不再加句号。Temperature、Base URL、API Key、Model ID、厂商名和模型 id 仍保留英文。
- **档案卡顶栏：** 「当前 / Active」徽章与右侧开关同一行、同一高度，新档案沿用同一布局。
- **审批档位说明：** 两处分号都改成紧挨汉字和英文，不再有一处贴着全角括号。
- **预置下拉箭头：** 「从预置添加」的系统箭头换成侧栏同款箭头，并离右边框留出一截。
- **底栏空输入占位：** 「发送跟进」改为「发送指令」。
- **设置卡片说明：** 标题与 hint 改为上下排列，避免「UI language」被挤成两行。
- **切会话不断流（Phase 3）：** pending patch/shell/memory 打上 `session_id`；`cancel_turn` 与 `GET …/patches|shells|memory/proposals?session_id=` 按会话过滤；Stop A 不撤 B 的审批门。pytest **+3**（`test_gate_session_scope`）。
- **切会话不断流（Phase 2）：** 切走不再 abort SSE；`liveStreamsRef` 按会话保活并离线归约 pairs/pending；切回即时恢复 UI 与 Stop；后台事件不写入当前会话。
- **切会话不断流（Phase 1）：** 断开 SSE 不再 `cancelSession`（后端继续跑）；Stop 才取消当前会话；侧栏对运行中会话标题使用与 CoT「Worked for」相同的 `.text-shimmer` 光线流转（无「生成中」文案）；后台完成标未读；切回仍 busy 时恢复 Stop + poll。
- **Files 面板 MVP：** 顶栏 Files 切换；`SurfaceHost` 可扩展表面；人用 `GET/PUT /api/workspace/files/*`（list/read 裸文本/write 直写，方案 A）；coding 层新增 `read_text_file`/`write_text_file`，不改 Agent `read_file`。调研：[`docs/research/files-viewer-mvp.md`](docs/research/files-viewer-mvp.md)、[`docs/research/app-packaging-gap.md`](docs/research/app-packaging-gap.md)。
- **Files 打开态：** 浏览/编辑分屏改为整页编辑器（绝对定位 textarea 修空内容塌陷）；打开 Files 时隐藏消息上下跳转。
- **Files Cursor 式布局：** 左栏搜索 + New File + 编辑器；右栏可展开文件夹树（仿 Sidebar chevron）；点文件在左侧打开；面板加宽。
- **Files 交互抛光：** 空态居中搜索/新建（开文件后隐藏）；通栏标签顶栏（关标签自动保存）；树可收起；面板宽与树宽可拖拽（有最小宽度）；关闭/树切换改为图标。
- **Files 细调：** 对话区 `min-w-[440px]`；拖拽条改细（类 sidebar 发丝线）；工作区名与树收起回到树顶栏；空态搜索/新建改为更轻的胶囊样式。
- **顶栏分栏：** App 通栏 header 拆入对话列；Files `TopChrome` 对齐 `h-11` 作为右侧顶栏，左右空间各归各列。
- **顶栏/Files 开关：** 对话顶栏左侧显示当前 session 名；去掉 Files 胶囊；面板开关为顶栏右侧图标（开合皆此，完全收起无窄条）；面板最大宽度按行宽扣聊天 `min` 计算，避免拖宽时文件树被裁掉。
- **Files chrome 打磨：** 顶栏右簇 `…` / 🔍 / `<<`（前两者占位）；打开文件为双行（标签行 + 工具行）；`.md` 支持 Preview/Source；空态搜索/新建上移并轻化。
- **Files 多标签与保活：** 可同时打开多文件（底边高亮标签，非胶囊）；工具栏常显；树开关改工具栏列表图标且收起不留窄条；Preview/Source 移到编辑区右上；脏关闭弹「保存/不保存/取消」；面板收起仅隐藏不卸载，保留打开与未保存状态。
- **Files 再打开空白：** 保活时勿用外层 `hidden` 包一层再测宽（宽会被测成 0）；改为 `SurfaceHost visible` 直接藏 aside，并忽略过小行宽、再显示时重算宽度。
- **顶栏腾空：** 去掉 header 的 session id / 工作区名 pill；session id 并入回合 Meta 行与复制 JSON（`session_id`）；该区留给后续 Files 展示。
- **围栏代码块 Copy：** Markdown `pre` 右上角复制按钮（悬停显示；触控常显），复制块内源文本；可选语言标签。
- **模型选择：** 改为贴模型按钮上方的 ⋮ 式弹出菜单（非居中模态）；手动/选用过的模型写入 `loop.recentModels` 并入列表，免反复填写。
- **输入/气泡 Cursor 对齐：** 底栏与消息列同为 `max-w-3xl px-6` 左右齐边；`--composer-radius-pill` / `--composer-radius-block` 两档；已发送气泡永远 block；多行/Goal/附件底栏块态；固定目标去分割线。
- **底部栏尺寸：** 控件 32px、字号/内边距略收；底栏略下移（`pb-7`）；单行文案 `leading-8` 保中轴。
- **输入框描边：** `--input-border` 加深（浅 `#b8b3a6` / 深 `#555658`），文本框外沿、「+」、快捷胶囊共用，避免看不见边。
- **空会话输入框：** 上下略收（min-h / padding / 文本区）；圆角改 `composer-shell`（22px 回退，支持时 Apple squircle）。
- **输入框观感（润）：** `--input-border` 改半透明 hairline；composer 多层轻阴影 + 内高光；`composer-chip` 统一「+」与 G/M/P；聚焦用柔和 accent 晕。
- **输入框角位：** 「+」/发送同径 `ACTION_BTN`；壳内边距左右下统一 `14px`，贴合连续圆角。
- **底部长条 / 用户气泡：** 圆角改为全胶囊 `radius-pill`，端头弧度与内圆按钮一致（对齐 Cursor）。
- **底部多行：** 超过一行时文案在上、工具在下；圆角从胶囊切到圆角矩形（`radius-xl` / squircle），对齐 Cursor。
- **空会话快捷条：** Goal 移出输入框工具栏，与 Multitask / Plan New Idea 并列（G→M→P）；去图标与 ⇧Tab；三钮与「+」统一描边胶囊、默认透明、悬停显底。
- **CoT 生成中动画：** 去掉三点跳动；Activity 顶栏与「尚无正文」占位都改为 Cursor 式 `Worked for Xs` 文字扫光（秒数跳动）；发送时即写入 `activityStartedAt`。
- **CoT Activity 密度：** 短 Thought（<5s）按流式顺序嵌进 Explored/Edited，展开可见全文；长 Thought 仍顶层打断；流式结束自动收起「Worked for」。pytest turn_activity **22**（+3）。
- **嵌套 Thought 默认收起：** Explored/Edited 展开时只显示 `Thought Ns` 行，正文点开才见；Read/Grepped 等仍直接列出。
- **删除 ToolTimeline 死代码：** 移除未引用的 `ToolTimeline.tsx`、仅为其服务的 `retryToolStep`/`onRetryToolStep` 接线，以及前端 `getSessionBlob` 包装；保留 `toolTrace`/Activity/spill blobs API。
- **消息操作按钮常显：** 复制/收藏不再 `opacity-0` 悬停才显示，避免「重试」左侧留白；图标改为 Lucide 路径 + 圆角描边，略放大更清晰。
- **Compaction handoff 质量：** 交接向六节 prompt + 注入 handoff 前缀；extractive 抽路径/工具进度；coerce 反 Goal 回声并灌 Critical 路径；summarize `max_tokens` 2048。调研：[`docs/research/compaction-handoff-peers.md`](docs/research/compaction-handoff-peers.md)。pytest **325**（+5 compress）。
- **Compaction Progress 诚实：** 摘要窗口无工具时写「未见工具结果」而非「尚未开始」；Next Steps 禁止无工具却「等待」；coerce 替换虚假 idle Progress；Next Steps 忽略「贴摘要/列文件」类核对提问。pytest **331**（compress）。
- **§7 压缩狗粮剧本：** [`docs/dogfood/section-7-compress-playbook.md`](docs/dogfood/section-7-compress-playbook.md)（降 limit + 多轮灌上下文强制触发）。
- **狗粮全表：** [`docs/dogfood/cot-s1-product-checklist.md`](docs/dogfood/cot-s1-product-checklist.md)（CoT/门控/Mem/结束态/压缩/Goal；含最小集与决策表）。
- **Bind to Folder：** 未绑定会话右键可挂到已有工作区（确认后写 `workspace_root` 并移出未绑定）；已绑定不可解绑；输入框 This PC 移除（打开工作区仍走侧栏 Open Workspace）。
- **Bind 确认 / 错误提示：** 用应用内弹层替代 `window.confirm`；API 校验错误 toast 只显示可读 `msg`（不再整段 JSON）；Copy/Bind 子菜单更窄；工作区行前加文件夹图标；Bind 图标改为 folder-input。
- **设置开关：** 重做圆点对齐（36×20 轨道 / 14px 圆点 / 上下 3px 钉死）；去掉 shadow，避免贴边毛刺。
- **用户气泡：** 已发送消息上下内边距 `py-3.5` → `py-2.5`，单行时更扁一点。
- **CoT 展开层次间距：** 可展开关键字与其下级块头尾各加 `my-1.5`；同级条目仍贴行高，不加额外空隙。
- **CoT Activity 间距：** `Worked for` 行上移一点（`-mt-2`），更贴近用户气泡与正文之间的视觉中线。
- **行内 code 观感：** 浅灰底（`--code-inline-bg`，亮/暗都只微加灰）；普通英文词/布尔/裸文件名不再打底，仅路径、行号、符号名等保留；系统提示收紧反引号用法。
- **CoT UI：** TurnActivity 去掉卡片/表格边框；正文同号字号与行距、无加粗、`--text-muted`；三角紧贴文案尾部；关键词（Worked/Thought/Edited/Read…）提亮一档；默认收起（流式中自动展开顶栏）。
- **CoT S1：** Provider 解析 `reasoning_content` / thinking 块；loop 在终稿/工具前发 `thought` SSE；档案开关 Reasoning/CoT；Activity 展示真 Thought（不造假）。pytest **310**（+6）。
- **CoT S0c：** 点击 Activity 的 Edited/Ran 行 → 审批区 Diff/Shell 卡片滚动并高亮（已折叠的「已应用/已完成」会自动展开）。
- **CoT S0b：** `TurnActivity` UI 替换 ToolTimeline / 检查点卡片；SSE 灌 `activity`；trace 刷新恢复 Explored（edit 可经 tool_result 回填）。
- **CoT S0a：** `turn_activity` 纯函数（Explored/Edited/Thought 分组）；pending 不计已编辑；`propose_memory`→note；TS 镜像 `src/utils/turnActivity.ts`。pytest **304**（+15）。
- **CoT 调研收口：** [`docs/research/cursor-cot-activity-timeline.md`](docs/research/cursor-cot-activity-timeline.md)（纠偏软着陆≠工具后空回复；Thought 须流式/真通道；开工 S0a Explored/Edited）。
- **Loop 结束态：** 改仓意图下「只探索+空停」自动 `edit_nudge` 续催一次；诚实合成文案（区分查阅 vs 未 propose_edit）；`EMPTY_RESPONSE` 说明零工具空包。纯探索不逼 edit。pytest **289**（+6）。
- **Mem M1（条目 ops）：** `propose_memory` 支持 `action=add|replace|remove`（`old_text` 唯一子串）与原子 `operations=[...]`；条目以 `\n§\n` 连接；拒绝精确重复 add；保留 M0 `mode=replace|append`。MEMORY_GUIDANCE / MemoryPanel 同步。pytest **282**（+6）。
- **Mem M1 加固：** 无 § 的空行旧文件按多条目解析；写入统一规范成 §；`mode=append`→`action=add`；整文件 replace 含重复段亦 `DUPLICATE`；加强「勿用 replace 追加」引导。pytest **283**（+1）。
- **Mem 收口（对齐 Hermes）：** Living 焦点改为产品狗粮；明确不做近义/矛盾自动消解；`session_search` / Provider / 后台 review 仍后置。
- **Mem 双轨路径修复：** Settings/API 改用 `/api/memory/tracks/{user|memory}/content`；响应校验路径后缀；避免旧进程忽略 query `target` 导致两轨都写 USER.md。pytest **276**（+1）。
- **Mem M0（MEMORY.md）：** 用户级 `MEMORY.md`（上限默认 2200）+ `propose_memory target=user|memory`；双轨冻结快照；system 注入 `MEMORY_GUIDANCE` + 两轨占用；Settings 双编辑器；MemoryPanel 区分 target。pytest **275**（+6）。
- **Gate 深拆 Step 3：** `propose_*` 仅 prepare；`tool_pipeline` 序为 prepare → before settle → execute（非 gate）；`abandon_await_proposal` + F3 `blocked` 结束态。pytest **269**（+3）。
- **Gate 深拆 Step 2：** `GatePresetDecision.action` allow|wait|block；AWAIT_* 在 `tool_pipeline` 经 `before_tool_call`(phase=await_gate) 决议后 await；loop 不再调用 `resolve_await_marker`。pytest **266**（+5）。
- **Gate 深拆 Step 1：** `wait_for_*` / patch·shell·memory gate handlers 抽到 `agent/gate_hooks.py`；loop 经 `resolve_await_marker` 委托，不再内联 await。pytest **261**（+4）。
- **F8 Goal 留痕收编：** `resolve_turn_goal` / `goal_change_audit_*`（`goal_hooks`）；session `pinned_goal` + PATCH；Goal ON 时输入区可编辑固定目标；审计 source：`extract` / `regenerate` / `pinned` / `manual`。pytest **257**（+8）。
- **Preset 收编：** `core/preset_hooks`（`GatePresetDecision` / `before_tool_call`）；loop 经 `resolve_gate_decision`；**Strict≠Trusted**（Strict 始终确认记忆）；Settings 文案同步。pytest +5。
- **宪章 §4/§5 对齐 Living：** 现状 vs 目标表刷新（F1–F4 已收编、A0–A4 ✅）；阶段表加状态列；文档头「绞杀前期」→ 主轴完成。
- **F4 契约 Step3：** 超 8KB 经 `observe_spill` 落 `file:turns/…`；slim payload 带 `full_ref` + 落盘 hint；SSE 携带同 ref；F6 复用不双写。pytest +2。
- **F4 契约 Step2：** `truncate_head_tail`（`…[省略 N 字]…`）；列表头尾条目 + `*_omitted`；shell/read hint 标明头尾保留。pytest +2。
- **F4 契约 Step1：** `ObservationResult` + `observe_tool_result()`；`slim_tool_result` / `slim_for_working` 委托；截断时 inline `full_ref`（≤8KB）。pytest +3。
- **F3/F4 收编：** gate 续环策略抽到 `agent/gate_policy.py`（`resolve_gate_outcome`）；F4 slim 经 `core/tool_hooks.slim_for_working`；`loop.py` 委托。pytest **237**（+2）。
- **软着陆「继续」：** 末轮 `softLanded` 条上真实「继续」按钮；发送结构化续跑 user（Goal + 未完成/建议下一步摘录），不再空喊「继续」。`soft_land_continue_user_message` + 前端镜像。pytest **235**（+2）。
- **Leaf 路径视图收口：** regenerate 旁支仍在库中时，前端 `buildMessagePairs` 按 `leaf_id`（parent 链）配对，不再用 sequence「下一则 assistant」误挂旧回答；复制对话同样只导出当前 tip 路径。`GET .../messages?view=active` 返回 leaf 路径。pytest **233**（+1）。
- **Settings typography：** 设置面板统一为 `text-[14px]`，层级改用字重与颜色（不再用多档字号）。
- **字距：** 全局 `letter-spacing` `0.015em` → `0.025em`（贴近消息区 / Cursor 量级，略松）。
- **用户气泡：** `--user-bubble` 与底部输入框同色（`var(--input-bg)`），减轻对回复正文的干扰。
- **浅色高亮：** 对话选中描边 `--pair-highlight` 浅色主题改为近黑（`#111111`），避免白底看不见。
- **会话滚动：** 切换 session 记住并恢复离开时的滚动位置（不再每次从顶长滑到底）；发送新消息后把本轮顶到视口上方；去掉列表 CSS `scroll-smooth` 与完成时滚到底。
- **Markdown 字重/列表标：** `strong` 为 `font-medium`（不加亮色）；标题 h1–h3 字号不变，字重恢复并强制标题内所有子节点同字重（避免标题里嵌套 `**` 导致半粗半细）；列表 marker 用正文色。
- **未读蓝点：** 直径 7px→5px；流式在当前会话内看完完成则标记已读并跟进 `updated_at`，避免看完再切走仍亮未读；仅离开期间完成才 `markUnread`。
- **长任务软着陆：** 触顶 `max_tool_iters` 时发 `soft_land` SSE、强制分节汇报（已完成 / 未完成·阻塞 / 建议下一步）、回复前置「提前收口·不代表完成」横幅；空模型回复走确定性兜底。前端 `softLanded` 旗标 + 琥珀色提示；trace/文案可回填。pytest **232**（`test_soft_land.py` +5）。
- **P0 压缩质量：** 保留 Pi 六段 LLM 主路径；失败/空/「（见原文）」改为抽取式六段兜底；增量合并上一轮摘要；`_summarize_blob` 与六段 prompt 对齐。pytest **223**（+6）。
- **P2 YOLO 门控闪烁：** YOLO 下 shell/diff/memory 不再发 `pending` SSE；前端仅 `await_approval` 进入等待态，running 不锁输入。
- **A1d USER.md 硬上限 + 会话冻结快照：** `USER_MD_CHAR_LIMIT=1375`（可设 `user_md_char_limit` 500–8000）；`propose_memory` 超限抛 `MEMORY_FULL`（不静默截断，须 `mode=replace` 合并缩短）；`freeze_user_md_for_session` / `get_frozen_user_md` 双态——本会话 system 只用冻结文本，中途 apply 立刻落盘；超限注入带 ⚠️ 提示。人工：同会话记住事实后工具显示已应用，下一轮 system 仍可能是旧 USER.md，新会话才刷新。`test_memory_bounds.py`；pytest **190**（+8）
- **A1c 五步工具管线 + Preset（默认 YOLO）：** `tool_pipeline.run_tool_steps`；`loop_preset` 设置（yolo/trusted/strict）；YOLO 下 propose_edit/delete/shell/memory 跳过 `await_approval` 直接 apply（仍发 pending 事件）；Trusted/Strict 保留确认门。产品默认写操作无弹窗；设置 → Agent 可切 Trusted。pytest **182**（+6）。人工：YOLO 改文件无 DiffPanel 等待；Trusted 审批卡回来
- **A1b 修复：Goal OFF 仍出质量环：** routes 在 `goal_mode=False` 时不再 extract/注入/compress-preserve/meta 带 goal；前端 meta/turn_meta 不再继承上轮 goal。Goal 按钮与 This PC 同尺寸（图标+文案），ON=实心 accent，OFF=暗色。pytest **176**
- **A1b Goal 会话开关：** `sessions.goal_mode` 默认 OFF；PATCH 可切换；chat/regenerate 按会话 flag 传 `LoopConfig.with_goal_mode`；输入栏 Goal 芯片；刷新后持久化
- **A1a Goal 闸门：** `LoopConfig.goal_mode` OFF 时不注入 Turn Goal、不跑进度检查点、不跑探索收敛；ON 保持原行为
- **A0 立层落地：** `agent_window.core`（`LoopConfig` / `AgentLoopState` / `TurnOutcome`）；`run_agent_loop` 抽 `_run_one_turn`；[`docs/layer-boundaries.md`](docs/layer-boundaries.md)；pytest 168（+8）
- **文档对齐宪章：** `architecture-charter.md` 为架构真源；`agent-window-roadmap.md` 重写为 A0–A4 交付主轴（可选 Goal、Preset、收编已完成 Foundation）；`foundation-status.md` 改为迁移/收编 Living 进度；旧 F4/F6 方案文档冻结；`AGENTS.md` 更新文档权威
- **宪章 §3.5 可进化记忆：** 吸收 Hermes `hermes-memory-system.md` 主张（有界 curated、冻结快照、四层分工、写入跟 Preset）；路线图 A1 / 进度表 backlog 对齐
- 设置 → Agent：补上 **探索收敛阈值** 滑条（`exploration_repeat_threshold`，0=关，3–12；默认 6）
- `docs/foundation-status.md`：P2 后端 MVP 勾选；网页 fetch·search / MCP / PDF 仍暂缓
- 系统提示：仅附件 / 「（见附件）」且无明确指令时，默认只读 + 口头摘要；禁止自行 propose_edit/落盘/写提取脚本，除非用户明确要求写文件
- 目标 / 检查点 / 工具轨迹 / 回合 meta：字号加大、对比度提高；检查点与工具轨迹默认折叠；展开三角改侧边栏 chevron；轨迹状态改 SVG + 主题色（浅色可读），去掉竖连线
- 检查点：模型未写进度说明时 settled，UI 显示「无进度说明」不再卡在「等待说明」；摘要同一行对齐并去掉多余间隔点
- 工具轨迹状态图标与文案垂直居中对齐
- 移除侧边栏「移到未绑定工作区」；reclaim 仅 remap 孤儿 `proj_*`（不再扫 `__unbound__`）
- 会话 reclaim 策略收紧：只 remap 孤儿 `proj_*`，不再把 `__unbound__` 全量扫进磁盘项目
- 侧边栏「Projects」改为 Cursor 风格 **Workspaces**：右侧「Open Workspace」（文件夹+号）打开 Recents / On This PC 菜单；三道杠筛选暂不做
- 侧边栏项目行：展开用可旋转右/下箭头（200ms），文件夹开合改为更细的 Lucide 风格并交叉淡入
- 侧边栏改为 Cursor 风格项目树：This PC 绑定的真实目录显示为可展开项目；可同时展示多项目下的会话；顶部「New Chat」与项目行右侧「+」同效（在对应项目下新建对话）
- 路线图按宪章 **A0–A4** 再对齐（取代旧「死抱目标默认脊柱 / Foundation F 清单」主轴）

### Fixed
- **桌面界面代理：** `scripts/preview-server.mjs` 把 `/api` 的查询串一并转到后端。选上级目录、打开子文件夹才会落到点中的路径。
- **自我介绍：** 系统提示里的产品名只写 Loop Agent。纯介绍里引用「测试通过」不再被当成这一轮写过文件，不再追加未审批声明。真的声称写盘或测试通过、又没有审批记录时，声明仍会加上。
- **侧栏时间：** 右边的数字改为距最近一次发送指令的时间。回复、改名、换模型不再把它往后推。无时区的 UTC 时间按 UTC 解析，避免东八区多出约 8 小时。还没发过指令的会话用创建时间。
- **会话名：** 侧栏里手动改过的名字会记住，之后发消息不再改写。没改过名字的会话，仍只用第一条指令生成一次短标题。
- **切会话：** 整行都能点中，同一工作区里切换不再重复请求工作区。已经显示出来的会话，后台刷新不会再把另一段消息闪上去，也不会再次滚动。
- **顶栏模型跟会话走：** 切到没有模型列的旧会话时，不再沿用上一会话的模型名；启动时不再用网关模型列表改写顶栏。手填若正好等于一张档案的默认模型，会绑上那张档案。档案回落时把新的档案 id 一并写回当前会话，切走再回来仍是回落后的模型。
- **会话发消息的网关检查：** 按该会话的档案判断有没有 URL 和 Key。当前档案没 Key 时，不再挡住另一张已配置的会话；会话档案没 Key 时，也不改用当前档案的 Key。压缩摘要走同一张档案的 client。
- **厂商预置示例：** Moonshot 预填改为官方 `kimi-k3`；DeepSeek 改为 `deepseek-flash`；Groq 改用仍对开发者开放的 `openai/gpt-oss-120b`；Together 改到 `api.together.ai`。
- **Diff/Shell 卡左侧紫条：** 待审批卡不再用 `border-l` 强调，与普通边框一致。
- **会话输入框丢字/无法继续输入：** 底栏换行时不再卸载 textarea；中文输入法合成期间跳过高度测量；会话消息加载中不再在居中/底栏两套输入框间切换。
- **Files 保存冲突误报：** `mtime_ns` 改为 API 字符串传递（避免 JS 丢纳秒精度）；mtime 漂移但内容未变时凭 `base_content` 仍可保存；冲突时对话框内显示错误并提供「重新加载」。
- **Files「在资源管理器中显示」：** WSL 下改用 `explorer.exe` + `wslpath`，不再依赖缺失的 `xdg-open`.
- **编辑/粘贴中等长度文案白屏：** 底栏 `ChatInput` 在临界换行宽度上因 `leading-8`↔`leading-5` 与 `barExpanded` 互触发无限 `setState`，React 卸载整树；现拆开测量/高度 effect，并用稳定 line-height + 滞回判断。
- **底栏粘贴形变 / 编辑描边 / sticky 露边：** 换行首帧即块态圆角、去掉 `border-radius` 过渡；编辑态不再套外层 outline，高亮画在 bar 上；sticky `z-index` 改为越早越高并略增底垫；消息列表 `isolate` 以免盖住设置等弹层。
- **切会话串停止键：** 切换 session 时 abort 流会 bump epoch 导致 `stream_end` 被忽略、`isStreaming` 粘住；现强制清 busy，停止键不再带到新会话。
- **max_tokens 截断诚实提示：** `finish_reason` 为 `length`/`max_tokens` 时在终稿末追加黄字说明（与压缩无关）；§7 狗粮剧本改为短终稿 + 提高 max_tokens，避免半句截断误判压缩失败。
- **Goal/CoT 间距：** 用户气泡 / 目标条 / Worked for 统一 `mb-3`；去掉错误负边距；目标条文案去重「目标 目标：」。
- **Reasoning 常开：** Settings 去掉 CoT 开关；有网关 reasoning 就显示 Thought，没有就不显示。
- **记忆 DUPLICATE 观感：** Activity 显示可读文案而非裸 JSON；propose_memory 一开始即记 memory_gate，减少误报黄字。
- **狗粮后续：** Goal 条与气泡/CoT 间距；Reasoning 关则不展示 Thought；记忆门通过后不再误报「未 propose_edit」；附件「保存到 workspace」纳入 edit 意图 + 系统提示强制 propose_edit。
- **CoT Edited/Ran 丢失：** Apply/Reject 同步写 activity；`done` 重载保留更完整 activity；hydrate 兼容历史 `gate` 与 `tool_result.full_ref`；新持久化保留 `diff`/`shell`/`memory` 类型。pytest **318**（+5）。
- **误报「请求失败」横幅：** 成功 `done`/首条 `token` 时清除 `messageError`；SSE 在 `done` 后忽略迟到的 `error`；新发送/停止/切会话时 abort 旧流并用 epoch 丢弃过期事件；SSE `event:` 行优先于 JSON 内 `type`。
- **F7 收敛消息序**：探索收敛 / 检查点 user 注入延后到整批 `tool` 回灌之后；取消/中断时 `_append_missing_tool_results` 补齐缺失 `tool_call_id`，避免上游 400（`tool_calls` 后缺 tool messages）
- **Dogfood §4.5.4**：`extract_turn_goal` 长 filler 继承 prior 目标；纯 tool 回合空正文合成中文模板（避免 `EMPTY_RESPONSE`）；`settings.update` 审计携带可选 `session_id`
- live tool timeline can expand spilled shell/tool output (#5)
- **F6 刷新/停止**：同步创建 assistant 占位；取消/错误时 `finalize_interrupted` 落库 trace + `turn_cancelled`；修复 `buildMessagePairs` 孤儿 user 配对导致空白页；停止后标 `failed` 并显示重试；刷新后从 API 恢复 ToolTimeline
- **F6 刷新续跑**：SSE 断开不再 `watch_disconnect` 取消 turn；agent 在后台继续写 DB，轮询追进度；重试按钮常显（非 hover）；停止后 API 竞态合并 `failed`
- 工具轮次上限从 8 提到默认 24（可配置 `max_tool_iters`，8–64；设置 → Agent）；达上限时先尝试无工具总结，避免任务直接中止无结果
- Shell / Diff 审批区：已完成命令与已应用改动默认折叠为摘要行；审批区限高可滚动，避免占满视口导致消息区无法浏览

### Removed
- **Steering UI（插队）：** 产品面去掉插队按钮/占位/前端 `steerSession`；停止按钮保留。后端 `POST .../steer` 与队列仍在（CLI/后置），暂不暴露。

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
