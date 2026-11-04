# 桌面壳

`loop shell` 是窗口宿主，和浏览器、CLI 并列，不进 `agent/` 环。窗口进程不 import 环。它从安装目录拉起一份后端，页面由这个后端托管，关窗后两边都停。

源码：

| 路径 | 职责 |
|------|------|
| `backend/src/agent_window/host/session.py` | 安装、启动、停进程、环境变量 |
| `backend/src/agent_window/host/frontend.py` | `LOOP_SHELL=1` 时挂 `dist/` |
| `backend/src/agent_window/main.py` | `include_router` 之后 `mount_shell_frontend(app)` |
| `shell/loop-window.c` | GTK + WebKitGTK 窗口。阻塞到用户关闭 |
| `src/components/SetupWizard.tsx` | 还没有工作区时的首次向导 |

开发服务仍是仓库里的 uvicorn **8000** 与 Vite **5173**。壳用 **8765**，不去占那两个端口。

## 打开一次窗口

`run_shell()`：

1. `shell_install_dir()`。缺 `dist/index.html`、`loop-window` 或 venv 里的 Python 时直接失败，提示先 `loop install`。
2. `prepare_data_dir(shell_data_dir())` 只 `mkdir`。不写、不拷贝 `workspace.json`，也不碰 `backend/data`。
3. `launch_plan`：工作目录是安装目录。后端 argv 是安装 venv 的 Python，`-m uvicorn agent_window.main:app --host 127.0.0.1 --port 8765`。窗口 argv 是 `loop-window http://127.0.0.1:8765/`。
4. `shell_port_is_free()`。8765 已有连接则退出，文案要求先关掉另一份窗口，避免接到别人的后端。
5. 子进程日志：`/tmp/loop-shell-backend.log`、`/tmp/loop-shell-window.log`。
6. `GET /health` 必须 200，最多等 25 秒；再等 `GET /` 200。然后开窗。`window.wait()` 返回后 `stop_process` 停窗口和后端。
7. 父进程收到 SIGTERM / SIGHUP 走 `_stop_shell_on_signal`，`finally` 里仍会停子进程。`stop_process` 对进程组先 SIGTERM，3 秒后 SIGKILL。

`backend_env()` 交给子进程的环境：

| 变量 | 值 |
|------|----|
| `APP_DATA_DIR` | 用户数据目录 |
| `LOOP_SHELL` | `1`。于是不读 `backend/.env`，保存模型也不把密钥写进 `.env` |
| `LOOP_STATIC_DIR` | 安装目录的 `dist` |
| `PYTHONPATH` | **删掉**，避免检出树盖住已安装的包 |
| `WEBKIT_DISABLE_DMABUF_RENDERER` 等 | `1`。WSLg 上否则窗口全黑 |
| `GDK_BACKEND` | `x11`。避免 Wayland 加速层把光标画到点不中的层 |
| `WAYLAND_DISPLAY` | **删掉** |

## 窗口程序

`shell/loop-window.c`：一个 `WebKitWebView` 铺满窗口，加载 argv 里的 URL。关闭即 `gtk_main_quit`。指针用 GDK 座位轮询，再 `window.__loopPointer(x, y)` 注进页面（缩放后的坐标）。加载失败留在窗口里，不静默黑屏。

`host/frontend.py` 只在壳上挂静态文件：

- `GET /` → `index.html`
- `/assets` → `dist/assets`
- `GET /favicon.svg`（文件存在才挂）
- `POST /api/shell-boot`：把 body 前 4000 字节写到 `/tmp/loop-shell-boot.log`，返回 `{"ok": true}`

`LOOP_SHELL` 不是 `1` 或没有 `LOOP_STATIC_DIR` 时，`mount_shell_frontend` 什么都不挂。开发进程保持纯 API，前端仍由 Vite 提供。

## 首次向导

用户数据里还没有工作区时，窗口先走 `SetupWizard`，不盖在主界面上。顺序：填一个模型（Base URL、API Key、Model ID，可从带地址的预置填入），再选已有文件夹或在当前位置新建。新建只建子文件夹。点「使用此文件夹」才绑定。只有一份空档案时会补全并激活。相对父路径的新建会被拒绝，避免落到进程当前目录。已经绑了工作区的开发服务不出现这一步。

密钥进 `model_profiles.json`。公开接口只给 `api_key_configured`。壳进程不把密钥写进 `backend/.env`，也不写进本地图。

## 安装与编译

`loop install` → `install_shell_assets`。前置：仓库里已有 `dist/index.html`、`backend/.venv/pyvenv.cfg`、包源码。窗口二进制不是 ELF 时现场 `gcc`。细节与卸载守卫在 [`runtime-dirs.md`](runtime-dirs.md)。

装好之后从菜单点 Loop Agent，等价于绝对路径的 `loop shell`。

## 相关测试

`backend/tests/test_shell_session.py`、`test_shell_frontend.py`、`test_shell_python.py`。窗口像素与向导点击没有自动化测试；改 UI 用 `npx tsc -b` 再手点。本图不启动 8000 / 5173 / 8765。
