
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters.command import CommandObject

from app.api.interfaces import PlatformClient
from app.keyboards.main_menu import app_keyboard, get_main_menu
from app.services.registration import RegistrationService
from app.config import settings

router = Router()
logger = logging.getLogger(__name__)


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
                        text="Открыть приложение 🚀",
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                ]
            ]
        )
        await message.answer(
            f"Сәләм, {user.first_name}! 👋\n\n"
            "Нажми кнопку ниже, чтобы открыть приложение для изучения башкирского языка:",
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

        greeting = "С возвращением" if result.get("is_new") is False else "Сәләм"
        text = (
            f"{greeting}, {user.first_name}!\n\n"
            "Я пишу про серию, напоминаю заниматься и иногда подкидываю мотивацию.\n"
            "Профиль и рейтинг — кнопками ниже.\n"
            "Учёба и всё остальное — в приложении."
        )

        await message.answer(text, reply_markup=get_main_menu())
        extra = app_keyboard()
        if extra is not None:
            await message.answer("Открыть приложение:", reply_markup=extra)

    except Exception:
        logger.exception("Ошибка регистрации пользователя Telegram")

        await message.answer(
            "Не удалось подключиться к платформе.\n"
            "Попробуй немного позже."
        )
