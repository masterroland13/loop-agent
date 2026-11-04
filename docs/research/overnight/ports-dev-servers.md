# 开发端口：8000 / 5173 / 8765 不要杀

> L3 调研笔记。给通宵值守、云端 Agent，以及任何「清端口再起服务」的步骤。  
> 这三口上常常已经挂着人正在用的 Loop Agent。杀掉等于打断开发会话，或把桌面壳从用户数据上拽下来。  
> 本文不改产品行为。人自己要重启开发服务时，仍用仓库里已有的脚本，并知道那些脚本会先清端口。

## 三口各是谁

| 端口 | 谁在听 | 数据 | 人怎么打开 |
|------|--------|------|------------|
| **8000** | 开发后端：`uvicorn agent_window.main:app` | 开发时 `backend/.env` 的 `APP_DATA_DIR=./data`，库在 `backend/data` | 不直接当页面。Vite 把 `/api`、`/health` 代理到这里 |
| **5173** | 开发前端：`npm run dev -- --host 0.0.0.0 --port 5173` | 无会话库 | 浏览器打开 `http://localhost:5173/`，带热更新 |
| **8765** | `loop shell` 拉起的安装目录后端，只绑 `127.0.0.1` | `~/.local/share/loop-agent`（或 `LOOP_SHELL_DATA_DIR`）。不读 `backend/.env`，不动 `backend/data` | 同一进程托管安装好的 `dist/`，窗口开 `http://127.0.0.1:8765/` |

约定写在根 `AGENTS.md`、`README.md` / `README.zh-CN.md`、`docs/design/loop-agent-manual.md`。前端代理在 `vite.config.ts`。桌面端口是 `backend/src/agent_window/host/session.py` 里的 `BACKEND_PORT = 8765`。

`loop ask`、`loop status`、`loop approve`、`loop reject`、`loop run --wait` 默认访问 `http://127.0.0.1:8000`。要连桌面壳时，才用 `AGENT_BASE_URL` 或 `~/.config/loop-agent/config.json` 的 `base_url` 指到 `http://127.0.0.1:8765`。

8000 和 8765 必须能同时活着。前者是检出目录里的狗粮后端，后者是装好的窗口。关窗口只会停掉它自己拉起的 8765 进程，不会去动 8000 / 5173。

## 不要杀

通宵任务、云端 Agent、探活失败后的「清理」都不要对这三口做下面任何一件事：

- `fuser -k`、`fuser -k -n tcp` 指向 8000、5173 或 8765
- `pkill` / `kill` 匹配 `uvicorn agent_window.main:app`、`vite.*5173`、`npm run dev.*5173`，或 `loop shell` 拉起的窗口与后端
- 代跑会先清端口的脚本：
  - `scripts/start-dev.sh` — 杀掉 8000 和 5173，再拉后端
  - `scripts/restart-loop.sh` — 杀掉 8000 和 5173，并 `pkill` uvicorn / vite / npm
  - `scripts/restart-uvicorn.sh` — 杀掉 8000 再拉后端
  - `scripts/rebuild-preview.sh` — `pkill` preview（预览若占着 5173，页面会一起没）

这些脚本是给人在自己的终端里重启用的。Agent 不要代跑。

杀掉之后：

- **8000**：开发会话的后端没了。5173 还在的话，`/api` 和 `/health` 全部失败。正在跑的回合和待审批会断。默认 CLI 也连不上。`backend/data` 里的库还在磁盘上，但进程内未完成的写入没有了。
- **5173**：浏览器里的开发界面和热更新没了。8000 上的会话还在，人打不开页面。
- **8765**：桌面壳的后端没了。窗口连的就是这一口。`loop shell` 发现 8765 已被占用会停下来，报「已经被占用」，不去接另一份后端。反过来，把占用者杀掉，就是把用户正在看的那一份停掉。用户数据在 `~/.local/share/loop-agent`，和 `backend/data` 不是同一份；不要为了「腾端口」把这一口清掉再开一份。

健康检查失败只说明「这口现在没有可用的 Loop Agent」。下一步是停下来看日志，不是杀进程、换端口，或再起一份盖住它。

## 可以怎么看（只读）

确认还活着。下面的命令不发 SIGTERM / SIGKILL：

```bash
curl -sS --max-time 3 http://127.0.0.1:8000/health
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 3 http://127.0.0.1:5173/
curl -sS --max-time 3 http://127.0.0.1:8765/health
ss -ltnp | grep -E ':8000|:5173|:8765' || true
```

`/health` 要看到 200 才算这口后端起来了。5173 看 HTTP 状态码即可。`ss` 只列出谁在听，不要把打印出来的 pid 拿去 `kill`。

人要自己重启开发服务时，用 `scripts/restart-loop.sh` 或 `scripts/restart-uvicorn.sh`，并且接受它们会先杀掉 8000（前者还会杀 5173）。不要把 8765 加进这些脚本的清端口列表。
