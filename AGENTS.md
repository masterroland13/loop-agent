# Loop Agent 项目工作规则

> 本文件会被注入系统提示（AGENTS.md 分层加载）。写给在本仓库工作的 Agent。  
> **产品名：** Loop Agent。对用户介绍自己或称呼本产品时只说 Loop Agent。

## 架构与文档权威

- **地图：** [`docs/README.md`](docs/README.md)（docs 分层索引）。  
- **架构真源：** [`docs/architecture-charter.md`](docs/architecture-charter.md)（分层、Goal 模式、Preset、可进化记忆 §3.5、A0–A4）。  
- **交付阶段：** [`docs/agent-window-roadmap.md`](docs/agent-window-roadmap.md)。  
- **进度 Living：** [`docs/foundation-status.md`](docs/foundation-status.md)（A0–A4 + 收编表）。  
- **分层边界：** [`docs/layer-boundaries.md`](docs/layer-boundaries.md)（import 方向；`tests/test_layer_boundaries.py`）。  
- 与宪章冲突时以宪章为准；勿按旧 F1–F9 清单开新旁路焊进 `loop.py`。

## 文档分层（L0–L3）

| 层 | 放什么 | 位置 |
|----|--------|------|
| **L0** | Agent 运行时薄指令 | 根 `AGENTS.md`；可选子树 `AGENTS.md`；`skills/*/SKILL.md`（仅 catalog 注入） |
| **L1** | 权威真源 | `docs/architecture-charter.md`、`layer-boundaries.md`、`agent-window-roadmap.md`；根 `README.md` / `CHANGELOG.md` |
| **L2** | Living / 进行中 | **唯一**进度：`docs/foundation-status.md`；可选 `docs/plans/`、`docs/adr/` |
| **L3** | 档案与参考（默认不注入） | `docs/design/`、`docs/archive/`、`docs/research/`、`docs/dogfood/` |

**规则：**

1. **冲突序：** 宪章 > 路线图 > foundation-status > 其余 docs。  
2. **禁止**在 `docs/` 根再堆无索引长文；新调研 → `research/`，冻结方案 → `archive/`，狗粮 → `dogfood/`，定稿设计 → `design/`。  
3. Living 进度只维护 `foundation-status.md`；勿改 `archive/` 当进度源。  
4. 根目录不放临时脚本/报告；运维与调试进 `scripts/`（见 `scripts/README.md`）。

## 测试纪律

- 改动后端逻辑必须附带 pytest 用例，放 `backend/tests/test_*.py`。
- 断言写「行为」不写「实现」：断言输出包含/不包含什么，不断言内部变量。
- 每个断言尽量有反向形式：不仅「应该有 X」，还要「不应该有 Y」。
- 修 bug 的顺序：先写**失败的复现测试** → 再修 → 测试变绿后提交。回归测试必须留下。
- 改完跑全量：`PYTHONPATH=src python -m pytest tests/ -q`；前端 `npx tsc -b`。
- 注意测试数量变化：加了多少用例，passed 数就应该涨多少，没变说明没被收集。

## 测试的边界（不要假装覆盖了）

- 前端无自动化测试，UI 改动只能 `tsc` + 人工点。
- 模型行为不可测（是否按需加载 Skill、是否诚实调工具），这类改动必须附带人工验证步骤。
- 已知未覆盖：CRLF 文件 diff、文件末尾无换行、并发 propose_edit 同一文件。

## 提交纪律

- 提交前 `git status` 检查测试残留文件（`*-test.py`、`dogfood_*.txt` 等）不要入库。
- commit message 用英文短句概括 why，例如 `hunk-level partial apply: per-block checkboxes in DiffPanel + apply-partial API`。
- 仓库未配 git 身份，用一次性参数：`git -c user.name=caapap -c user.email=caapap@localhost commit`。
- 每次提交前往 `CHANGELOG.md` 的 `[Unreleased]` 加条目。
- **架构进度**：改动 A0–A4、Goal 模式、Preset、或旧 F 项收编行为时，同步更新 [`docs/foundation-status.md`](docs/foundation-status.md)；战略阶段变更改 [`docs/agent-window-roadmap.md`](docs/agent-window-roadmap.md)；分层/原语变更改 [`docs/architecture-charter.md`](docs/architecture-charter.md)。

## 模型行为防线

- 系统提示要求：创建/修改/运行必须调 propose_edit / propose_shell，禁止文字声称完成。
- 模型声称「已创建/测试通过」但本轮无 gate 事件时，loop 会挂未验证警告——不要绕过这个机制。
- 被拒绝后用户要求重试时，必须重新调工具，不能只回文字。

## 环境

- 后端：`backend/.venv`，`PYTHONPATH=src uvicorn agent_window.main:app --port 8000`
- 前端：`npm run dev -- --host 0.0.0.0 --port 5173`
- CLI：激活 venv 后 `loop`（ask / status / approve / reject / run --wait）
- 路径含空格，所有 shell 命令里路径必须加引号。
