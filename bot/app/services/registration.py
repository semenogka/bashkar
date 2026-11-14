
from app.api.interfaces import PlatformClient


class RegistrationService:
    def __init__(self, platform_client: PlatformClient):
        self.platform_client = platform_client

    async def register(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str,
    ) -> dict:
        if not telegram_id:
            raise ValueError("Не удалось определить Telegram ID")

        if not first_name:
            first_name = "Ученик"

        result = await self.platform_client.register_user(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )

        if not result or not result.get("success"):
            raise RuntimeError("Не удалось зарегистрировать пользователя")

        return result
