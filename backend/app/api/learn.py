"""Обучение: карточки, ответы, дневная цель и ежедневные задания."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import (
    DailyTask,
    Fragment,
    LangPair,
    StreakLog,
    Translation,
    User,
    UserAnswer,
    VocabProgress,
)
from app.schemas import (
    AnswerIn,
    AnswerOut,
    BadgeOut,
    CardOut,
    DailyOut,
    DailyTaskOut,
)
from app.services.agreement import normalize, reconcile
from app.services.gamification import (
    add_xp,
    award_badges,
    note_answer_streak,
    refill_hearts,
    spend_heart,
    touch_streak,
    update_daily_tasks,
)

router = APIRouter(tags=["learn"])


def _make_trap(correct: str) -> str | None:
    """Готовит намеренно неверный вариант перевода (как в Duolingo)."""
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


async def _pick_fragment(session: AsyncSession, user: User, pair: LangPair) -> tuple[Fragment, Translation] | None:
    """Выбирает фрагмент: сначала повторение (по времени), потом новый."""
    base = (
        select(Translation, Fragment)
        .join(Fragment, Fragment.id == Translation.fragment_id)
        .where(Translation.lang_pair_id == pair.id)
    )

    # 1) Повторение: у которых подошёл next_review
    now = datetime.utcnow()
    review = (
        await session.execute(
            select(VocabProgress)
            .where(
                VocabProgress.user_id == user.id,
                VocabProgress.lang_pair_id == pair.id,
                VocabProgress.next_review.is_not(None),
                VocabProgress.next_review <= now,
            )
            .order_by(VocabProgress.next_review)
            .limit(20)
        )
    ).scalars().all()
    if review:
        frag_id = random.choice(review).fragment_id
        row = (
            await session.execute(base.where(Fragment.id == frag_id))
        ).first()
        if row:
            return row[1], row[0]

    # 2) Новые фрагменты
    seen = (
        await session.execute(
            select(VocabProgress.fragment_id).where(VocabProgress.user_id == user.id)
        )
    ).scalars().all()
    stmt = base
    if seen:
        stmt = stmt.where(Fragment.id.notin_(list(seen)))
    rows = (await session.execute(stmt.limit(300))).all()
    if not rows:
        rows = (await session.execute(base.limit(300))).all()
    if not rows:
        return None
    tr, frag = random.choice(rows)
    return frag, tr


async def _card_payload(frag: Fragment, tr: Translation, pair: LangPair, user: User,
                        *, trap: bool = True) -> CardOut:
    correct = tr.translation
    shown = correct
    is_trap = False
    options: list[str] = []
    if trap:
        candidate = _make_trap(correct)
        if candidate and candidate != correct:
            shown = candidate
            is_trap = True
            # Варианты ответа: правильный + ошибочный (как в Duolingo — выбор из 3)
            options = [correct, candidate]
            extra = _make_trap(correct)
            if extra and extra not in options:
                options.append(extra)
            random.shuffle(options)
    if not options:
        options = [correct]
    progress = await _session_progress(user.id, frag.id, pair.id)
    return CardOut(
        fragment_id=frag.id,
        external_id=frag.fragment_id,
        text_ba=frag.text_ba,
        source=frag.source,
        difficulty=frag.difficulty,
        lang_pair=pair.code,
        lang_pair_id=pair.id,
        translation=shown,
        is_trap=is_trap,
        options=options,
        mastery=progress.mastery if progress else 0,
    )


_progress_cache: dict[tuple[int, int, int], VocabProgress] = {}


async def _session_progress(user_id: int, fragment_id: int, pair_id: int) -> VocabProgress | None:
    return _progress_cache.get((user_id, fragment_id, pair_id))


@router.get("/cards/next", response_model=CardOut)
async def next_card(
    user_id: int,
    lang_pair_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    pair_id = lang_pair_id or user.lang_pair_id
    if not pair_id:
        raise HTTPException(400, "Не выбрана языковая пара")
    pair = await session.get(LangPair, pair_id)
    if not pair:
        raise HTTPException(404, "Пара не найдена")

    picked = await _pick_fragment(session, user, pair)
    if picked is None:
        raise HTTPException(404, "Нет фрагментов — выполните импорт датасета")
    frag, tr = picked

    progress = (
        await session.execute(
            select(VocabProgress).where(
                VocabProgress.user_id == user_id,
                VocabProgress.fragment_id == frag.id,
                VocabProgress.lang_pair_id == pair.id,
            )
        )
    ).scalar_one_or_none()
    _progress_cache[(user_id, frag.id, pair.id)] = progress  # type: ignore[assignment]
    return await _card_payload(frag, tr, pair, user)


@router.post("/answers", response_model=AnswerOut)
async def submit_answer(payload: AnswerIn, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, payload.user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    frag = await session.get(Fragment, payload.fragment_id)
    if not frag:
        raise HTTPException(404, "Фрагмент не найден")
    pair = await session.get(LangPair, payload.lang_pair_id)
    if not pair:
        raise HTTPException(404, "Пара не найдена")

    tr = (
        await session.execute(
            select(Translation).where(
                Translation.fragment_id == frag.id,
                Translation.lang_pair_id == pair.id,
            )
        )
    ).scalar_one_or_none()
    correct_answer = tr.translation if tr else None
    is_correct = bool(correct_answer) and normalize(payload.answer) == normalize(correct_answer)

    session.add(UserAnswer(
        user_id=user.id,
        fragment_id=frag.id,
        lang_pair_id=pair.id,
        answer=payload.answer,
        is_correct=is_correct,
        time_spent=payload.time_spent,
        mode=payload.mode,
    ))

    # --- Прогресс по слову (дерево навыков / повторения) ---
    progress = (
        await session.execute(
            select(VocabProgress).where(
                VocabProgress.user_id == user.id,
                VocabProgress.fragment_id == frag.id,
                VocabProgress.lang_pair_id == pair.id,
            )
        )
    ).scalar_one_or_none()
    if progress is None:
        progress = VocabProgress(user_id=user.id, fragment_id=frag.id, lang_pair_id=pair.id)
        session.add(progress)
    if is_correct:
        progress.correct_count = (progress.correct_count or 0) + 1
        progress.mastery = min(5, (progress.mastery or 0) + 1)
    else:
        progress.wrong_count = (progress.wrong_count or 0) + 1
        progress.mastery = max(0, (progress.mastery or 0) - 1)
    progress.last_seen = datetime.utcnow()
    progress.next_review = datetime.utcnow() + timedelta(
        days=[0, 1, 3, 7, 16, 35][min(progress.mastery, 5)]
    )
    _progress_cache[(user.id, frag.id, pair.id)] = progress  # type: ignore[assignment]

    # --- Сердца ---
    hearts_lost = False
    refill_hearts(user)
    if not is_correct and payload.mode == "normal":
        hearts_lost = spend_heart(user)

    # --- XP, серия, квесты ---
    xp_gained = 0
    streak_bonus = 0
    if is_correct:
        xp_gained = 10
        if payload.time_spent and payload.time_spent < 10:
            xp_gained += 5
        if payload.mode == "speed":
            xp_gained += 5
        streak_len = note_answer_streak(user, True)
        if streak_len > 0 and streak_len % 5 == 0:
            streak_bonus = 10
            xp_gained += streak_bonus
        add_xp(user, xp_gained)
    else:
        note_answer_streak(user, False)
    # Серия и дневной прогресс — за любую активность
    await touch_streak(session, user, xp=xp_gained)

    total = (
        await session.execute(
            select(func.count()).select_from(UserAnswer).where(UserAnswer.user_id == user.id)
        )
    ).scalar_one()
    correct_total = (
        await session.execute(
            select(func.count()).select_from(UserAnswer).where(
                UserAnswer.user_id == user.id, UserAnswer.is_correct.is_(True)
            )
        )
    ).scalar_one()
    accuracy = (correct_total / total * 100) if total else 0.0

    tasks = await update_daily_tasks(
        session, user, card_done=True, accuracy=accuracy
    )
    daily_progress = {
        t.code: {"progress": t.progress, "target": t.target, "completed": t.completed}
        for t in tasks
    }

    # --- Согласование перевода (большинство) ---
    if is_correct and tr is not None:
        await reconcile(session, frag.id, pair.id)

    await session.commit()

    # --- Бейджи ---
    new_badges = await award_badges(session, user)
    await session.commit()

    hint = None
    if not is_correct and correct_answer:
        hint = "Подсказка: начни с первых трёх букв"
    return AnswerOut(
        correct=is_correct,
        correct_translation=correct_answer,
        xp_gained=xp_gained + streak_bonus,
        hearts=user.hearts,
        hearts_lost=hearts_lost,
        level=user.level,
        xp=user.xp,
        streak=user.streak,
        streak_bonus=streak_bonus,
        new_badges=[BadgeOut.model_validate(b) for b in new_badges],
        daily_progress=daily_progress,
        mastery=progress.mastery,
        hint=hint,
    )


@router.get("/daily", response_model=DailyOut)
async def daily(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    today = date.today()
    # задачи дня только читаем — не создаём и не обновляем при простом просмотре
    tasks = (
        await session.execute(
            select(DailyTask).where(DailyTask.user_id == user_id, DailyTask.day == today)
        )
    ).scalars().all()
    log = (
        await session.execute(
            select(StreakLog).where(StreakLog.user_id == user_id, StreakLog.day == today)
        )
    ).scalar_one_or_none()
    return DailyOut(
        tasks=[DailyTaskOut(
            id=t.id, code=t.code, title=t.title, progress=t.progress,
            target=t.target, xp_reward=t.xp_reward, completed=t.completed,
        ) for t in tasks],
        cards_done_today=log.cards_done if log else 0,
        daily_goal=user.daily_goal,
        streak=user.streak,
        hearts=user.hearts,
        xp=user.xp,
        level=user.level,
    )
