# 为什么 CI 草案只跑后端 pytest

> L3 调研。2026-11-04 在云 VM 上实跑之后写的。工作流是草案，**不要合并**。  
> 产品默认不动：`auto_compress` 仍关。不开始 C6 / C7，不做 N2（MCP client）。

## 这次实际跑了什么

仓库当时没有 `.github/workflows/`。下面是同一台云 VM、同一份 `main`（`47c18f98fc55f1faeaa9b2f967878323e4310520`）上的命令。虚拟环境放在 `/tmp/loop-agent-venv`，没有写进仓库。安装前系统没有 `python3-venv`，用 `sudo apt-get install -y python3.12-venv` 补上，没有改 git 配置。

仓库里没有 `backend/.env`。命令没有设置 `LLM_API_KEY`、`APP_DATA_DIR` 或 `auto_compress`。

### 后端 pytest — 通过

```bash
cd backend
PYTHONPATH=src /tmp/loop-agent-venv/bin/python -m pytest tests/ -q --tb=short -ra
```

- 解释器：Python 3.12.3（GCC 13.3.0）
- pytest 9.2.0（`pip install -e ".[dev]"` 按 `pyproject.toml` 范围解析，**没有**用 `uv.lock`；这台机器没有 `uv`）
- 退出码：**0**
- 页脚：**461 passed, 814 warnings in 8.09s**
- 没有 `FAILED` / `ERROR` / `SKIPPED` 段。`-ra` 没有打出 short test summary，即 0 failed、0 skipped、0 error。
- 进度点：6 行 × 72 + 29 = 461。

同一次安装解析到的直接依赖（只记录实跑，CI 会重新解析，版本可能不同）：

| 包 | 版本 |
|----|------|
| pytest | 9.2.0 |
| pytest-asyncio | 1.4.1.post1 |
| fastapi | 0.162.0 |
| starlette | 1.10.0 |
| uvicorn | 0.54.0 |
| pydantic | 2.14.2 |
| pydantic-settings | 2.16.2 |
| httpx | 0.28.1 |
| SQLAlchemy | 2.1.8 |
| openai | 3.45.0 |

814 条警告全部在 pytest 摘要里，按来源加总等于页脚。都不是失败。另有一条在摘要之前打印：`pytest_asyncio` 的 `PytestDeprecationWarning`（`asyncio_default_fixture_loop_scope` 未设置）。页脚 814 与摘要分组之和相同。

| 条数 | 种类 | 位置 |
|------|------|------|
| 1 | PydanticDeprecatedSince20（class Config） | `config.py:14` `Settings` |
| 1 | 同上 | `schemas.py:38` `SessionResponse` |
| 1 | 同上 | `schemas.py:110` `MessageResponse` |
| 1 | DeprecationWarning `on_event` | `main.py:31` |
| 1 | 同上（由上面的 startup 触发） | site-packages `fastapi/applications.py:4723` |
| 67 | `datetime.utcnow()` | `storage.py:45` |
| 325 | 同上（SQLAlchemy 包装列默认值） | site-packages `sqlalchemy/sql/schema.py:4362` |
| 40 | 同上 | `audit.py:27` |
| 170 | 同上 | `storage.py:119` |
| 170 | 同上 | `storage.py:215` |
| 11 | 同上 | `turn_trace.py:111` |
| 3 | 同上 | `storage.py:163` |
| 6 | 同上 | `storage.py:145` |
| 6 | 同上 | `storage.py:153` |
| 6 | 同上 | `api/routes.py:1634` |
| 2 | 同上 | `api/routes.py:1607` |
| 2 | 同上 | `turn_trace.py:143` |
| 1 | 同上 | `storage.py:180` |

`datetime.utcnow` 合计 809。加上 3 条 Pydantic 和 2 条 `on_event`，等于 814。

副作用：未设置 `APP_DATA_DIR` 时，产品默认数据目录是 `~/.local/share/loop-agent`。这次 pytest 在那里写下 `model_profiles.json`（413 字节）。`api_key` 是空字符串；`base_url` 为代码默认 `https://llm-cn.gameye.ai/v1`，`model_id` 为 `kimi-k3`。`users/local-user/sessions/` 是空目录。该文件在仓库外，没有提交，也没有密钥。

### 前端类型检查 — 通过

`npm ci`（155 个包）之后：

```bash
npx tsc -b --pretty false
```

- TypeScript 6.0.3，Node v22.23.4，npm 10.9.9
- 退出码：**0**
- 标准输出空，没有类型错误

### 前端 oxlint — 通过（有警告）

```bash
npm run lint
# oxlint -c config/oxlint.json src
```

- oxlint 1.76.0
- 退出码：**0**
- **14** 条 warning，0 error：
  - `src/components/WorkedForText.tsx:8` — `react(only-export-components)` ×1
  - `src/i18n/index.tsx:25,35,60,72,77` — 同上 ×5
  - `src/hooks/useMessagePairs.ts:1798,1801` — `react-hooks(exhaustive-deps)` 在 cleanup 里读 ref ×2
  - `src/App.tsx:438,502,527,549,884,899` — `exhaustive-deps` 缺 `settings.language` ×6

### 没有跑的检查

- 仓库没有配置 ruff、mypy、pyright。没有临时装一个来制造一份风格报告。
- `npm ci` 顺带打印了 `npm audit`：3 个 high severity。没有单独做审计，也没有跑 `npm audit fix`。
- 写这一节时，GitHub Actions 还没有执行这个文件。第一次实跑见下文「GitHub Actions 第一次实跑」。VM 上的 461 / 814 是提交前的结果，不是 Actions 日志。

## 工作流为什么写成这样

[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) 只做一件事：`ubuntu-latest` 上 Python 3.12，`pip install -e ".[dev]"`，然后在 `backend/` 跑 `PYTHONPATH=src python -m pytest tests/ -q --tb=short -ra`。

- **只跑 pytest。** `AGENTS.md` 把后端 pytest 当作逻辑改动的门禁。前端没有自动化测试；oxlint 现有 14 条 warning 且退出码为 0，放进 CI 要么永远黄、要么得先改产品代码。这次不改产品。
- **不需要密钥。** 上面的 461 条是在没有 `backend/.env`、没有 `LLM_API_KEY` 的情况下通过的。`permissions: contents: read`。不使用 `pull_request_target`，不上传覆盖率，不访问模型网关。
- **不改产品默认。** 工作流不设置 `auto_compress`，不启动 8000 / 5173，不写安装目录。
- **Python 3.12。** 与这次实跑的 3.12.3 同一次要版本。`pyproject.toml` 写的是 `>=3.10`，3.10 和 3.11 没有跑。
- **pip，不用 uv。** `backend/uv.lock` 在，但这台 VM 没有 `uv`，验证走的是 pip 浮动范围。草案和验证用同一种安装，所以「VM 绿了」不等于锁文件可复现。锁文件里的包名仍是 `agent-window-backend`，和 `pyproject.toml` 的 `loop-agent-backend` 不一致；草案不去改这个。
- **动作版本**用 2026-11 仍在维护的大版本：`actions/checkout@v7`、`actions/setup-python@v7`。浮动大版本以后还会动。
- **触发**是全部 `pull_request` 和全部 `push`。同一仓库里的 PR 往往两条都会跑。没有加并发取消，文件保持短。`timeout-minutes: 15`：这次 pytest 本身 8.09 秒，余量给 pip。
- **警告不当成错误。** 814 条是既有 `utcnow` / Pydantic class Config / FastAPI `on_event`。把它们变成 error 会让门禁变红，但行为测试是绿的。修这些不在这条草案里。

## GitHub Actions 第一次实跑

提交 `a62580fb2efc48014e7c6d7b589931d4ad53621e` 推上去之后，同一条工作流跑了两次，都成功。这就是上面说的「push 与 pull_request 会各跑一次」。没有密钥。Runner 上的 Python 是 **3.12.16**（`actions/setup-python@v7` 日志：`Successfully set up CPython (3.12.16)`），不是 VM 里的 3.12.3。

| 事件 | 结论 | 运行 | pytest 页脚 |
|------|------|------|-------------|
| `push` | success，job 约 37s，整次运行 39s | https://github.com/masterroland13/loop-agent/actions/runs/41875214348 | `461 passed, 814 warnings in 12.13s` |
| `pull_request` | success，job 约 32s，整次运行 34s | https://github.com/masterroland13/loop-agent/actions/runs/41875242115 | `461 passed, 814 warnings in 11.77s` |

两条日志的页脚都与 VM 的 461 passed / 814 warnings 相同，用时更长。Actions 日志里同样先出现那 3 条 Pydantic class Config 警告。没有把 Actions 上的 814 条再按文件加总一遍；页脚是原样抄的。

这次只说明「这个草案文件能在 GitHub 上跑完 pytest」。仍然不要合并：依赖没有锁，3.10 / 3.11 没跑，前端不在 CI 里，814 条警告也没有变成失败。

## 合并之前还缺什么

1. GitHub 已经跑过 `a62580f` 上的这个文件，push 与 pull_request 都是 461 passed。这不等于可以合并。
2. 若要可复现，再决定是装 `uv` 并 `uv sync --frozen`，还是把这次 pip 版本写死。现在两样都没做。
3. 前端 `tsc` 可以以后另加一个 job；oxlint 要先处理那 14 条 warning，或者明确允许 warning。
