"""API v1 для фронтенда «БЕЗТЕЛ» (Telegram Web App): хаб, чат, карточки, дейлик, состязания, профиль."""
from __future__ import annotations

import datetime as dt
import re
import random
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import (
    DailyChallenge,
    DailyVote,
    Duel,
    Fragment,
    LangPair,
    SpeedRun,
    Translation,
    User,
    UserAnswer,
    VocabProgress,
)
from app.services.agreement import normalize
from app.services.speech import to_int16_wav, transcribe
from app.services.tutor import tutor_reply

router = APIRouter(prefix="/v1", tags=["v1"])

# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------
THEMES = [
    {"id": 1, "title": "Приветствие и знакомство", "description": "Сәләм! Как дела? Меня зовут…", "icon": "👋"},
    {"id": 2, "title": "Семья и близкие", "description": "Мама, папа, брат, сестра — ғаилә.", "icon": "👨‍👩‍👧"},
    {"id": 3, "title": "Еда и напитки", "description": "Хлеб, чай, башкирский мёд.", "icon": "🍯"},
    {"id": 4, "title": "Природа и погода", "description": "Лес, гора, река, снег.", "icon": "🏔️"},
    {"id": 5, "title": "Учёба и работа", "description": "Школа, урок, учитель, книга.", "icon": "📚"},
    {"id": 6, "title": "Путешествия", "description": "Дорога, поезд, родной край.", "icon": "🚌"},
]

CULTURAL_NOTES = [
    "Башкиры издавна встречают гостей чаем и мёдом — «мәржәге» с башкирским мёдом считается символом гостеприимства.",
    "Башкирский язык относится к кыпчакской группе тюркских языков и имеет статус государственного в Башкортостане.",
    "Сәләм — универсальное приветствие: подходит и для друга, и для старшего.",
    "В башкирском языке нет категории рода: слово «ул» может значить и «он», и «она».",
    "Ҡаҙын — башкирское блюдо, которое подают на праздниках и в честь гостей.",
    "Традиционный башкирский напиток — кумыс (ҡымыҙ) из кобыльего молока.",
    "Башкирия — край тысячи озёр и гор; самая высокая точка — гора Ямантау.",
    "Өфө — столица Башкортостана, город с более чем 450-летней историей.",
]

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "ğ", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "ҡ": "q", "л": "l", "м": "m",
    "н": "n", "ң": "ñ", "о": "o", "ө": "ö", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ү": "ü", "ф": "f", "х": "x", "һ": "h", "ц": "c", "ч": "ç", "ш": "ş",
    "щ": "ş", "ъ": "", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ә": "ä", "ҙ": "ź", "ҫ": "ś",
}


def translit(text: str) -> str:
    return "".join(TRANSLIT.get(ch.lower(), ch) for ch in text)


def _corrupt(text: str) -> str:
    replacements = {
        "моя": "твоя", "мой": "твой", "лучший": "худший",
        "близкий": "далёкий", "родная": "чужая", "будущее": "прошлое",
        "большое": "малое", "самый": "самый", "основа": "преграда",
    }
    words = text.split()
    out = []
    for w in words:
        low = w.lower().strip(".,!?")
        if low in replacements and random.random() < 0.4:
            w = w.replace(low, replacements[low])
        out.append(w)
    if len(out) > 3 and random.random() < 0.3:
        del out[random.randrange(len(out))]
    return " ".join(out)


def _make_trap(correct: str) -> str | None:
    words = correct.split()
    if len(words) < 2:
        return None
    kind = random.random()
    if kind < 0.34:
        random.shuffle(words)
        return " ".join(words)
    if kind < 0.67:
        idx = random.randrange(len(words))
        words[idx] = words[idx][:-1] if len(words[idx]) > 3 else words[idx] + "а"
        return " ".join(words)
    return correct.replace(" ", "  ")


# ---------------------------------------------------------------------------
# Пользователь (Telegram или гость)
# ---------------------------------------------------------------------------
async def _resolve_user(
    session: AsyncSession,
    telegram_id: str | None = None,
    telegram_name: str | None = None,
) -> User:
    if telegram_id:
        user = (
            await session.execute(select(User).where(User.external_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            pair = (
                await session.execute(select(LangPair).where(LangPair.code == "ba-ru"))
            ).scalar_one_or_none()
            user = User(
                external_id=telegram_id,
                username=f"tg_{telegram_id}",
                name=telegram_name or "Ученик",
                role="student",
                lang_pair_id=pair.id if pair else None,
                avatar="🐝",
                hearts=5,
                created_at=dt.datetime.utcnow(),
            )
            session.add(user)
            await session.flush()
        return user

    user = (
        await session.execute(select(User).where(User.username == "guest"))
    ).scalar_one_or_none()
    if user is None:
        pair = (
            await session.execute(select(LangPair).where(LangPair.code == "ba-ru"))
        ).scalar_one_or_none()
        user = User(
            username="guest",
            name="Гость",
            role="student",
            lang_pair_id=pair.id if pair else None,
            avatar="🐝",
            hearts=5,
            created_at=dt.datetime.utcnow(),
        )
        session.add(user)
        await session.flush()
    return user


# ---------------------------------------------------------------------------
# Хелперы выборки контента
# ---------------------------------------------------------------------------
async def _ba_ru_pair(session: AsyncSession) -> LangPair | None:
    return (
        await session.execute(select(LangPair).where(LangPair.code == "ba-ru"))
    ).scalar_one_or_none()


async def _random_card(session: AsyncSession) -> tuple[Fragment, Translation] | None:
    pair = await _ba_ru_pair(session)
    if pair is None:
        return None
    rows = (
        await session.execute(
            select(Translation, Fragment)
            .join(Fragment, Fragment.id == Translation.fragment_id)
            .where(Translation.lang_pair_id == pair.id)
            .limit(500)
        )
    ).all()
    if not rows:
        return None
    tr, frag = random.choice(rows)
    return frag, tr


# ---------------------------------------------------------------------------
# Хаб
# ---------------------------------------------------------------------------
_DAILY_INSIGHT: dict[dt.date, dict] = {}


@router.get("/hub/insight")
async def hub_insight(session: AsyncSession = Depends(get_session)) -> dict:
    today = dt.date.today()
    if today not in _DAILY_INSIGHT:
        card = await _random_card(session)
        if card is None:
            raise HTTPException(404, "Нет карточек")
        frag, tr = card
        _DAILY_INSIGHT[today] = {
            "bashkir_phrase": frag.text_ba,
            "translation_ru": tr.translation,
            "cultural_note": random.choice(CULTURAL_NOTES),
        }
    return _DAILY_INSIGHT[today]


# ---------------------------------------------------------------------------
# Чат с башкиром
# ---------------------------------------------------------------------------
class ChatMessageIn(BaseModel):
    text: str
    history: list[dict] = []
    target_lang: str = "ru"


def _reply_payload(reply: dict, recognized_text: str | None = None) -> dict:
    audio = reply.get("audio")
    text_ba = _strip_links(reply.get("text_ba") or "")
    translation = _strip_links(reply.get("translation") or "")
    return {
        "bashkir_reply": text_ba,
        "russian_translation": translation,
        "recognized_text": recognized_text,
        "audio_url": audio.get("url") if audio else None,
        "clarify": reply.get("clarify", False),
        "proper": reply.get("proper"),
    }


_LINK_RE = re.compile(r"https?://\S+|www\.\S+|\[[^\]]*\]\([^)]*\)", re.IGNORECASE)


def _strip_links(text: str) -> str:
    """Убирает ссылки на вики/словари и прочие URL из текста ответа ИИ."""
    if not text:
        return text
    text = _LINK_RE.sub("", text)
    # Убираем остаточные упоминания вики/словаря без URL
    text = re.sub(r"(википеди[ая]|wikipedia|словар[ья]|dictionary)", "", text, flags=re.IGNORECASE)
    return text.strip()


@router.post("/chat/message")
async def chat_message(
    data: ChatMessageIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    reply = await tutor_reply(data.text, data.history, data.target_lang)
    user = await _resolve_user(session, telegram_id, telegram_name)
    if user is not None:
        from app.services.gamification import add_xp, touch_streak, update_daily_tasks

        add_xp(user, 5)
        await touch_streak(session, user, xp=5)
        await update_daily_tasks(session, user, card_done=True)
        await session.commit()
    return _reply_payload(reply)


@router.post("/chat/voice")
async def chat_voice(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    wav_path = tmp_path + ".16k.wav"
    try:
        converted = to_int16_wav(tmp_path, wav_path)
        text = await transcribe(converted)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка распознавания: {exc}") from exc
    finally:
        for path in (tmp_path, wav_path):
            try:
                Path(path).unlink()
            except OSError:
                pass

    if not text:
        raise HTTPException(400, "Речь не распознана")
    reply = await tutor_reply(text, [], "ru")
    user = await _resolve_user(session, telegram_id, telegram_name)
    if user is not None:
        from app.services.gamification import add_xp, touch_streak, update_daily_tasks

        add_xp(user, 5)
        await touch_streak(session, user, xp=5)
        await update_daily_tasks(session, user, card_done=True)
        await session.commit()
    return _reply_payload(reply, recognized_text=text)


# ---------------------------------------------------------------------------
# Изучение: карточки и темы
# ---------------------------------------------------------------------------
@router.get("/cards/next")
async def cards_next(session: AsyncSession = Depends(get_session)) -> dict:
    card = await _random_card(session)
    if card is None:
        raise HTTPException(404, "Нет карточек")
    frag, tr = card
    return {
        "fragment_id": frag.id,
        "word_bashkir": frag.text_ba,
        "phonetics": translit(frag.text_ba),
        "translation_ru": tr.translation,
    }


@router.get("/cards/batch")
async def cards_batch(count: int = 20, session: AsyncSession = Depends(get_session)) -> list[dict]:
    pair = await _ba_ru_pair(session)
    if pair is None:
        return []
    rows = (
        await session.execute(
            select(Translation, Fragment)
            .join(Fragment, Fragment.id == Translation.fragment_id)
            .where(Translation.lang_pair_id == pair.id)
            .limit(min(count, 100))
        )
    ).all()
    random.shuffle(rows)
    return [
        {"bashkir": frag.text_ba, "russian": tr.translation}
        for tr, frag in rows
    ]


class CardAnswerIn(BaseModel):
    fragment_id: int
    know: bool


@router.post("/cards/answer")
async def cards_answer(
    data: CardAnswerIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    frag = await session.get(Fragment, data.fragment_id)
    if frag is None:
        raise HTTPException(404, "Фрагмент не найден")

    is_correct = bool(data.know)
    session.add(
        UserAnswer(
            user_id=user.id,
            fragment_id=frag.id,
            lang_pair_id=user.lang_pair_id,
            answer=frag.text_ba,
            is_correct=is_correct,
            mode="normal",
        )
    )
    from app.services.gamification import add_xp, note_answer_streak, touch_streak, update_daily_tasks

    xp = 10 if is_correct else 0
    if is_correct:
        add_xp(user, xp)
        note_answer_streak(user, True)
    else:
        note_answer_streak(user, False)
    await touch_streak(session, user, xp=xp)
    await update_daily_tasks(session, user, card_done=True)
    await session.commit()
    return {"ok": True, "xp_gained": xp, "level": user.level, "streak": user.streak}


@router.get("/themes")
async def themes() -> list[dict]:
    return THEMES


@router.get("/lang-pairs")
async def lang_pairs_v1(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(select(LangPair).where(LangPair.enabled.is_(True)).order_by(LangPair.id))
    ).scalars().all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.native_label or p.code,
            "source_lang": p.source_lang,
            "target_lang": p.target_lang,
        }
        for p in rows
    ]


# ---------------------------------------------------------------------------
# Дейлик
# ---------------------------------------------------------------------------
_PROCESSED_VOTE_DAYS: set[dt.date] = set()


async def _process_daily_votes(session: AsyncSession, day: dt.date) -> None:
    rows = (
        await session.execute(
            select(DailyVote.user_id, DailyVote.choice).where(DailyVote.day == day)
        )
    ).all()
    approve = {uid for uid, choice in rows if choice == "approve"}
    reject = {uid for uid, choice in rows if choice == "reject"}
    if not approve and not reject:
        return
    majority = approve if len(approve) >= len(reject) else reject
    from app.services.gamification import add_xp, touch_streak

    for uid in majority:
        user = await session.get(User, uid)
        if user is not None:
            add_xp(user, 15)
            await touch_streak(session, user, xp=15)
    await session.commit()


async def _vote_stats(session: AsyncSession, day: dt.date) -> dict:
    total = (
        await session.execute(
            select(func.count()).select_from(DailyVote).where(DailyVote.day == day)
        )
    ).scalar_one()
    approve = (
        await session.execute(
            select(func.count())
            .select_from(DailyVote)
            .where(DailyVote.day == day, DailyVote.choice == "approve")
        )
    ).scalar_one()
    reject = (
        await session.execute(
            select(func.count())
            .select_from(DailyVote)
            .where(DailyVote.day == day, DailyVote.choice == "reject")
        )
    ).scalar_one()
    total = total or 1
    return {
        "approvePercent": round(approve / total * 100),
        "rejectPercent": round(reject / total * 100),
    }


@router.get("/daily/tasks")
async def daily_tasks(
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> list[dict]:
    user = await _resolve_user(session, telegram_id, telegram_name)
    from app.services.gamification import ensure_daily_tasks

    tasks = await ensure_daily_tasks(session, user)
    await session.commit()
    return [
        {
            "code": t.code,
            "title": t.title,
            "progress": t.progress,
            "target": t.target,
            "completed": t.completed,
            "xp_reward": t.xp_reward,
        }
        for t in tasks
    ]


@router.get("/daily/task")
async def daily_task(
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    today = dt.date.today()

    # Завершить голосование за прошедшие дни: начислить XP большинству (по одному разу на день)
    past_days = (
        await session.execute(select(DailyVote.day).where(DailyVote.day < today).distinct())
    ).scalars().all()
    for day in past_days:
        if day not in _PROCESSED_VOTE_DAYS:
            await _process_daily_votes(session, day)
            _PROCESSED_VOTE_DAYS.add(day)

    challenge = (
        await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id, DailyChallenge.day == today
            )
        )
    ).scalar_one_or_none()

    if challenge is None:
        card = await _random_card(session)
        if card is None:
            raise HTTPException(404, "Нет данных")
        frag, tr = card
        is_corrupted = random.random() < 0.4
        proposed = _corrupt(tr.translation) if is_corrupted else tr.translation
        challenge = DailyChallenge(
            user_id=user.id,
            day=today,
            fragment_id=frag.id,
            proposed_translation=proposed,
            is_corrupted=is_corrupted,
        )
        session.add(challenge)
        await session.commit()
        await session.refresh(challenge)

    frag = await session.get(Fragment, challenge.fragment_id)
    if frag is None:
        raise HTTPException(404, "Нет данных")

    # Пользователь уже отвечал — возвращаем сохранённый результат, а не новый текст
    if challenge.is_correct is not None:
        return {
            "bashkir_text": frag.text_ba,
            "proposed_translation": challenge.proposed_translation,
            "is_corrupted": challenge.is_corrupted,
            "answered": True,
            "is_correct": challenge.is_correct,
            "user_answer": challenge.user_answer,
            "vote_stats": await _vote_stats(session, today),
        }

    return {
        "bashkir_text": frag.text_ba,
        "proposed_translation": challenge.proposed_translation,
        "is_corrupted": challenge.is_corrupted,
        "answered": False,
        "vote_stats": await _vote_stats(session, today),
    }


class DailyCheckIn(BaseModel):
    bashkir_text: str
    original_proposed: str
    user_corrected: str | None = None
    approved: bool = False


@router.post("/daily/check")
async def daily_check(
    data: DailyCheckIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    today = dt.date.today()

    challenge = (
        await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id, DailyChallenge.day == today
            )
        )
    ).scalar_one_or_none()
    if challenge is None:
        raise HTTPException(404, "Задание дня не найдено. Сначала откройте дейлик.")

    if challenge.is_correct is not None:
        raise HTTPException(400, "Вы уже ответили на дейлик сегодня.")

    if data.approved:
        challenge.user_answer = "approve"
        challenge.is_correct = not bool(challenge.is_corrupted)
        challenge.answered_at = dt.datetime.utcnow()
        await session.commit()
        feedback = "Спасибо! Ваш голос учтён." if challenge.is_correct else "Спасибо! Ваш голос учтён."
        return {
            "is_correct": challenge.is_correct,
            "model_feedback": feedback,
            "reference": None,
            "answered": True,
        }

    frag = (
        await session.execute(select(Fragment).where(Fragment.text_ba == data.bashkir_text))
    ).scalars().first()
    reference = None
    if frag is not None:
        pair = await _ba_ru_pair(session)
        if pair is not None:
            tr = (
                await session.execute(
                    select(Translation).where(
                        Translation.fragment_id == frag.id,
                        Translation.lang_pair_id == pair.id,
                    )
                )
            ).scalar_one_or_none()
            reference = tr.translation if tr else None

    is_correct = bool(reference) and normalize(data.user_corrected) == normalize(reference)

    # Сохраняем ответ пользователя, чтобы при обновлении страницы показывать результат
    challenge.user_answer = data.user_corrected
    challenge.is_correct = is_correct
    challenge.answered_at = dt.datetime.utcnow()
    await session.commit()

    if is_correct:
        feedback = "Дөрөҫ! Башкирский перевод верный. 🔥"
    else:
        feedback = f"Табып ҡарағыҙ: правильный вариант — «{reference or data.original_proposed}»."
    return {
        "is_correct": is_correct,
        "model_feedback": feedback,
        "reference": reference,
        "answered": True,
    }


class DailyVoteIn(BaseModel):
    approved: bool


@router.post("/daily/vote")
async def daily_vote(
    data: DailyVoteIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    today = dt.date.today()
    choice = "approve" if data.approved else "reject"

    already = (
        await session.execute(
            select(DailyVote).where(
                DailyVote.day == today, DailyVote.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if already is None:
        session.add(DailyVote(day=today, user_id=user.id, choice=choice))
        await session.commit()

    return await _vote_stats(session, today)


# ---------------------------------------------------------------------------
# Состязания
# ---------------------------------------------------------------------------
@router.get("/battles/prompt")
async def battle_prompt(mode: str = "sprint", session: AsyncSession = Depends(get_session)) -> dict:
    card = await _random_card(session)
    if card is None:
        raise HTTPException(404, "Нет данных")
    frag, tr = card
    correct = tr.translation

    options = [correct]
    attempts = 0
    while len(options) < (2 if mode == "pvp" else 4) and attempts < 20:
        trap = _make_trap(correct)
        if trap and trap not in options and trap != correct:
            options.append(trap)
        attempts += 1
    while len(options) < (2 if mode == "pvp" else 4):
        options.append(correct + ".")
    random.shuffle(options)
    correct_index = options.index(correct)

    if mode == "pvp":
        return {
            "pvp_bashkir_phrase": frag.text_ba,
            "options": options,
            "correct_index": correct_index,
            "fragment_id": frag.id,
        }
    return {
        "bashkir_prompt": frag.text_ba,
        "options": options,
        "correct_index": correct_index,
        "fragment_id": frag.id,
    }


# ---------------------------------------------------------------------------
# Профиль
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PvP matchmaking + WebSocket
# ---------------------------------------------------------------------------
import uuid as _uuid

_PVP_WAITING: dict[str, dict] = {}
_PVP_MATCHES: dict[str, dict] = {}
_USER_MATCH: dict[str, str] = {}
_PVP_WS: dict[str, WebSocket] = {}
_PVP_WS_WAITING: set[str] = set()
_PVP_WS_MATCHES: dict[str, dict] = {}
_PVP_WS_USER_MATCH: dict[str, str] = {}


def _client_id(telegram_id: str | None, client_id: str | None) -> str:
    return client_id or telegram_id or "guest"


async def _build_pvp_prompt(session: AsyncSession) -> dict:
    card = await _random_card(session)
    if card is None:
        raise HTTPException(404, "Нет карточек")
    frag, tr = card
    correct = tr.translation
    options = [correct]
    attempts = 0
    while len(options) < 2 and attempts < 20:
        trap = _make_trap(correct)
        if trap and trap not in options and trap != correct:
            options.append(trap)
        attempts += 1
    while len(options) < 2:
        options.append(correct + ".")
    random.shuffle(options)
    correct_index = options.index(correct)
    return {
        "pvp_bashkir_phrase": frag.text_ba,
        "options": options,
        "correct_index": correct_index,
        "fragment_id": frag.id,
    }


@router.post("/pvp/find")
async def pvp_find(
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)

    if uid in _USER_MATCH:
        mid = _USER_MATCH[uid]
        match = _PVP_MATCHES.get(mid)
        if match:
            return {
                "status": "matched",
                "match_id": mid,
                "questions": match["questions"],
                "started_at": match["started_at"].isoformat(),
                "duration": match["duration"],
                "finished": bool(match.get("finished")),
            }
        _USER_MATCH.pop(uid, None)

    now = dt.datetime.utcnow()
    for oid, info in list(_PVP_WAITING.items()):
        if (now - info["joined_at"]).total_seconds() > 60:
            _PVP_WAITING.pop(oid, None)

    opponent = None
    for oid in list(_PVP_WAITING.keys()):
        if oid != uid:
            opponent = oid
            break

    if opponent is not None:
        _PVP_WAITING.pop(opponent, None)
        _PVP_WAITING.pop(uid, None)
        questions = [await _build_pvp_prompt(session) for _ in range(10)]
        mid = _uuid.uuid4().hex
        _PVP_MATCHES[mid] = {
            "users": [uid, opponent],
            "questions": questions,
            "started_at": now,
            "duration": 60,
            "progress": {
                uid: {"index": 0, "score": 0, "done": False},
                opponent: {"index": 0, "score": 0, "done": False},
            },
            "finished": False,
        }
        _USER_MATCH[uid] = mid
        _USER_MATCH[opponent] = mid
        return {
            "status": "matched",
            "match_id": mid,
            "questions": questions,
            "started_at": now.isoformat(),
            "duration": 60,
            "finished": False,
        }

    _PVP_WAITING[uid] = {"joined_at": now}
    return {"status": "searching"}


@router.get("/pvp/status")
async def pvp_status(
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    if uid in _USER_MATCH:
        mid = _USER_MATCH[uid]
        match = _PVP_MATCHES.get(mid)
        if match:
            now = dt.datetime.utcnow()
            elapsed = (now - match["started_at"]).total_seconds()
            finished = elapsed >= match["duration"] or all(p.get("done") for p in match["progress"].values())
            opp_uid = [u for u in match["users"] if u != uid][0]
            winner = None
            winner_is_you = False
            if finished:
                s_you = match["progress"][uid]["score"]
                s_opp = match["progress"][opp_uid]["score"]
                if s_you > s_opp:
                    winner = uid
                    winner_is_you = True
                elif s_opp > s_you:
                    winner = opp_uid
                else:
                    winner = "draw"
            return {
                "status": "finished" if finished else "matched",
                "match_id": mid,
                "questions": match["questions"],
                "started_at": match["started_at"].isoformat(),
                "duration": match["duration"],
                "your_progress": match["progress"][uid],
                "opponent_progress": {
                    "index": match["progress"][opp_uid]["index"],
                    "score": match["progress"][opp_uid]["score"],
                    "done": match["progress"][opp_uid]["done"],
                },
                "winner": winner,
                "winner_is_you": winner_is_you,
            }
        _USER_MATCH.pop(uid, None)
    if uid in _PVP_WAITING:
        return {"status": "searching"}
    return {"status": "idle"}


class PvpProgressIn(BaseModel):
    index: int = 0
    score: int = 0
    done: bool = False


@router.post("/pvp/progress")
async def pvp_progress(
    data: PvpProgressIn,
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    if uid not in _USER_MATCH:
        raise HTTPException(404, "Нет активного матча")
    mid = _USER_MATCH[uid]
    match = _PVP_MATCHES.get(mid)
    if not match or uid not in match["progress"]:
        raise HTTPException(404, "Матч не найден")
    match["progress"][uid]["index"] = int(data.index)
    match["progress"][uid]["score"] = int(data.score)
    match["progress"][uid]["done"] = bool(data.done)
    opp_uid = [u for u in match["users"] if u != uid][0]
    return {
        "ok": True,
        "opponent_progress": {
            "index": match["progress"][opp_uid]["index"],
            "score": match["progress"][opp_uid]["score"],
            "done": match["progress"][opp_uid]["done"],
        },
    }


@router.post("/pvp/cancel")
async def pvp_cancel(
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    _PVP_WAITING.pop(uid, None)
    mid = _USER_MATCH.pop(uid, None)
    if mid and mid in _PVP_MATCHES:
        match = _PVP_MATCHES.pop(mid, None)
        if match:
            for u in match.get("users", []):
                _USER_MATCH.pop(u, None)
    return {"status": "cancelled"}


async def _ws_finish(match: dict, session: AsyncSession | None = None, winner_uid: str | None = None):
    if match.get("finished"):
        return
    match["finished"] = True
    users = match["users"]
    scores = {u: match["progress"][u]["score"] for u in users}
    if winner_uid is None:
        u1, u2 = users
        if scores[u1] > scores[u2]:
            winner_uid = u1
        elif scores[u2] > scores[u1]:
            winner_uid = u2
        else:
            winner_uid = "draw"
    for u in users:
        ws = _PVP_WS.get(u)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "finished",
                    "winner": winner_uid,
                    "winner_is_you": winner_uid == u,
                    "your_score": scores[u],
                    "opponent_score": scores[[x for x in users if x != u][0]],
                })
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
    for u in users:
        _PVP_WS.pop(u, None)
        _PVP_WS_USER_MATCH.pop(u, None)


@router.websocket("/pvp/ws")
async def pvp_websocket(
    websocket: WebSocket,
    client_id: str | None = Query(default=None),
    telegram_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    uid = _client_id(client_id, telegram_id)
    await websocket.accept()

    old = _PVP_WS.get(uid)
    if old is not None and old is not websocket:
        try:
            await old.close()
        except Exception:
            pass
    _PVP_WS[uid] = websocket

    try:
        while True:
            data = await websocket.receive_json()
            typ = data.get("type")

            if typ == "find":
                if uid in _PVP_WS_USER_MATCH:
                    mid = _PVP_WS_USER_MATCH[uid]
                    match = _PVP_WS_MATCHES.get(mid)
                    if match:
                        opp_uid = [u for u in match["users"] if u != uid][0]
                        finished = bool(match.get("finished"))
                        winner = None
                        winner_is_you = False
                        if finished:
                            scores = {u: match["progress"][u]["score"] for u in match["users"]}
                            if scores[uid] > scores[opp_uid]:
                                winner = uid
                                winner_is_you = True
                            elif scores[opp_uid] > scores[uid]:
                                winner = opp_uid
                            else:
                                winner = "draw"
                        await websocket.send_json({
                            "type": "matched",
                            "match_id": mid,
                            "questions": match["questions"],
                            "started_at": match["started_at"].isoformat(),
                            "duration": match["duration"],
                            "finished": finished,
                            "winner": winner,
                            "winner_is_you": winner_is_you,
                            "your_score": match["progress"][uid]["score"],
                            "opponent_score": match["progress"][opp_uid]["score"],
                            "opponent_progress": {
                                "index": match["progress"][opp_uid]["index"],
                                "score": match["progress"][opp_uid]["score"],
                                "done": match["progress"][opp_uid]["done"],
                            },
                        })
                        if finished:
                            await websocket.send_json({
                                "type": "finished",
                                "winner": winner,
                                "winner_is_you": winner_is_you,
                                "your_score": match["progress"][uid]["score"],
                                "opponent_score": match["progress"][opp_uid]["score"],
                            })
                        continue

                _PVP_WS_WAITING.discard(uid)
                opponent = None
                for oid in list(_PVP_WS_WAITING):
                    if oid != uid and oid in _PVP_WS:
                        opponent = oid
                        break

                if opponent is not None:
                    _PVP_WS_WAITING.discard(opponent)
                    questions = [await _build_pvp_prompt(session) for _ in range(10)]
                    mid = _uuid.uuid4().hex
                    now = dt.datetime.utcnow()
                    _PVP_WS_MATCHES[mid] = {
                        "users": [uid, opponent],
                        "questions": questions,
                        "started_at": now,
                        "duration": 60,
                        "progress": {
                            uid: {"index": 0, "score": 0, "done": False},
                            opponent: {"index": 0, "score": 0, "done": False},
                        },
                        "finished": False,
                    }
                    _PVP_WS_USER_MATCH[uid] = mid
                    _PVP_WS_USER_MATCH[opponent] = mid
                    payload = {
                        "type": "matched",
                        "match_id": mid,
                        "questions": questions,
                        "started_at": now.isoformat(),
                        "duration": 60,
                        "finished": False,
                        "opponent_progress": {"index": 0, "score": 0, "done": False},
                    }
                    for u in (uid, opponent):
                        ws = _PVP_WS.get(u)
                        if ws is not None:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                else:
                    _PVP_WS_WAITING.add(uid)
                    await websocket.send_json({"type": "searching"})

            elif typ == "progress":
                mid = _PVP_WS_USER_MATCH.get(uid)
                match = _PVP_WS_MATCHES.get(mid) if mid else None
                if not match or match.get("finished"):
                    continue
                match["progress"][uid] = {
                    "index": int(data.get("index", 0)),
                    "score": int(data.get("score", 0)),
                    "done": bool(data.get("done", False)),
                }
                opp_uid = [u for u in match["users"] if u != uid][0]
                opp_ws = _PVP_WS.get(opp_uid)
                if opp_ws is not None:
                    try:
                        await opp_ws.send_json({
                            "type": "opponent_progress",
                            "index": match["progress"][uid]["index"],
                            "score": match["progress"][uid]["score"],
                            "done": match["progress"][uid]["done"],
                        })
                    except Exception:
                        pass

                if match["progress"][uid].get("done"):
                    await _ws_finish(match, session)

            elif typ == "time_up":
                mid = _PVP_WS_USER_MATCH.get(uid)
                match = _PVP_WS_MATCHES.get(mid) if mid else None
                if match and not match.get("finished"):
                    await _ws_finish(match, session)

            elif typ == "cancel":
                _PVP_WS_WAITING.discard(uid)
                await websocket.send_json({"type": "cancelled"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        _PVP_WS.pop(uid, None)
        _PVP_WS_WAITING.discard(uid)
        mid = _PVP_WS_USER_MATCH.get(uid)
        if mid:
            match = _PVP_WS_MATCHES.get(mid)
            if match and not match.get("finished"):
                opp_uid = [u for u in match["users"] if u != uid][0]
                opp_ws = _PVP_WS.get(opp_uid)
                if opp_ws is not None:
                    try:
                        await opp_ws.send_json({"type": "opponent_left"})
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# Начисление XP (спринт, PvP и т.п.)
# ---------------------------------------------------------------------------
class XpAwardIn(BaseModel):
    amount: int
    reason: str = ""


@router.post("/xp/award")
async def award_xp(
    data: XpAwardIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    from app.services.gamification import add_xp, touch_streak, update_daily_tasks

    amount = max(0, int(data.amount or 0))
    if amount:
        add_xp(user, amount)
        await touch_streak(session, user, xp=amount)
        if data.reason == "pvp_win":
            await update_daily_tasks(session, user, battle_done=True)
        else:
            await update_daily_tasks(session, user, card_done=True)
        await session.commit()
    return {"xp": user.xp or 0, "level": user.level or 1, "amount": amount}


class SprintFinishIn(BaseModel):
    score: int = 0


@router.post("/sprint/finish")
async def sprint_finish(
    data: SprintFinishIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    from app.services.gamification import add_xp, touch_streak, update_daily_tasks

    amount = max(0, int(data.score or 0))
    if amount:
        add_xp(user, amount)
        await touch_streak(session, user, xp=amount)
        await update_daily_tasks(session, user, speed_done=True)
        await session.commit()
    return {"xp": user.xp or 0, "level": user.level or 1, "amount": amount}


@router.get("/profile")
async def profile(
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)

    total = (
        await session.execute(
            select(func.count()).select_from(UserAnswer).where(UserAnswer.user_id == user.id)
        )
    ).scalar_one()
    correct = (
        await session.execute(
            select(func.count()).select_from(UserAnswer).where(
                UserAnswer.user_id == user.id, UserAnswer.is_correct.is_(True)
            )
        )
    ).scalar_one()
    accuracy = round(correct / total * 100, 1) if total else 0.0

    rank = (
        await session.execute(
            select(func.count()).select_from(User).where(User.xp > (user.xp or 0))
        )
    ).scalar_one() + 1

    words = (
        await session.execute(
            select(func.count()).select_from(VocabProgress).where(
                VocabProgress.user_id == user.id, VocabProgress.mastery >= 3
            )
        )
    ).scalar_one()

    from app.services.gamification import xp_for_level

    lvl = user.level or 1
    base_xp = xp_for_level(lvl)
    next_xp = xp_for_level(lvl + 1)
    progress_xp = max(0, (user.xp or 0) - base_xp)
    need_xp = max(1, next_xp - base_xp)
    return {
        "user_id": user.id,
        "username": user.name or user.username or "Гость",
        "streak": user.streak or 0,
        "accuracy": accuracy,
        "rank": rank,
        "words": words,
        "level": lvl,
        "xp": user.xp or 0,
        "xp_current_level": progress_xp,
        "xp_for_next_level": need_xp,
    }
