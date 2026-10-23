# Loop Agent 脚本

仓库根目录只保留工程入口；运维与本地检查脚本都放这里。

| 脚本 | 作用 |
|------|------|
| `start-dev.sh` | 启动后端（8000）；提示如何开前端 |
| `loop shell` | 打开桌面窗口；关窗停掉它自己拉起的后端和界面 |
| `restart-loop.sh` | 重启前后端 |
| `rebuild-preview.sh` | 构建前端并重启 vite preview |
| `preview-server.mjs` | Windows 侧预览静态 `dist/` |
| `restart-uvicorn.sh` | 杀掉 8000 后重启 uvicorn |
| `build-frontend.sh` | `npm run build`（加载 nvm） |
| `smoke/check.sh` | 检查 venv / 进程 / 关键 import |
| `smoke/unit.sh` | shell 白名单单元冒烟 |
| `smoke/api.sh` | 绑定工作区 + shell 冒烟（依赖后端已启动） |
| `smoke/weather.sh` | 调用内置天气工具 |
| `smoke/sse-smoke.py` | SSE 冒烟 |
| `debug/show-routes.sh` | 打印 routes.py 片段 |
| `debug/find-api.sh` | 搜索 sessions / SSE 相关代码 |
| `debug/inspect-db.py` | 查看本地 DB |

CLI 审批（不调模型）：在 `backend/` 下 `PYTHONPATH=src python -m pytest tests/test_cli_gates.py tests/test_cli_http_gates.py -q`。依赖 LLM 的手工清单见 [`docs/design/v1-7-headless-cli-design.md`](../docs/design/v1-7-headless-cli-design.md) §12。

在仓库根执行，例如：

```bash
./scripts/start-dev.sh
./scripts/smoke/check.sh
```
