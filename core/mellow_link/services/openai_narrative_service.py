"""
OpenAI narrative service adapter.

This service is used for optional single-shot narrative enhancement without
requiring Azure deployment names.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any

try:
    from openai import AsyncOpenAI
except Exception as exc:  # pragma: no cover - import failure depends on environment
    AsyncOpenAI = None
    _OPENAI_IMPORT_ERROR = exc
else:
    _OPENAI_IMPORT_ERROR = None

logger = logging.getLogger(__name__)


@dataclass
class OpenAIGenerationResult:
    content: str
    model: str


class OpenAINarrativeLLMService:
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        *,
        api_key: str,
        models: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._timeout = float(timeout or self.DEFAULT_TIMEOUT)
        self._models = {
            "fast": "",
            "thinking": "",
            "research": "",
        }
        if models:
            for key, value in models.items():
                normalized_key = str(key or "").strip().lower()
                if normalized_key in self._models:
                    self._models[normalized_key] = str(value or "").strip()

        fallback_model = next((value for value in self._models.values() if value), "")
        if fallback_model:
            for key, value in list(self._models.items()):
                if not value:
                    self._models[key] = fallback_model

        self._client: AsyncOpenAI | None = None
        self._connected = False

    async def connect(self) -> bool:
        if AsyncOpenAI is None:
            logger.warning("[OpenAINarrativeLLMService] openai SDK unavailable: %s", _OPENAI_IMPORT_ERROR)
            self._connected = False
            return False
        if not self._is_configured():
            logger.info("[OpenAINarrativeLLMService] Narrative OpenAI config incomplete; service disabled")
            self._connected = False
            return False

        self._client = AsyncOpenAI(api_key=self._api_key)
        self._connected = True
        return True

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        self._connected = False
        if client is None:
            return

        closer = getattr(client, "close", None) or getattr(client, "aclose", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

    async def unload_all_models(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._connected and self._client is not None)

    def get_model_for_mode(self, mode: str) -> str:
        requested_mode = str(mode or "").strip().lower()
        if requested_mode == "thinking-lite":
            requested_mode = "thinking"
        if requested_mode == "auto":
            requested_mode = "fast"
        return (
            self._models.get(requested_mode)
            or self._models.get("thinking")
            or self._models.get("fast")
            or self._models.get("research")
            or ""
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        mode: str = "fast",
        context_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        auto_unload: bool = True,
        **kwargs: Any,
    ) -> OpenAIGenerationResult:
        del context_id, auto_unload
        if not self.is_available():
            connected = await self.connect()
            if not connected or self._client is None:
                raise RuntimeError("OpenAINarrativeLLMService not connected")

        model = self.get_model_for_mode(mode)
        if not model:
            raise RuntimeError("OpenAINarrativeLLMService model not configured")

        messages: list[dict[str, Any]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_timeout = kwargs.pop("request_timeout_seconds", None)
        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", 0.1),
            "max_tokens": kwargs.pop("max_tokens", 1200),
            "timeout": float(request_timeout or self._timeout),
        }
        top_p = kwargs.pop("top_p", None)
        if top_p is not None:
            request_kwargs["top_p"] = top_p
        if tools:
            request_kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message if response.choices else None
        content = self._extract_message_content(getattr(message, "content", ""))
        response_model = str(getattr(response, "model", "") or "").strip() or model
        return OpenAIGenerationResult(content=content, model=response_model)

    def _is_configured(self) -> bool:
        return bool(self._api_key and any(str(value or "").strip() for value in self._models.values()))

    def _extract_message_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text = item
                elif isinstance(item, dict):
                    text = str(item.get("text") or "")
                else:
                    text = str(getattr(item, "text", "") or "")
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        return str(content or "").strip()


def create_openai_narrative_service(
    *,
    api_key: str,
    models: dict[str, str] | None = None,
    timeout: float = OpenAINarrativeLLMService.DEFAULT_TIMEOUT,
) -> OpenAINarrativeLLMService:
    return OpenAINarrativeLLMService(
        api_key=api_key,
        models=models,
        timeout=timeout,
    )
