"""FSM-состояния Telegram-бота."""
from aiogram.fsm.state import State, StatesGroup


class LearnFlow(StatesGroup):
    choosing_lang = State()   # выбор языковой пары при регистрации
    answering_card = State()  # ждём ответ на карточку
    speed_running = State()   # идёт забег «быстрый перевод»
    chatting = State()         # свободный чат с репетитором


class SpeedFlow(StatesGroup):
    answering = State()
