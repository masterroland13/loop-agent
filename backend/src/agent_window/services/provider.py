import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import openai

from agent_window.services.reasoning import (
    completion_extra_body_for_reasoning,
    extract_reasoning_text,
    visible_text_content,
)
from agent_window.config import settings
from agent_window.services import model_registry as registry

logger = logging.getLogger(__name__)

# Set by the HTTP turn (and copied into the detached SSE task). Empty means active profile.
turn_profile_id: ContextVar[Optional[str]] = ContextVar("turn_profile_id", default=None)

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

    # Connection-level failures (DNS, TCP, TLS)
    if "connecttimeout" in lower.replace(" ", "") or "connect timeout" in lower:
        return "无法连接到 LLM 网关（连接超时）。请检查网络或更换 Base URL。"
    if "connection refused" in lower or "name or service not known" in lower or "nodename nor servname" in lower:
        return "无法连接到 LLM 网关（地址不可达）。请检查 Base URL 是否正确。"
    if "ssl" in lower and ("certificate" in lower or "handshake" in lower):
        return "LLM 网关 SSL 证书验证失败。请检查 Base URL 或网络代理。"

    # HTTP status codes
    if "401" in text or "invalid api key" in lower or "authentication" in lower or "unauthorized" in lower:
        return "LLM 鉴权失败，请检查 API Key 是否正确。"
    if "403" in text or "forbidden" in lower or "permission" in lower:
        return "LLM 权限不足（403）。请检查 API Key 权限或账户状态。"
    if "404" in text and "model" in lower:
        return "请求的模型不存在（404）。请在设置中检查模型 id。"
    if "429" in text or "rate limit" in lower or "too many" in lower:
        return "请求过于频繁（429），请稍后再试。"
    if "500" in text or "internal server" in lower:
        return "LLM 网关内部错误（500），请稍后重试。"
    if "502" in text or "bad gateway" in lower or "503" in text or "service unavailable" in lower:
        return "LLM 网关暂时不可用（502/503），请稍后重试。"

    # Model-level errors
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
                model_hint = token.rstrip(".,")
                break
        if model_hint:
            return (
                f"模型「{model_hint}」当前不可用（网关未配置该别名）。"
                "请在模型列表中另选一个再试。"
            )
        return "当前模型不可用（网关未配置该别名）。请换一个模型再试。"

    # Timeout (read/write, not connect)
    if "timeout" in lower or "timed out" in lower:
        return "上游模型响应超时，请重试。"

    # Context/token limits
    if "context_length" in lower or "maximum context" in lower or "too many tokens" in lower:
        return "对话上下文超出模型限制。请新开一个会话重试。"

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
        # profile_id -> (base_url, api_key, client). Not the process-global active client.
        self._profile_clients: Dict[str, Tuple[str, str, Any]] = {}

    def _default_model(self) -> str:
        handle = registry.resolve_active_handle()
        if handle and handle.model_id:
            return handle.model_id
        return settings.llm_model

    def _generation_defaults(self) -> Dict[str, Any]:
        g = registry.get_globals()
        return {
            "temperature": g.get("temperature", settings.llm_temperature),
            "max_tokens": g.get("max_tokens", settings.llm_max_tokens),
        }

    def _sync_client(self) -> None:
        """Load credentials from the active enabled Model Registry profile.

        Settings test / model list only. A turn must use ``_client_for_profile``
        so two sessions do not swap this singleton.
        """
        creds = registry.resolve_credentials()
        key = str(creds.get("api_key") or "").strip()
        url = (creds.get("base_url") or "").strip().rstrip("/")
        if self.client is not None and url == self.base_url and key == self.api_key:
            return
        self.base_url = url
        self.api_key = key
        self.client = openai.AsyncOpenAI(api_key=key, base_url=url) if key else None

    def _client_for_profile(self, profile_id: Optional[str] = None) -> Tuple[Any, str]:
        """Return (client, default model id) for one profile. Does not write settings.llm_*."""
        bound = profile_id if profile_id is not None else turn_profile_id.get()
        creds = registry.resolve_credentials(bound or None)
        pid = str(creds.get("profile_id") or "")
        key = str(creds.get("api_key") or "").strip()
        url = (creds.get("base_url") or "").strip().rstrip("/")
        default_model = str(creds.get("model_id") or "") or self._default_model()
        if not pid or not key:
            return None, default_model
        cached = self._profile_clients.get(pid)
        if cached and cached[0] == url and cached[1] == key:
            return cached[2], default_model
        client = openai.AsyncOpenAI(api_key=key, base_url=url)
        self._profile_clients[pid] = (url, key, client)
        return client, default_model

    def profile_is_ready(self, profile_id: Optional[str] = None) -> bool:
        """True when that profile has a URL and a key. Does not touch settings or the active client."""
        creds = registry.resolve_credentials(profile_id or None)
        return bool(str(creds.get("api_key") or "").strip()) and bool(str(creds.get("base_url") or "").strip())

    def is_available(self) -> bool:
        """Active profile only. Turn gates use ``profile_is_ready``."""
        self._sync_client()
        return self.client is not None and bool(self.api_key)

    async def list_models(self) -> Dict[str, Any]:
        """Return {models: [{id}], default, source}."""
        self._sync_client()
        default = self._default_model()
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

    async def test_profile(self, profile_id: str) -> Dict[str, Any]:
        """Ping a specific profile with a temporary client (list models)."""
        profile = registry.get_profile(profile_id)
        if profile is None:
            return {"ok": False, "error": "档案不存在"}
        key = str(profile.get("api_key") or "").strip()
        url = (profile.get("base_url") or "").strip().rstrip("/")
        if not key:
            return {"ok": False, "error": "未配置 API Key"}
        if not url:
            return {"ok": False, "error": "未配置 Base URL"}
        client = openai.AsyncOpenAI(api_key=key, base_url=url)
        try:
            page = await client.models.list()
            count = len([i for i in (page.data or []) if getattr(i, "id", None)])
            if count == 0:
                return {"ok": False, "error": "网关未返回模型列表", "model_count": 0}
            return {"ok": True, "model_count": count}
        except Exception as e:
            return {"ok": False, "error": humanize_provider_error(e)[:200]}

    async def chat_complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        profile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Non-streaming completion; returns content + optional tool_calls."""
        client, default_model = self._client_for_profile(profile_id)
        if not client:
            raise RuntimeError("LLM provider not configured")

        gens = self._generation_defaults()
        payload: Dict[str, Any] = {
            "model": model or default_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else gens["temperature"],
            "max_tokens": max_tokens or gens["max_tokens"],
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Thought is always-on when the gateway returns reasoning; no Settings toggle.
        extra = completion_extra_body_for_reasoning(
            supports_reasoning=True,
            reasoning_mode="openai_compatible",
        )
        if extra:
            payload["extra_body"] = {**(payload.get("extra_body") or {}), **extra}

        logger.info(
            "chat_complete: model=%s msgs=%s tools=%s reasoning=%s",
            payload["model"],
            len(messages),
            len(tools) if tools else 0,
            True,
        )
        t0 = time.perf_counter()
        try:
            response = await client.chat.completions.create(**payload)
        except Exception as e:
            if self._is_tools_schema_error(e) and tools:
                logger.warning("tools rejected by provider; retrying without tools for model=%s", model or default_model)
                try:
                    retry_payload = {**payload, "tools": None, "tool_choice": None}
                    response = await client.chat.completions.create(**retry_payload)
                except Exception as e2:
                    raise RuntimeError(humanize_provider_error(e2)) from e2
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return self._normalize_completion(
                    response.choices[0],
                    elapsed_ms=elapsed_ms,
                    tools_fallback=True,
                    tools_fallback_reason=humanize_provider_error(e),
                )
            raise RuntimeError(humanize_provider_error(e)) from e

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return self._normalize_completion(
            response.choices[0],
            elapsed_ms=elapsed_ms,
            tools_fallback=False,
        )

    def _normalize_completion(
        self,
        choice: Any,
        *,
        elapsed_ms: int,
        tools_fallback: bool,
        tools_fallback_reason: str = "",
    ) -> Dict[str, Any]:
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

        reasoning_text, reasoning_source = extract_reasoning_text(message)
        content = visible_text_content(message)
        if not content and isinstance(getattr(message, "content", None), str):
            content = message.content or ""

        out: Dict[str, Any] = {
            "content": content or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "tools_fallback": tools_fallback,
            "reasoning_content": reasoning_text,
            "reasoning_source": reasoning_source if reasoning_text else "none",
            "reasoning_duration_ms": elapsed_ms if reasoning_text else None,
        }
        if tools_fallback:
            out["tools_fallback_reason"] = tools_fallback_reason
        return out

    @staticmethod
    def _is_tools_schema_error(exc: BaseException) -> bool:
        text = str(exc).lower()
        return "tools.function.parameters" in text or "json schema" in text or "moonshot" in text

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[Dict]:
        client, default_model = self._client_for_profile(None)
        if not client:
            logger.error("LLM provider not configured")
            yield {
                "type": "error",
                "code": "PROVIDER_NOT_CONFIGURED",
                "message": "LLM provider not configured",
            }
            return

        gens = self._generation_defaults()
        payload = {
            "model": request.model or default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature if request.temperature is not None else gens["temperature"],
            "max_tokens": request.max_tokens or gens["max_tokens"],
            "stream": True,
        }

        logger.info("Sending LLM request with %s messages", len(request.messages))

        try:
            response = await client.chat.completions.create(**payload)
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
