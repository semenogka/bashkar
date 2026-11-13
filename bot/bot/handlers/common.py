"""Telegram-бот: карточки, быстрый перевод, дуэли, чат, статистика."""
from __future__ import annotations

import time
from typing import Any

import httpx
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import API_URL
from bot.states import LearnFlow

router = Router()

LANG_BUTTONS = [
    ("🇷🇺 Русский", "ba-ru"),
    ("🇰🇿 Казахский", "ba-kk"),
    ("🇨🇳 Китайский", "ba-zh"),
]


# ---------------------------------------------------------------------------
# HTTP-клиент
# ---------------------------------------------------------------------------
async def api_get(path: str, **params) -> Any:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(f"{API_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()


async def api_post(path: str, payload: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(f"{API_URL}{path}", json=payload or {})
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Регистрация и меню
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    payload = {
        "external_id": str(message.from_user.id),
        "name": message.from_user.full_name,
        "avatar": "🐝",
    }
    user = await api_post("/api/users", payload)
    await state.update_data(user_id=user["id"], history=[])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=f"lang:{code}")] for text, code in LANG_BUTTONS
    ])
    await message.answer(
        f"🐝 <b>Сәләм, {message.from_user.first_name}!</b>\n\n"
        "Меня зовут Бяш — репетитор по башкирскому языку.\n"
        "Выбери язык перевода, и начнём:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(LearnFlow.choosing_lang)


@router.callback_query(F.data.startswith("lang:"))
async def choose_lang(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    data = await state.get_data()
    user_id = data.get("user_id")
    if user_id:
        await api_post(f"/api/users/{user_id}/lang-pair", {"lang_pair_code": code})
    await state.update_data(lang_pair=code)
    await state.set_state(None)
    await callback.message.edit_text(
        f"✅ Язык перевода: <b>{code}</b>\n\n"
        "Команды:\n"
        "/task — карточка с переводом\n"
        "/speed — быстрый перевод (60 секунд)\n"
        "/duel — состязание\n"
        "/chat — поговорить с репетитором\n"
        "/stats — твоя статистика\n"
        "/top — таблица лидеров",
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Карточки
# ---------------------------------------------------------------------------
@router.message(Command("task"))
async def cmd_task(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Начни с /start 🐝")
        return
    try:
        card = await api_get("/api/cards/next", user_id=user_id)
    except httpx.HTTPError:
        await message.answer("Не удалось получить карточку. Попробуй ещё раз.")
        return

    await state.update_data(card=card)
    buttons = [
        [InlineKeyboardButton(text=option, callback_data=f"ans:{i}")]
        for i, option in enumerate(card.get("options") or [card["translation"]])
    ]
    buttons.append([InlineKeyboardButton(text="🔊 Озвучка", callback_data="tts")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"🐝 <b>{card['text_ba']}</b>\n\n"
        "Как это переводится?\n"
        f"Источник: {card.get('source') or '—'}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await state.set_state(LearnFlow.answering_card)


@router.callback_query(F.data.startswith("ans:"))
async def answer_card(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card = data.get("card")
    if not card:
        await callback.answer("Карточка устарела, возьми новую: /task")
        return
    index = int(callback.data.split(":")[1])
    options = card.get("options") or [card["translation"]]
    chosen = options[index] if index < len(options) else card["translation"]

    result = await api_post("/api/answers", {
        "user_id": data["user_id"],
        "fragment_id": card["fragment_id"],
        "lang_pair_id": card["lang_pair_id"],
        "answer": chosen,
        "time_spent": 3.0,
        "mode": "normal",
    })

    if result["correct"]:
        extra = f"\n🔥 Серия: {result['streak']} · ⭐ {result['xp']} · Lv.{result['level']}"
    else:
        extra = f"\n❤️ Сердец: {result['hearts']}"
    for badge in result.get("new_badges", []):
        extra += f"\n🏅 Новый бейдж: {badge['emoji']} {badge['name']}"

    await callback.message.edit_text(
        f"{'✅ Верно!' if result['correct'] else '❌ Неверно'}\n\n"
        f"Правильный перевод: <b>{result['correct_translation']}</b>{extra}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "tts")
async def play_tts(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card = data.get("card")
    if not card:
        await callback.answer()
        return
    audio = await api_post("/api/speech/tts", {"text": card["text_ba"], "lang": "ba"})
    url = f"{API_URL}{audio['url']}"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            tmp = f"tts_{card['fragment_id']}.wav"
            with open(tmp, "wb") as fh:
                fh.write(response.content)
        await callback.message.answer_audio(tmp, title="Озвучка на башкирском")
    except Exception as exc:  # noqa: BLE001
        await callback.answer(f"Не удалось озвучить: {exc}")


# ---------------------------------------------------------------------------
# Быстрый перевод
# ---------------------------------------------------------------------------
@router.message(Command("speed"))
async def cmd_speed(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Начни с /start 🐝")
        return
    cards = await api_get("/api/speed/cards", user_id=user_id, limit=30)
    await state.update_data(
        speed_cards=cards,
        speed_index=0,
        speed_correct=0,
        speed_total=0,
        speed_score=0,
        speed_streak=0,
        speed_best=0,
        speed_started=time.time(),
    )
    await state.set_state(LearnFlow.speed_running)
    await message.answer(
        "⚡ <b>Быстрый перевод!</b>\n\n"
        "60 секунд на 30 карточек. Отвечай переводами — быстрее = больше очков.\n\n"
        f"Сейчас:\n<b>{cards[0]['text_ba']}</b>\n"
        f"Перевод: <i>{cards[0]['translation']}</i>",
        parse_mode="HTML",
    )


@router.message(LearnFlow.speed_running)
async def speed_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    cards = data.get("speed_cards") or []
    index = data.get("speed_index", 0)
    if index >= len(cards):
        await finish_speed(message, state)
        return
    card = cards[index]
    elapsed = time.time() - data.get("speed_started", time.time())
    if elapsed > 60:
        await finish_speed(message, state)
        return

    correct = message.text.strip().lower() == card["translation"].strip().lower()
    streak = data.get("speed_streak", 0) + 1 if correct else 0
    points = max(1, int(12 - elapsed / (index + 1))) if correct else 0
    await state.update_data(
        speed_index=index + 1,
        speed_correct=data.get("speed_correct", 0) + (1 if correct else 0),
        speed_total=data.get("speed_total", 0) + 1,
        speed_score=data.get("speed_score", 0) + points,
        speed_streak=streak,
        speed_best=max(data.get("speed_best", 0), streak),
    )

    if index + 1 >= len(cards):
        await finish_speed(message, state)
        return
    nxt = cards[index + 1]
    mark = "✅" if correct else "❌"
    await message.answer(
        f"{mark} +{points} очков · 🔥 {streak}\n\n"
        f"Следующее:\n<b>{nxt['text_ba']}</b>\n"
        f"Перевод: <i>{nxt['translation']}</i>",
        parse_mode="HTML",
    )


async def finish_speed(message: Message, state: FSMContext):
    data = await state.get_data()
    cards = data.get("speed_cards") or []
    run = await api_post("/api/speed/run", {
        "user_id": data["user_id"],
        "lang_pair_id": cards[0]["lang_pair_id"] if cards else 1,
        "score": data.get("speed_score", 0),
        "correct": data.get("speed_correct", 0),
        "total": data.get("speed_total", 0),
        "duration": 60.0,
        "best_streak": data.get("speed_best", 0),
    })
    await state.set_state(None)
    badges = "".join(f"\n🏅 {b['emoji']} {b['name']}" for b in run.get("new_badges", []))
    await message.answer(
        f"🏁 <b>Время вышло!</b>\n\n"
        f"Очки: <b>{run['score']}</b>\n"
        f"Верных: {run['correct']} из {run['total']}\n"
        f"Лучшая серия: {run['best_streak']}\n"
        f"+{run['xp_gained']} XP{badges}",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Дуэль
# ---------------------------------------------------------------------------
@router.message(Command("duel"))
async def cmd_duel(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Начни с /start 🐝")
        return
    profile = await api_get(f"/api/users/{user_id}")
    pairs = await api_get("/api/lang-pairs")
    pair_id = next((p["id"] for p in pairs if p["code"] == profile.get("lang_pair_code")), None)
    duel = await api_post("/api/duels", {"challenger_id": user_id, "lang_pair_id": pair_id})
    await state.update_data(duel=duel)
    await message.answer(
        f"⚔️ <b>Дуэль {duel['code']}</b>\n\n"
        f"Переведи быстрее и точнее:\n<b>{duel['text_ba']}</b>\n\n"
        "Ответь переводом сообщением.",
        parse_mode="HTML",
    )


@router.message(Command("chat"))
async def cmd_chat(message: Message, state: FSMContext):
    await state.set_state(LearnFlow.chatting)
    await message.answer(
        "💬 <b>Чат с репетитором.</b>\n\n"
        "Пиши на любом языке — отвечу на башкирском, переведу и озвучу.\n"
        "/cancel — выйти из чата.",
        parse_mode="HTML",
    )


@router.message(LearnFlow.chatting)
async def chat_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    history = data.get("history") or []
    try:
        result = await api_post("/api/chat", {
            "user_id": user_id,
            "message": message.text,
            "target_lang": (data.get("lang_pair") or "ba-ru").split("-")[-1],
            "history": history[-10:],
        })
    except httpx.HTTPError:
        await message.answer("Репетитор недоступен, попробуй позже 🐝")
        return

    history = (history + [
        {"role": "user", "content": message.text},
        {"role": "assistant", "content": result["text_ba"]},
    ])[-12:]
    await state.update_data(history=history)

    text = f"🐝 <b>{result['text_ba']}</b>"
    if result.get("translation"):
        text += f"\n<i>{result['translation']}</i>"
    if result.get("clarify"):
        text += "\n\n🤔 Я переспрашиваю — уточним, что ты имел в виду."
    await message.answer(text, parse_mode="HTML")

    audio = result.get("audio")
    if audio:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(f"{API_URL}{audio['url']}")
                tmp = "chat_tts.wav"
                with open(tmp, "wb") as fh:
                    fh.write(response.content)
            await message.answer_audio(tmp, title="Озвучка ответа")
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Статистика и рейтинг
# ---------------------------------------------------------------------------
@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Начни с /start 🐝")
        return
    stats = await api_get(f"/api/stats/me/{user_id}")
    daily = await api_get(f"/api/daily", user_id=user_id)
    tasks = "\n".join(
        f"{'✅' if t['completed'] else '▫️'} {t['title']} ({t['progress']}/{t['target']})"
        for t in daily["tasks"]
    )
    badges = " ".join(b["emoji"] for b in stats.get("badges", [])) or "—"
    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"⭐ XP: {stats['xp']} · Lv.{stats['level']} · {stats['league']}\n"
        f"🔥 Серия: {stats['streak']} (рекорд {stats['longest_streak']})\n"
        f"❤️ Сердец: {stats['hearts']} · 💎 Кристаллов: {stats['gems']}\n"
        f"✅ Ответов: {stats['total_answers']} (точность {stats['accuracy']}%)\n"
        f"📚 Слов освоено: {stats['vocab_learned']}\n"
        f"⚡ Забегов: {stats['speed_runs']} (рекорд {stats['best_speed']})\n"
        f"⚔️ Дуэлей: {stats['duels_won']} из {stats['duels_total']}\n"
        f"🏅 Бейджи: {badges}\n\n"
        f"<b>Задания дня:</b>\n{tasks}\n\n"
        f"Сегодня: {daily['cards_done_today']}/{daily['daily_goal']} карточек",
        parse_mode="HTML",
    )


@router.message(Command("top"))
async def cmd_top(message: Message):
    board = await api_get("/api/leaderboard/users", limit=10)
    lines = [
        f"{'🥇' if row['rank'] == 1 else '🥈' if row['rank'] == 2 else '🥉' if row['rank'] == 3 else '  '} "
        f"{row['rank']}. {row['name']} — {row['xp']} XP · Lv.{row['level']} · 🔥{row['streak']}"
        for row in board
    ]
    await message.answer("🏆 <b>Таблица лидеров</b>\n\n" + "\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено. /start — начать заново.")
