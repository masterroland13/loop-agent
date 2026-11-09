# 包装差距文与 `loop shell` 的文档债

> L3 调研。只记录债务和改写提案。  
> **本次不改** [`../app-packaging-gap.md`](../app-packaging-gap.md)，也不改产品代码。  
> 冲突序：宪章 > 路线图 > [`foundation-status.md`](../../foundation-status.md) > 这篇调研。调研落后于真源时，以宪章 §1.4 为准。

## 冲突

[`app-packaging-gap.md`](../app-packaging-gap.md) 仍把桌面壳的首选写成 **Electron 或 Tauri**（开窗启后端、关窗停，加载打包前端或 localhost），并把「壳与进程、安装向导、Files 等人机面」列成同事可装版本还缺的东西。文末仍按「壳 + Files + 向导」估内测安装包约 1～2 月。

仓库里已经落地的桌面路径是 **`loop shell`**，窗口程序是 `shell/loop-window.c`（GTK + WebKitGTK，`webkit2gtk-4.1`）。`loop install` 把界面、`loop-window` 和一份后端虚拟环境放进 `~/.local/lib/loop-agent`，写入 `~/.local/bin/loop` 和桌面启动项。这条路径不引入 Electron，也不引入 Tauri。

真源（都已写成 `loop shell` / WebKitGTK）：

| 位置 | 写了什么 |
|------|----------|
| 宪章 §1.4 | 安装目录 / 用户数据 / 工作区；桌面入口是 `loop shell`，关窗停后端 |
| [`layer-boundaries.md`](../../layer-boundaries.md) | `loop shell` 与浏览器、CLI 并列，不进 `agent/` 环；源码 `shell/loop-window.c` |
| [`foundation-status.md`](../../foundation-status.md) 2026-10-23 | 桌面壳、安装目录、首次向导、桌面启动项、卸载留数据；安装窗口手测通过 |
| 根 README / `README.zh-CN.md` | Linux / WSL 上的 WebKitGTK；`loop install` / `loop shell` / `loop uninstall` |
| [`loop-agent-manual.md`](../../design/loop-agent-manual.md) | 可选桌面壳（WebKitGTK），端口 8765 |
| CHANGELOG `[Unreleased]` | 桌面壳、安装目录、首次向导三条已记实现 |

`app-packaging-gap.md` 与 Files MVP 同一批进库（进度表 2026-09-12）。桌面壳在 2026-10-23 落地之后，这篇调研没有改口。

## 原文哪里过时

| 原文 | 问题 | 应对 |
|------|------|------|
| 「现状是本机双进程 Web……不是安装包」 | 开发服务仍是 uvicorn + Vite。同事路径已经是 `loop install` + `loop shell`，只是还不是商店安装包 | 拆成「开发双进程」和「已有的用户目录安装」两句 |
| 封装表首选「Electron 或 Tauri」 | 与宪章和已装上的窗口程序冲突。再按这行开工会多加一层运行时 | 首选改为 `loop shell`（WebKitGTK）。Electron、Tauri 写成不采用 |
| 「封装还须：数据目录、首次向导」 | 两件都已在 §1.4 和向导里 | 改成「已有」，只把更新与签名留在未做 |
| 差距 2「缺：壳与进程、安装向导、Files」 | 壳、向导、Files 人机面已进树 | 从「缺」里拿掉。日志、升级、平台签名仍缺 |
| 建议顺序 1～3（Files、一键启停、向导） | 这三步已完成 | 顺序只保留签名、升级，以及脱离 git 检出的安装方式 |
| 「内测安装包量级约 1～2 月（壳 + Files + 向导）」 | 工期前提已经消失。不要再引用这个月数 | 删掉日历估计 |

开发者用浏览器打开 5173、CLI 继续做自动化，这两句仍然对。Docker 不适合「绑本机文件夹改代码」、纯 PWA 带不了本机后端，也仍然对。Cursor 级 Terminal / Browser / 多 Agent / 云仍不要和「本机窗口能开」放进同一个里程碑。

## 仍然成立的差距

这些没有被 `loop shell` 做完，改写时要留下：

1. **安装仍从 git 检出跑。** 需要 `dist/index.html`、`backend/.venv`，以及 Linux 可执行文件 `shell/loop-window`。二进制缺失或比 `shell/loop-window.c` 旧时，用 `gcc` 和 `pkg-config`（`webkit2gtk-4.1`）编译。已经放在 `~/.local` 下的 `loop` 会拒绝再次 `install`。
2. **壳只覆盖 Linux / WSL。** 窗口依赖 WebKitGTK。没有 Windows / macOS 壳，也没有双击安装包。
3. **没有代码签名，没有自动更新。** 升级要回到仓库再装。原文里的「日志」没有对应的已落地条目，改写时不要把它写成已完成。
4. **密钥仍不在系统钥匙串。** 那是 [`api-key-storage.md`](../api-key-storage.md) 的题，不塞进包装文的「再选一次壳」。

## 改写提案

下面整段用来替换 `app-packaging-gap.md` 的正文。本次 PR **不写入那个文件**。套用时保留原路径和 H1，只换掉过时论断。

````markdown
# 桌面 App 封装与差距（调研）

> L3 research。开发时是本机双进程 Web（Vite + FastAPI）。同事路径是 `loop install` + `loop shell`，还不是商店安装包。
>
> 桌面壳以宪章 §1.4 为准：WebKitGTK 上的 `loop shell`。不采用 Electron，也不采用 Tauri。

## 现状

- 开发：`uvicorn`（8000）+ Vite（5173），浏览器访问。`backend/.env` 里 `APP_DATA_DIR=./data` 仍用仓库狗粮库。
- 安装：`loop install` 从 git 检出拷入界面、`shell/loop-window` 和后端虚拟环境，落到 `~/.local/lib/loop-agent`；命令行入口 `~/.local/bin/loop`；桌面项 `~/.local/share/applications/loop-agent.desktop`。
- 桌面：`loop shell` 用安装目录里的环境开窗，页面由同一后端在 **8765** 托管，数据目录 `~/.local/share/loop-agent`。关窗停掉它拉起的后端。8765 已被占用时不开第二份。这个进程不读 `backend/.env`。
- 窗口程序是 `shell/loop-window.c`（GTK + WebKitGTK）。产品路径不引入 Electron，也不引入 Tauri。
- 还没有工作区时，窗口里的向导先收集模型，再选或新建文件夹。
- `loop uninstall` 只删程序文件，留下用户数据和工作区。
- CLI `loop` 仍是自动化通道。默认打 8000；要打桌面那份后端时把地址指到 8765。
- Files 人机面已有（list / read / write + 面板）。

## 封装路径

| 路线 | 说明 |
|------|------|
| **`loop shell`（已选）** | WebKitGTK 窗口。开窗启后端、关窗停。页面由安装目录里的后端托管 |
| Electron | 不采用。多一层运行时，和已落地的薄壳重复 |
| Tauri | 不采用。理由同上 |
| 安装器 + 系统浏览器 | 体验弱，端口和依赖容易撞车 |
| Docker | 适合服务端；不适合「绑本机文件夹改代码」主路径 |
| 纯 PWA | 没有本机后端就做不了 workspace |

运行时三个目录（宪章 §1.4）已经分开：安装目录、用户数据目录、工作区。会话库和密钥不进安装树。

## 差距分层

1. **本机狗粮可用** — 环、门控、压缩、记忆、Files、向导、`loop shell` 手测已通过。
2. **同事可装的桌面 App** — 已有壳、进程、向导、Files、卸载留数据。仍缺：脱离 git 检出的安装包、升级、平台签名。壳只覆盖 Linux / WSL（WebKitGTK）。
3. **Cursor 级完整表面** — Terminal / Browser / 多 Agent / 云。不要和「本机窗口能开」放进同一个里程碑。

## 建议顺序

1. 让安装不依赖这份 git 检出（依赖、`webkit2gtk`、已安装副本拒绝再装，都要有明确的同事路径）
2. 升级：已安装的 `loop` 怎样换成新构建，而不是只能回到仓库再跑 `install`
3. 签名
4. 若要离开 Linux / WSL，单独立项；默认壳仍是 `loop shell`，不改回 Electron 或 Tauri

CLI 保留为自动化通道，不替代桌面壳。

## 不要再引用的工期

「壳 + Files + 向导约 1～2 月」写于这三项落地之前（进度表：调研 2026-09-12，壳与向导 2026-10-23）。这句作废，不要再拿它排期。
````

## 旁注（本稿不改）

[`plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md) 的范围表仍把「Electron」和签名放在同一格「桌面壳后置清单」。签名仍可后置。Electron 已经不是后置方案。那是 L2 计划里的一句旧词，等改包装文时一并改掉，避免两处继续互相引用。

[`context-loop-c0-c5-review.md`](../context-loop-c0-c5-review.md) 写「不做 Electron」，和简历段里的 WebKitGTK 一致，不是这篇债务。

## 本次不做

- 不改 `app-packaging-gap.md` 原文。
- 不改 `shell/`、`loop install`、前端或打包脚本。
- 不新开 Electron / Tauri 方案，也不把 WebKitGTK 换成别的壳。
