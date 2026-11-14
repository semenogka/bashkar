
from typing import Any

from app.api.interfaces import PlatformClient


class MockPlatformClient(PlatformClient):
    def __init__(self):
        self.registered_users = set()

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str,
    ) -> dict[str, Any]:
        is_new = telegram_id not in self.registered_users
        self.registered_users.add(telegram_id)

        return {
            "success": True,
            "is_new": is_new,
            "user": {
                "id": telegram_id,
                "external_id": str(telegram_id),
                "name": first_name,
                "username": username,
                "xp": 250,
                "level": 3,
                "league": "bronze",
                "streak": 5,
            },
        }

    async def get_user_profile(self, telegram_id: int):
        return {
            "id": telegram_id,
            "name": "Тестовый пользователь",
            "xp": 250,
            "level": 3,
            "league": "bronze",
            "streak": 5,
        }

    async def get_user_rating(self, telegram_id: int):
        return {
            "position": 15,
            "points": 250,
        }

    async def get_leaderboard(self, telegram_id: int, period: str = "day"):
        return {
            "period": period,
            "top": [{"name": "Тестовый пользователь", "xp": 250}],
            "position": 1,
            "points": 250,
            "class_rank": None,
            "school_rank": None,
        }

    async def get_user_statistics(self, telegram_id: int):
        return {
            "total_answers": 40,
            "correct": 32,
            "accuracy": 80,
            "vocab_learned": 25,
            "level": 3,
            "xp": 250,
            "streak": 5,
        }

    async def get_user_schedule(self, telegram_id: int):
        return []

    async def get_user_tasks(self, telegram_id: int):
        return []
