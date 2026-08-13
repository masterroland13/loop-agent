# Hal Agent

可运行的 Hal Agent 对话窗口：左侧工作区/会话管理，中间问答流，右侧收藏与导航。  
前端 React + Vite；后端 FastAPI + SQLite + LiteLLM（OpenAI 兼容）。

## 目录结构

```
hal-agent/
├── README.md                 # 项目说明（本文件）
├── package.json              # 前端依赖与 npm scripts
├── package-lock.json         # 依赖锁定版本
├── index.html                # Vite 入口 HTML（须在仓库根）
├── vite.config.ts            # Vite / Tailwind / API 代理（须在仓库根）
├── tsconfig.json             # TypeScript 工程引用入口（须在仓库根）
├── .gitignore
│
├── config/                   # 前端工程配置（可集中的配置）
│   ├── tsconfig.app.json     # 应用源码 TS 配置
│   ├── tsconfig.node.json    # Vite 配置文件 TS 配置
│   └── oxlint.json           # Oxlint 规则
│
├── public/                   # 静态资源（不经打包变换）
├── src/                      # 前端源码
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   ├── components/
│   ├── hooks/
│   ├── types/
│   ├── utils/
│   └── styles/
│
├── backend/                  # 后端 FastAPI
├── docs/                     # 产品/架构文档
│   ├── agent-window-roadmap.md
│   └── v1-7-headless-cli-design.md
├── scripts/                  # 运维、冒烟与调试脚本（见 scripts/README.md）
│   ├── start-dev.sh
│   ├── preview-server.mjs
│   ├── rebuild-preview.sh
│   ├── restart-uvicorn.sh
│   ├── build-frontend.sh
│   ├── smoke/
│   └── debug/
├── logs/                     # 运行日志（内容 gitignore，仅保留目录）
├── dist/                     # 前端构建产物（gitignore）
└── node_modules/             # 前端依赖（gitignore）
```



## 根目录文件分别干什么？


| 文件                                   | 作用                        | 能否挪进子目录              |
| ------------------------------------ | ------------------------- | -------------------- |
| `package.json` / `package-lock.json` | npm 项目清单与锁文件              | **否**（工具默认读根目录）      |
| `index.html`                         | 浏览器入口，Vite 默认从根找          | **否**                |
| `vite.config.ts`                     | 开发服务器、插件、`/api` 代理        | **否**（Vite 默认根配置）    |
| `tsconfig.json`                      | TS project references 总入口 | **否**（`tsc -b` 默认读根） |
| `README.md` / `.gitignore`           | 说明与忽略规则                   | **否**（惯例在根）          |
| `tsconfig.app.json` ~~等~~            | 已迁到 `config/`             | 已整理                  |
| `.oxlintrc.json`                     | 已迁到 `config/oxlint.json`  | 已整理                  |
| `vite.log` ~~/~~ `viteproxy.log`     | 运行日志                      | 已归到 `logs/`（并忽略）     |




## 分类说明


| 类别      | 位置                | 职责                 |
| ------- | ----------------- | ------------------ |
| 工程配置    | `config/`         | TS 子配置、lint 规则     |
| 页面组装    | `src/App.tsx`     | hooks 与组件拼装        |
| UI 组件   | `src/components/` | 展示与本地交互            |
| 状态钩子    | `src/hooks/`      | 会话、消息、收藏、工作区、设置、主题 |
| API 客户端 | `src/api/`        | REST / SSE         |
| 样式      | `src/styles/`     | 设计 token、全局 CSS    |
| 文档      | `docs/`           | 路线图等               |
| 脚本      | `scripts/`        | 启动、预览、重建、冒烟、调试 |
| 日志      | `logs/`           | 本地运行日志             |
| 后端      | `backend/`        | FastAPI + LLM + 存储 |




## 快速启动



### 后端（WSL）

```bash
cd backend
# 首次：在 .env 配置 LiteLLM 密钥（BASE_URL 已指向 https://llm-cn.gameye.ai/v1）
uv run uvicorn agent_window.main:app --host 0.0.0.0 --port 8000
```

或：

```bash
./scripts/start-dev.sh
```



### 前端（推荐开发模式）

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

浏览器打开 [http://localhost:5173/](http://localhost:5173/)

### 前端（预览构建产物）

```bash
npm run build
npm run preview
```



## 主要 API

- `GET /health`
- `GET|POST /api/sessions`
- `PATCH|DELETE /api/sessions/{id}`
- `GET|POST /api/sessions/{id}/messages`（POST 为 SSE）
- `GET /api/favorites`
- `PATCH /api/messages/{id}/favorite`

