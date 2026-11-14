"""Напоминания в Telegram: учёба, серия и короткая мотивация."""
from __future__ import annotations

import datetime as dt
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db_client import UFA, DbPlatformClient, ufa_today
from app.keyboards.main_menu import app_keyboard

logger = logging.getLogger(__name__)

MILESTONES = {3, 7, 14, 21, 30, 60, 100}

MOTIVATION = (
    "Одно слово сегодня лучше, чем десять «завтра».",
    "Башкирский остаётся, когда к нему возвращаешься.",
    "Пятнадцать минут — и день уже не пустой.",
    "Серия держится на маленьком шаге, не на подвиге.",
    "Сегодняшняя фраза завтра вспомнится сама.",
    "Короткое занятие тоже считается.",
    "Язык растёт в те дни, когда не хочется, но открыл.",
)


def _motivation(day_index: int) -> str:
    return MOTIVATION[day_index % len(MOTIVATION)]


class Notifier:
    def __init__(self, bot: Bot, db: DbPlatformClient):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=UFA)

    def start(self) -> None:
        self.scheduler.add_job(self.morning, CronTrigger(hour=10, minute=0, timezone=UFA), id="remind")
        self.scheduler.add_job(self.evening, CronTrigger(hour=20, minute=0, timezone=UFA), id="streak")
        self.scheduler.start()
        self.scheduler.add_job(self.catch_up, id="catchup")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def catch_up(self) -> None:
        """Если бот подняли после часа рассылки, письмо за сегодня всё равно уходит один раз."""
        hour = dt.datetime.now(UFA).hour
        if hour >= 10:
            await self.morning()
        if hour >= 20:
            await self.evening()

    async def morning(self) -> None:
        today = ufa_today()
        line = _motivation(today.toordinal())
        for user in await self.db.list_notify_users():
            if user["studied_today"]:
                continue
            if not await self.db.claim_notice(user["id"], "remind", today):
                continue
            text = (
                f"{user['name']}, пора заняться башкирским.\n\n"
                f"{line}\n\n"
                "Профиль и рейтинг — здесь. Учиться — в приложении."
            )
            await self._send(user, "remind", today, text)

    async def evening(self) -> None:
        today = ufa_today()
        for user in await self.db.list_notify_users():
            streak = user["streak"]
            if user["studied_today"]:
                if streak in MILESTONES and await self.db.claim_notice(user["id"], "milestone", today):
                    text = (
                        f"Серия {streak} дней. Так и держи.\n\n"
                        "Завтра приложение снова будет ждать."
                    )
                    await self._send(user, "milestone", today, text)
                continue
            if streak <= 0:
                continue
            if not await self.db.claim_notice(user["id"], "streak", today):
                continue
            text = (
                f"Серия {streak} дн. сегодня ещё не сохранена.\n\n"
                "Одно короткое занятие в приложении — и она останется."
            )
            await self._send(user, "streak", today, text)

    async def _send(self, user: dict, kind: str, day, text: str) -> None:
        try:
            await self.bot.send_message(user["chat_id"], text, reply_markup=app_keyboard())
        except TelegramAPIError:
            logger.info("Не доставили уведомление %s пользователю %s", kind, user["id"])
            await self.db.release_notice(user["id"], kind, day)
        except Exception:
            logger.exception("Ошибка уведомления %s", kind)
            await self.db.release_notice(user["id"], kind, day)
