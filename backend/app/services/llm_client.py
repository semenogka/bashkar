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


class LLMClient:
    """Клиент к OpenAI-совместимому endpoint (Groq / FreeLLMAPI / Ollama)."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.llm_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
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
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                async with session.post(
                    settings.llm_api_base_url, json=payload, headers=headers
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        if resp.status in (429, 413):
                            raise RateLimitError(f"Rate limit: {body}")
                        raise LLMError(f"API error {resp.status}: {body}")
                    data = await resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise LLMError(f"Empty choices: {str(data)[:300]}")
                    content = (choices[0].get("message") or {}).get("content") or ""
                    return content.strip()
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
