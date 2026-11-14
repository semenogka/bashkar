import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api.interfaces import PlatformClient
from app.keyboards.main_menu import app_keyboard, rating_keyboard

router = Router()
logger = logging.getLogger(__name__)

PERIODS = {"day": "день", "month": "месяц", "year": "год"}


def _profile_text(profile: dict) -> str:
    name = html.escape(str(profile.get("name") or "Не указано"))
    streak = int(profile.get("streak") or 0)
    best = int(profile.get("longest_streak") or 0)
    return (
        "👤 <b>Профиль</b>\n\n"
        f"Имя: {name}\n"
        f"Уровень: {profile.get('level', 1)}\n"
        f"Опыт: {profile.get('xp', 0)} XP\n"
        f"Серия: {streak} дн.\n"
        f"Лучшая серия: {best} дн."
    )


def _rating_text(board: dict) -> str:
    period = PERIODS.get(board.get("period"), "день")
    lines = [f"🏆 <b>Рейтинг за {period}</b>", ""]
    top = board.get("top") or []
    if not top:
        lines.append("За этот период очков пока нет. Они появляются после занятий в приложении.")
    else:
        for index, row in enumerate(top, start=1):
            name = html.escape(str(row.get("name") or "Ученик"))
            lines.append(f"{index}. {name} — {row.get('xp', 0)} XP")
    lines.append("")
    position = board.get("position")
    points = board.get("points") or 0
    if position:
        lines.append(f"Ты: {position} место · {points} XP")
    else:
        lines.append("Тебя в этом периоде пока нет.")
    class_rank = board.get("class_rank")
    if class_rank:
        title = html.escape(str(class_rank["name"]))
        lines.append(f"Класс {title}: {class_rank['rank']} место · {class_rank['xp']} XP")
    school_rank = board.get("school_rank")
    if school_rank:
        title = html.escape(str(school_rank["name"]))
        lines.append(f"Школа {title}: {school_rank['rank']} место · {school_rank['xp']} XP")
    return "\n".join(lines)


async def _send_profile(message: Message, platform_client: PlatformClient) -> None:
    try:
        profile = await platform_client.get_user_profile(message.from_user.id)
        await message.answer(_profile_text(profile), parse_mode="HTML", reply_markup=app_keyboard())
    except Exception:
        logger.exception("Ошибка получения профиля")
        await message.answer("Не удалось загрузить профиль. Напиши /start и попробуй ещё раз.")


async def _send_rating(message: Message, platform_client: PlatformClient, period: str = "day") -> None:
    try:
        board = await platform_client.get_leaderboard(message.from_user.id, period)
        await message.answer(
            _rating_text(board),
            parse_mode="HTML",
            reply_markup=rating_keyboard(board.get("period") or "day"),
        )
    except Exception:
        logger.exception("Ошибка получения рейтинга")
        await message.answer("Не удалось загрузить рейтинг. Напиши /start и попробуй ещё раз.")


@router.message(Command("profile"))
@router.message(F.text.in_({"👤 Профиль", "👤 Мой профиль"}))
async def profile_handler(message: Message, platform_client: PlatformClient):
    await _send_profile(message, platform_client)


@router.message(Command("rating"))
@router.message(F.text.in_({"🏆 Рейтинг", "🏆 Мой рейтинг"}))
async def rating_handler(message: Message, platform_client: PlatformClient):
    await _send_rating(message, platform_client)


@router.callback_query(F.data.startswith("lb:"))
async def rating_period(callback: CallbackQuery, platform_client: PlatformClient):
    period = (callback.data or "lb:day").split(":", 1)[1]
    if period not in PERIODS:
        period = "day"
    try:
        board = await platform_client.get_leaderboard(callback.from_user.id, period)
        if callback.message is None:
            await callback.answer()
            return
        await callback.message.edit_text(
            _rating_text(board),
            parse_mode="HTML",
            reply_markup=rating_keyboard(period),
        )
        await callback.answer()
    except Exception:
        logger.exception("Ошибка смены периода рейтинга")
        await callback.answer("Не удалось обновить рейтинг", show_alert=True)


@router.message(F.text.in_({"📊 Статистика", "📚 Открыть платформу", "🚀 Приложение"}))
async def retired_handler(message: Message):
    await message.answer(
        "Учёба, словарь и задания — в приложении.\n"
        "Здесь остаются профиль, рейтинг и напоминания.",
        reply_markup=app_keyboard(),
    )


@router.message(F.text & ~F.text.startswith("/"))
async def only_profile_and_rating(message: Message):
    await message.answer(
        "В боте можно открыть профиль и рейтинг.\n"
        "Всё остальное — в приложении.",
        reply_markup=app_keyboard(),
    )
