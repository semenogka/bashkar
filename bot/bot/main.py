import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart

from bot.config import BOT_TOKEN
from bot.handlers import start


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(start.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())