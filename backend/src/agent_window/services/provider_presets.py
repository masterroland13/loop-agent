"""OpenAI-compatible gateway presets. Data only — no extra protocols.

Model ids are current vendor examples. ``kimi-k3`` is Moonshot's documented
Chat Completions id and also the blank router's default; the router card
inherits the active base URL instead of pinning Moonshot's.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ``inherit_base_url``: omit base_url on create so the new card copies the active gateway.
PROVIDER_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "router",
        "label": "OpenAI Compatible / Router",
        "base_url": "",
        "model_id": "kimi-k3",
        "inherit_base_url": True,
    },
    {
        "id": "moonshot",
        "label": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "model_id": "kimi-k3",
        "inherit_base_url": False,
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model_id": "deepseek-flash",
        "inherit_base_url": False,
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "openrouter/auto",
        "inherit_base_url": False,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model_id": "gpt-4o-mini",
        "inherit_base_url": False,
    },
    {
        "id": "groq",
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model_id": "openai/gpt-oss-120b",
        "inherit_base_url": False,
    },
    {
        "id": "together",
        "label": "Together",
        "base_url": "https://api.together.ai/v1",
        "model_id": "MiniMaxAI/MiniMax-M3",
        "inherit_base_url": False,
    },
    {
        "id": "siliconflow",
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model_id": "Qwen/Qwen2.5-7B-Instruct",
        "inherit_base_url": False,
    },
    {
        "id": "zhipu",
        "label": "Zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model_id": "glm-4-flash",
        "inherit_base_url": False,
    },
    {
        "id": "dashscope",
        "label": "DashScope / Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_id": "qwen-plus",
        "inherit_base_url": False,
    },
]


def list_provider_presets() -> List[Dict[str, Any]]:
    """Public preset rows. No API keys."""
    out: List[Dict[str, Any]] = []
    for row in PROVIDER_PRESETS:
        out.append(
            {
                "id": row["id"],
                "label": row["label"],
                "base_url": row["base_url"],
                "model_id": row["model_id"],
                "inherit_base_url": bool(row["inherit_base_url"]),
            }
        )
    return out
