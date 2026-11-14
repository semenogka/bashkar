from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from app.config import settings


def mini_app_url() -> str:
    return (settings.MINI_APP_URL or "").strip()


def webapp_button(text: str = "Открыть приложение") -> InlineKeyboardButton | None:
    url = mini_app_url()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def get_main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="🏆 Рейтинг"),
        ]
    ]
    url = mini_app_url()
    if url.startswith("https://"):
        rows.append([KeyboardButton(text="🚀 Приложение", web_app=WebAppInfo(url=url))])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Профиль или рейтинг",
    )


def app_keyboard() -> InlineKeyboardMarkup | None:
    button = webapp_button()
    if button is None:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def rating_keyboard(period: str) -> InlineKeyboardMarkup:
    def label(code: str, title: str) -> str:
        return f"· {title} ·" if code == period else title

    rows = [[
        InlineKeyboardButton(text=label("day", "День"), callback_data="lb:day"),
        InlineKeyboardButton(text=label("month", "Месяц"), callback_data="lb:month"),
        InlineKeyboardButton(text=label("year", "Год"), callback_data="lb:year"),
    ]]
    button = webapp_button("Учиться в приложении")
    if button is not None:
        rows.append([button])
    return InlineKeyboardMarkup(inline_keyboard=rows)
