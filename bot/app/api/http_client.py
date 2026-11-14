
"""HTTP-клиент для работы с API платформы."""
from typing import Any

import httpx

from app.api.interfaces import PlatformClient
from app.config import settings


class HttpPlatformClient(PlatformClient):
    def __init__(self):
        if not settings.PLATFORM_API_URL:
            raise ValueError("Не задан PLATFORM_API_URL в файле .env")

        self.base_url = settings.PLATFORM_API_URL.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=15.0,
        )

        # Связь Telegram ID с внутренним ID пользователя платформы.
        self.user_ids: dict[int, int] = {}

    async def close(self):
        await self.client.aclose()

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str,
    ) -> dict[str, Any]:
        response = await self.client.post(
            "/users",
            json={
                "external_id": str(telegram_id),
                "name": first_name,
                "username": username,
                "role": "student",
            },
        )
        response.raise_for_status()

        user = response.json()
        self.user_ids[telegram_id] = user["id"]

        return {
            "success": True,
            "is_new": None,
            "user": user,
        }

    def _get_internal_id(self, telegram_id: int) -> int:
        user_id = self.user_ids.get(telegram_id)

        if user_id is None:
            raise ValueError(
                "Пользователь не найден. Сначала отправьте команду /start."
            )

        return user_id

    async def get_user_profile(self, telegram_id: int) -> dict[str, Any]:
        user_id = self._get_internal_id(telegram_id)

        response = await self.client.get(f"/users/{user_id}")
        response.raise_for_status()

        return response.json()

    async def get_user_rating(self, telegram_id: int) -> dict[str, Any]:
        user_id = self._get_internal_id(telegram_id)

        response = await self.client.get(
            "/leaderboard/users",
            params={"limit": 1000},
        )
        response.raise_for_status()

        data = response.json()

        # Поддерживаем как список, так и объект со списком.
        users = data if isinstance(data, list) else data.get("users", [])

        for index, user in enumerate(users, start=1):
            if user.get("user_id") == user_id:
                return {
                    "position": user.get("rank", index),
                    "points": user.get("xp", 0),
                }

        return {"position": None, "points": 0}

    async def get_leaderboard(self, telegram_id: int, period: str = "day") -> dict[str, Any]:
        user_id = self._get_internal_id(telegram_id)
        period = period if period in {"day", "month", "year"} else "day"
        response = await self.client.get(
            "/leaderboard/users",
            params={"limit": 10, "period": period},
        )
        response.raise_for_status()
        data = response.json()
        users = data if isinstance(data, list) else data.get("users", [])
        top = [{"name": row.get("name") or "Ученик", "xp": row.get("xp", 0)} for row in users]
        position = None
        points = 0
        for row in users:
            if row.get("user_id") == user_id:
                position = row.get("rank")
                points = row.get("xp", 0)
        return {
            "period": period,
            "top": top,
            "position": position,
            "points": points,
            "class_rank": None,
            "school_rank": None,
        }

    async def get_user_statistics(self, telegram_id: int) -> dict[str, Any]:
        user_id = self._get_internal_id(telegram_id)

        response = await self.client.get(f"/stats/me/{user_id}")
        response.raise_for_status()

        return response.json()

    async def get_user_schedule(self, telegram_id: int) -> list[dict[str, Any]]:
        # В изученных маршрутах API расписание пока не найдено.
        return []

    async def get_user_tasks(self, telegram_id: int) -> list[dict[str, Any]]:
        # Маршруты заданий требуют JWT, которого у бота пока нет.
        return []
