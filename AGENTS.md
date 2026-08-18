# Hal Agent 项目工作规则

> 本文件会被注入系统提示（AGENTS.md 分层加载）。写给在本仓库工作的 Agent。

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

## 模型行为防线

- 系统提示要求：创建/修改/运行必须调 propose_edit / propose_shell，禁止文字声称完成。
- 模型声称「已创建/测试通过」但本轮无 gate 事件时，loop 会挂未验证警告——不要绕过这个机制。
- 被拒绝后用户要求重试时，必须重新调工具，不能只回文字。

## 环境

- 后端：`backend/.venv`，`PYTHONPATH=src uvicorn agent_window.main:app --port 8000`
- 前端：`npm run dev -- --host 0.0.0.0 --port 5173`
- CLI：激活 venv 后 `hal`（ask / status / approve / reject / run --wait）
- 路径含空格，所有 shell 命令里路径必须加引号。
