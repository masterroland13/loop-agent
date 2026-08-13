# Agent Window Backend

Python + FastAPI 后端：会话、消息流式回复、收藏持久化。

## 目录

```
src/agent_window/
├── main.py          # 应用入口（CORS、挂载路由、启动 init_db）
├── config.py        # Settings / .env
├── models.py        # SQLAlchemy：Session / Message
├── schemas.py       # Pydantic 请求与响应
├── api/
│   └── routes.py    # REST + SSE 路由
└── services/
    ├── provider.py  # LLM（Kimi / OpenAI SDK）
    └── storage.py   # SQLite + Markdown 文件读写
```

## 启动

```bash
cd backend
uv run uvicorn agent_window.main:app --host 0.0.0.0 --port 8000
```

在 `backend/.env` 配置（LiteLLM 统一入口）：

```
APP_DATA_DIR=./data
LLM_PROVIDER=litellm
LLM_BASE_URL=https://llm-cn.gameye.ai/v1
LLM_API_KEY=sk-...
LLM_MODEL=kimi-for-coding
```

`LLM_MODEL` 需与 LiteLLM 网关上配置的模型别名一致。