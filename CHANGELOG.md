# Changelog

All notable changes to Hal Agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Dates are UTC+8.

---

## [Unreleased]

### Added
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
