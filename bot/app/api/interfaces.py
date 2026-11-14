
from abc import ABC, abstractmethod
from typing import Any


class PlatformClient(ABC):

    @abstractmethod
    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def get_user_profile(
        self,
        telegram_id: int
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def get_user_rating(
        self,
        telegram_id: int
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def get_leaderboard(
        self,
        telegram_id: int,
        period: str = "day",
    ) -> dict[str, Any]:
        pass

    async def ensure_schema(self) -> None:
        return None

    async def list_notify_users(self) -> list[dict[str, Any]]:
        return []

    async def claim_notice(self, user_id: int, kind: str, day) -> bool:
        return False

    async def release_notice(self, user_id: int, kind: str, day) -> None:
        return None

    @abstractmethod
    async def get_user_statistics(
        self,
        telegram_id: int
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def get_user_schedule(
        self,
        telegram_id: int
    ) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def get_user_tasks(
        self,
        telegram_id: int
    ) -> list[dict[str, Any]]:
        pass
