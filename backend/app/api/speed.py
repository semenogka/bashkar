"""Режим «Быстрый перевод»: 60 секунд на максимум правильных переводов."""
from __future__ import annotations

import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import Fragment, LangPair, SpeedRun, Translation, User, UserAnswer
from app.schemas import BadgeOut, SpeedRunIn, SpeedRunOut
from app.services.gamification import (
    add_xp,
    award_badges,
    touch_streak,
    update_daily_tasks,
)

router = APIRouter(prefix="/speed", tags=["speed"])


@router.get("/cards")
async def speed_cards(
    user_id: int,
    lang_pair_id: int | None = None,
    limit: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """Выдаёт пачку карточек для таймера (без ловушек — только скорость)."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    pair_id = lang_pair_id or user.lang_pair_id
    if not pair_id:
        raise HTTPException(400, "Не выбрана языковая пара")
    pair = await session.get(LangPair, pair_id)
    if not pair:
        raise HTTPException(404, "Пара не найдена")

    rows = (
        await session.execute(
            select(Fragment, Translation)
            .join(Translation, Translation.fragment_id == Fragment.id)
            .where(Translation.lang_pair_id == pair.id)
            .limit(limit * 3)
        )
    ).all()
    if not rows:
        raise HTTPException(404, "Нет фрагментов")
    picked = random.sample(rows, min(limit, len(rows)))
    return [
        {
            "fragment_id": frag.id,
            "text_ba": frag.text_ba,
            "translation": tr.translation,
            "lang_pair": pair.code,
            "lang_pair_id": pair.id,
        }
        for frag, tr in picked
    ]


@router.post("/run", response_model=SpeedRunOut)
async def finish_run(payload: SpeedRunIn, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, payload.user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    run = SpeedRun(
        user_id=user.id,
        lang_pair_id=payload.lang_pair_id,
        score=max(0, payload.score),
        correct=max(0, payload.correct),
        total=max(0, payload.total),
        duration=payload.duration,
        best_streak=max(0, payload.best_streak),
    )
    session.add(run)

    xp_gained = payload.score
    if xp_gained:
        add_xp(user, xp_gained, session, reason="speed")
        await touch_streak(session, user, xp=xp_gained)

    await update_daily_tasks(session, user, speed_done=True)
    await session.commit()

    new_badges = await award_badges(session, user)
    await session.commit()
    await session.refresh(run)

    return SpeedRunOut(
        id=run.id,
        score=run.score,
        correct=run.correct,
        total=run.total,
        best_streak=run.best_streak,
        duration=run.duration,
        xp_gained=xp_gained,
        new_badges=[BadgeOut.model_validate(b) for b in new_badges],
        created_at=run.created_at,
    )


@router.get("/leaderboard")
async def speed_leaderboard(limit: int = 50, session: AsyncSession = Depends(get_session)):
    best = (
        await session.execute(
            select(
                SpeedRun.user_id,
                func.max(SpeedRun.score).label("best_score"),
                func.max(SpeedRun.best_streak).label("best_streak"),
            )
            .group_by(SpeedRun.user_id)
            .order_by(func.max(SpeedRun.score).desc())
            .limit(limit)
        )
    ).all()
    result = []
    for rank, (uid, score, streak) in enumerate(best, start=1):
        user = await session.get(User, uid)
        if not user:
            continue
        result.append({
            "rank": rank,
            "user_id": uid,
            "name": user.name or f"Ученик {uid}",
            "avatar": user.avatar,
            "best_score": int(score or 0),
            "best_streak": int(streak or 0),
            "level": user.level,
        })
    return result
