"""API v1 для фронтенда «БЕЗТЕЛ» (Telegram Web App): хаб, чат, карточки, дейлик, состязания, профиль."""
from __future__ import annotations

import datetime as dt
import re
import random
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import (
    DailyChallenge,
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
@router.get("/hub/insight")
async def hub_insight(session: AsyncSession = Depends(get_session)) -> dict:
    card = await _random_card(session)
    if card is None:
        raise HTTPException(404, "Нет данных")
    frag, tr = card
    return {
        "bashkir_phrase": frag.text_ba,
        "translation_ru": tr.translation,
        "cultural_note": random.choice(CULTURAL_NOTES),
    }


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
@router.get("/daily/task")
async def daily_task(
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
        }

    return {
        "bashkir_text": frag.text_ba,
        "proposed_translation": challenge.proposed_translation,
        "is_corrupted": challenge.is_corrupted,
        "answered": False,
    }


class DailyCheckIn(BaseModel):
    bashkir_text: str
    original_proposed: str
    user_corrected: str


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


_VOTES = {"approve": 0, "reject": 0}


@router.post("/daily/vote")
async def daily_vote(data: DailyVoteIn) -> dict:
    _VOTES["approve" if data.approved else "reject"] += 1
    total = sum(_VOTES.values()) or 1
    return {
        "approvePercent": round(_VOTES["approve"] / total * 100),
        "rejectPercent": round(_VOTES["reject"] / total * 100),
    }


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

    return {
        "user_id": user.id,
        "username": user.name or user.username or "Гость",
        "streak": user.streak or 0,
        "accuracy": accuracy,
        "rank": rank,
        "words": words,
        "level": user.level or 1,
        "xp": user.xp or 0,
    }
