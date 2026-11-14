"""Асинхронный клиент LLM (OpenAI-совместимый API)."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import aiohttp

from app.core.config import settings


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


# Groq снял эти id. Запрос с ними отвечает 400 model_decommissioned,
# а репетитор молча подставляет заглушку «Сәләм».
_RETIRED_MODELS = {
    "llama3-8b-8192": "llama-3.3-70b-versatile",
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768": "llama-3.3-70b-versatile",
    "gemma-7b-it": "llama-3.3-70b-versatile",
    "gemma2-9b-it": "llama-3.1-8b-instant",
}
_FALLBACK_MODEL = "llama-3.3-70b-versatile"


def _message_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"Empty choices: {str(data)[:300]}")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning") or message.get("reasoning_content") or "").strip()
    if content:
        return content
    if reasoning:
        return reasoning
    raise LLMError(f"Empty message: {str(data)[:300]}")


class LLMClient:
    """Клиент к OpenAI-совместимому endpoint (Groq / FreeLLMAPI / Ollama)."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or settings.llm_api_key or "").strip()
        self.model = model or settings.llm_model
        self._session: aiohttp.ClientSession | None = None

    def resolved_model(self) -> str:
        model = (self.model or "").strip()
        if not model:
            return _FALLBACK_MODEL
        return _RETIRED_MODELS.get(model, model)

    def _is_reasoning_model(self, model: str) -> bool:
        return "gpt-oss" in model or model.startswith("o1") or model.startswith("o3")

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: float,
        use_completion_tokens: bool,
        drop_temperature: bool,
        drop_reasoning: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        reasoning = self._is_reasoning_model(model)
        if reasoning or use_completion_tokens:
            # У reasoning-моделей Groq ответ ест отдельные токены после рассуждения,
            # а max_tokens / temperature≠1 отклоняются с 400.
            payload["max_completion_tokens"] = max(max_tokens + 512, 768)
            if reasoning and not drop_reasoning:
                payload["reasoning_effort"] = "low"
            if not drop_temperature:
                payload["temperature"] = 1
        else:
            payload["max_tokens"] = max_tokens
            payload["top_p"] = top_p
            if not drop_temperature:
                payload["temperature"] = temperature
        return payload

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.llm_timeout)
            ssl_context = None
            try:
                import ssl

                import certifi

                ssl_context = ssl.create_default_context(cafile=certifi.where())
            except Exception:  # noqa: BLE001
                ssl_context = None
            connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        top_p: float = 1.0,
        retries: int = 2,
    ) -> str:
        if not self.api_key:
            raise LLMError("LLM API key is empty")

        model = self.resolved_model()
        use_completion_tokens = False
        drop_temperature = False
        drop_reasoning = False
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        last_error: Exception | None = None
        switched_model = False

        for attempt in range(retries + 2):
            payload = self._build_payload(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                use_completion_tokens=use_completion_tokens,
                drop_temperature=drop_temperature,
                drop_reasoning=drop_reasoning,
            )
            try:
                async with session.post(
                    settings.llm_api_base_url, json=payload, headers=headers
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        lowered = body.lower()
                        if resp.status in (429, 413):
                            raise RateLimitError(f"Rate limit: {body}")
                        if (
                            not switched_model
                            and (
                                "model_decommissioned" in lowered
                                or "model_not_found" in lowered
                                or "does not exist" in lowered
                                or "decommissioned" in lowered
                            )
                        ):
                            switched_model = True
                            model = _FALLBACK_MODEL
                            use_completion_tokens = False
                            drop_temperature = False
                            drop_reasoning = False
                            continue
                        if "reasoning_effort" in lowered and not drop_reasoning:
                            drop_reasoning = True
                            continue
                        if "max_completion_tokens" in lowered and not use_completion_tokens:
                            use_completion_tokens = True
                            continue
                        if "temperature" in lowered and not drop_temperature:
                            drop_temperature = True
                            continue
                        raise LLMError(f"API error {resp.status}: {body[:500]}")
                    data = await resp.json()
                    return _message_text(data)
            except RateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(1.2 * (attempt + 1))
        raise LLMError(str(last_error))

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ---------------------------------------------------------------------------
# Разбор ответа модели: метки вида "BA: ... / TR: ..."
# ---------------------------------------------------------------------------
HOMOGLYPHS = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y",
}
KEYS = ("BA", "TR", "CLARIFY", "PROPER")


def normalize_key(line: str) -> str:
    line = line.replace("\u00a0", " ").replace("\ufeff", "")
    idx = line.find(":")
    if idx <= 0:
        return line
    head = "".join(HOMOGLYPHS.get(ch, ch) for ch in line[:idx])
    return head + line[idx:]


def parse_fields(raw: str) -> dict[str, str]:
    """Разбирает ответ модели построчно. Устойчив к разделителю '/', markdown и NBSP."""
    fields: dict[str, str] = {}
    if not raw:
        return fields
    current: str | None = None
    lines: list[str] = []
    for line in raw.splitlines():
        line = normalize_key(line)
        # Поддерживаем "BA: ... / TR: ..." в одну строку и markdown-обёртки
        parts = re.split(r"\s*/\s*", line.strip())
        lines.extend(p.strip() for p in parts if p.strip())
    for line in lines:
        m = re.match(r"^[\s>*`#-]*\**\s*(" + "|".join(KEYS) + r")\s*\**\s*[:：]\s*(.*)$", line, re.I)
        if m:
            current = m.group(1).upper()
            fields[current] = m.group(2).strip()
            continue
        if current and line:
            fields[current] = (fields[current] + " " + line).strip()
    return fields


def parse_reply(raw: str) -> tuple[str, str, bool, str | None]:
    """(текст на башкирском, перевод, нужно ли уточнение, правильное написание)."""
    fields = parse_fields(raw)
    if fields.get("BA"):
        cl = (fields.get("CLARIFY") or "").strip().lower()
        clarify = cl in ("да", "yes", "true", "1")
        proper = (fields.get("PROPER") or "").strip() or None
        return fields["BA"].strip(), (fields.get("TR") or "").strip(), clarify, proper

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start:end + 1])
            return (
                (data.get("ba") or "").strip(),
                (data.get("translation") or "").strip(),
                bool(data.get("clarify")),
                data.get("proper") or None,
            )
        except Exception:  # noqa: BLE001
            pass
    return text.strip(), "", False, None
