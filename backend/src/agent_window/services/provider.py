import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import openai

from agent_window.config import settings

logger = logging.getLogger(__name__)

# Used when /models is unreachable; must be aliases that exist on the gateway.
FALLBACK_MODELS = [
  "kimi-k3",
  "kimi-k3-256k",
  "kimi-for-coding",
  "kimi-for-coding-highspeed",
  "bailian-kimi-k2.7-code",
]


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True


def humanize_provider_error(exc: BaseException) -> str:
    """Map common LiteLLM/OpenAI errors to short Chinese hints."""
    text = str(exc)
    lower = text.lower()
    if "invalid model name" in lower or "model_not_found" in lower:
        model_hint = ""
        for token in text.replace("=", " ").replace("'", " ").replace('"', " ").split():
            if (
                token.startswith("kimi")
                or token.startswith("bailian")
                or token.startswith("yz-")
                or token.startswith("openrouter")
                or token.startswith("deepseek")
            ):
                model_hint = token.rstrip(".,;")
                break
        if model_hint:
            return (
                f"模型「{model_hint}」当前不可用（网关未配置该别名）。"
                "请在模型列表中另选一个再试。"
            )
        return "当前模型不可用（网关未配置该别名）。请换一个模型再试。"
    if "401" in text or "invalid api key" in lower or "authentication" in lower:
        return "LLM 鉴权失败，请检查后端 LLM_API_KEY。"
    if "429" in text or "rate limit" in lower:
        return "请求过于频繁，请稍后再试。"
    if "timeout" in lower or "timed out" in lower:
        return "上游模型超时，请重试。"
    return text


class LLMProvider:
    def __init__(
        self,
        provider: str = settings.llm_provider,
        api_key: str = settings.llm_api_key,
        base_url: str = settings.llm_base_url,
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url) if api_key else None

    def _sync_client(self) -> None:
        key = str(settings.llm_api_key or "").strip()
        url = (settings.llm_base_url or "").strip().rstrip("/")
        if self.client is not None and url == self.base_url and key == self.api_key:
            return
        self.base_url = url
        self.api_key = key
        self.client = openai.AsyncOpenAI(api_key=key, base_url=url) if key else None

    def is_available(self) -> bool:
        self._sync_client()
        return self.client is not None and bool(self.api_key)

    async def list_models(self) -> Dict[str, Any]:
        """Return {models: [{id}], default, source}."""
        self._sync_client()
        default = settings.llm_model
        if not self.client:
            ids = list(FALLBACK_MODELS)
            if default not in ids:
                ids = [default] + ids
            return {
                "models": [{"id": m} for m in ids],
                "default": default,
                "source": "fallback",
            }
        try:
            page = await self.client.models.list()
            ids = sorted({item.id for item in (page.data or []) if getattr(item, "id", None)})
            if not ids:
                raise RuntimeError("empty model list")
            if default not in ids:
                ids = [default] + [i for i in ids if i != default]
            return {
                "models": [{"id": mid} for mid in ids],
                "default": default,
                "source": "provider",
            }
        except Exception:
            logger.exception("list_models failed; using fallback")
            ids = list(FALLBACK_MODELS)
            if default not in ids:
                ids = [default] + ids
            return {
                "models": [{"id": m} for m in ids],
                "default": default,
                "source": "fallback",
            }

    async def chat_complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Non-streaming completion; returns content + optional tool_calls."""
        self._sync_client()
        if not self.client:
            raise RuntimeError("LLM provider not configured")

        payload: Dict[str, Any] = {
            "model": model or settings.llm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(
            "chat_complete: model=%s msgs=%s tools=%s",
            payload["model"],
            len(messages),
            len(tools) if tools else 0,
        )
        try:
            response = await self.client.chat.completions.create(**payload)
        except Exception as e:
            if self._is_tools_schema_error(e) and tools:
                logger.warning("tools rejected by provider; retrying without tools for model=%s", model or settings.llm_model)
                try:
                    response = await self.client.chat.completions.create(**{**payload, "tools": None, "tool_choice": None})
                except Exception as e2:
                    raise RuntimeError(humanize_provider_error(e2)) from e2
                choice = response.choices[0]
                message = choice.message
                return {
                    "content": message.content or "",
                    "tool_calls": [],
                    "finish_reason": choice.finish_reason,
                    "tools_fallback": True,
                    "tools_fallback_reason": humanize_provider_error(e),
                }
            raise RuntimeError(humanize_provider_error(e)) from e

        choice = response.choices[0]
        message = choice.message

        tool_calls: List[Dict[str, Any]] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    }
                )

        return {
            "content": message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "tools_fallback": False,
        }

    @staticmethod
    def _is_tools_schema_error(exc: BaseException) -> bool:
        text = str(exc).lower()
        return "tools.function.parameters" in text or "json schema" in text or "moonshot" in text

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[Dict]:
        self._sync_client()
        if not self.client:
            logger.error("LLM provider not configured")
            yield {
                "type": "error",
                "code": "PROVIDER_NOT_CONFIGURED",
                "message": "LLM provider not configured",
            }
            return

        payload = {
            "model": request.model or settings.llm_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature or settings.llm_temperature,
            "max_tokens": request.max_tokens or settings.llm_max_tokens,
            "stream": True,
        }

        logger.info("Sending LLM request with %s messages", len(request.messages))

        try:
            response = await self.client.chat.completions.create(**payload)
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield {"type": "token", "content": delta.content}
        except Exception as e:
            logger.exception("LLM provider error: %s", e)
            yield {
                "type": "error",
                "code": "LLM_PROVIDER_ERROR",
                "message": humanize_provider_error(e),
            }
            return

        logger.info("LLM request completed")
        yield {"type": "done"}


provider = LLMProvider()
