
import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.db_client import DbPlatformClient
from aiogram.types import BotCommand

from app.handlers import start, menu
from app.services.notifier import Notifier


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    platform_client = DbPlatformClient(settings.DATABASE_URL)
    logging.info("Бот читает PostgreSQL напрямую")

    dp["platform_client"] = platform_client

    dp.include_router(start.router)
    dp.include_router(menu.router)

    await platform_client.ensure_schema()
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="rating", description="Рейтинг"),
    ])
    notifier = Notifier(bot, platform_client)
    notifier.start()

    logging.info("Бот запущен. Напоминания в 10:00 и 20:00 по Уфе")

    try:
        await dp.start_polling(bot)
    finally:
        notifier.shutdown()
        await platform_client.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
