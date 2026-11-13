import os
import json
import aiohttp
from dotenv import load_dotenv

# Загружаем .env из backend/
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3-8b-8192")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


class LLMClient:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or LLM_API_KEY
        self.model = model or LLM_MODEL
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def chat_completion(self, messages: list[dict], temperature: float = 0.7,
                             max_tokens: int = 512, top_p: float = 1.0) -> str:
        session = await self._get_session()
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
        async with session.post(API_BASE_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                if resp.status in [429, 413, 404]:
                    raise RateLimitError(f"Rate limit: {text}")
                raise LLMError(f"API error {resp.status}: {text}")
            data = await resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMError(f"Empty choices: {str(data)[:300]}")
            content = (choices[0].get("message") or {}).get("content") or ""
            return content.strip()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()