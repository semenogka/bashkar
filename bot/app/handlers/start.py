
import logging
import random

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters.command import CommandObject

from app.api.interfaces import PlatformClient
from app.keyboards.main_menu import app_keyboard, get_main_menu
from app.services.registration import RegistrationService
from app.config import settings

router = Router()
logger = logging.getLogger(__name__)

_FAREWELL = {
    "пока",
    "до свидания",
    "прощай",
    "прощайте",
    "хуш",
    "һау бул",
    "һау булығыҙ",
    "goodbye",
    "bye",
}


@router.message(CommandStart())
async def start_handler(
    message: Message,
    command: CommandObject,
    platform_client: PlatformClient,
):
    user = message.from_user
    payload = command.args  # None, если команда без параметров

    # Deep link: /start webapp — предлагаем открыть Mini App
    if payload == "webapp":
        mini_app_url = settings.MINI_APP_URL or "https://t.me/beztel_bot"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Ҡушымтаны асыу 🚀",
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                ]
            ]
        )
        await message.answer(
            f"Сәләм, {user.first_name}!\n\n"
            "Башҡорт телен өйрәнергә ҡушымтаны ас. Төймәне баҫ.",
            reply_markup=keyboard,
        )
        return

    # Обычный /start — регистрация на платформе
    try:
        registration_service = RegistrationService(platform_client)

        result = await registration_service.register(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        if result.get("is_new") is False:
            text = (
                f"Сәләм, {user.first_name}! Кире ҡайттың.\n\n"
                "Һине күреүемә шатмын.\n"
                "Профиль менән рейтинг — аҫтағы төймәләрҙә.\n"
                "Уҡыу — ҡушымтала."
            )
        else:
            text = (
                f"Сәләм, {user.first_name}!\n\n"
                "Башҡорт теленә рәхим ит.\n"
                "Мин серия тураһында хәбәр итәм, уҡырға саҡырам һәм дәрт бирәм.\n"
                "Профиль менән рейтинг — аҫтағы төймәләрҙә.\n"
                "Уҡыу — ҡушымтала."
            )

        await message.answer(text, reply_markup=get_main_menu())
        extra = app_keyboard()
        if extra is not None:
            await message.answer("Ҡушымтаны асыу:", reply_markup=extra)

    except Exception:
        logger.exception("Ошибка регистрации пользователя Telegram")

        await message.answer(
            "Платформаға тоташып булманы.\n"
            "Бер аҙҙан яңынан ҡара."
        )


def _is_farewell(text: str | None) -> bool:
    return (text or "").strip().casefold() in _FAREWELL


@router.message(Command("stop"))
@router.message(F.text.func(_is_farewell))
async def farewell_handler(message: Message):
    name = message.from_user.first_name if message.from_user else ""
    who = f", {name}" if name else ""
    farewell = random.choice((
        f"Хуш{who}!\nҺау бул. Кире ҡайтһаң, /start яҙ.",
        f"Һау булығыҙ{who}!\nКүрешеүгә тиклем. Ҡайтҡас /start яҙ.",
        f"Хуш{who}!\nИҫән-һау бул. Кире ҡайтһаң, /start яҙ.",
    ))
    await message.answer(farewell)
