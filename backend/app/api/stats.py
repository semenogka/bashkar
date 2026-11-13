"""Статистика: по игроку, по платформе, каталог достижений."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import (
    Badge,
    ClassGroup,
    Duel,
    Fragment,
    School,
    SpeedRun,
    StreakLog,
    Translation,
    User,
    UserAnswer,
    UserBadge,
    VocabProgress,
)
from app.schemas import BadgeOut, PlatformStatsOut, UserStatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


async def build_user_stats(session: AsyncSession, user: User) -> dict:
    """Собирает статистику игрока (используется и в профиле)."""
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

    rows = (
        await session.execute(
            select(UserAnswer.created_at, UserAnswer.is_correct)
            .where(UserAnswer.user_id == user.id)
            .order_by(UserAnswer.created_at)
        )
    ).all()

    by_day: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    by_hour = [0] * 24
    for created_at, is_correct in rows:
        key = created_at.date().isoformat()
        by_day[key]["total"] += 1
        if is_correct:
            by_day[key]["correct"] += 1
        by_hour[created_at.hour] += 1

    accuracy_by_day = [
        {
            "date": day,
            "total": data["total"],
            "correct": data["correct"],
            "accuracy": round(data["correct"] / data["total"] * 100, 1) if data["total"] else 0.0,
        }
        for day, data in sorted(by_day.items())[-30:]
    ]

    vocab = (
        await session.execute(
            select(func.count()).select_from(VocabProgress).where(
                VocabProgress.user_id == user.id, VocabProgress.mastery >= 3
            )
        )
    ).scalar_one()

    today = date.today()
    today_log = (
        await session.execute(
            select(StreakLog).where(StreakLog.user_id == user.id, StreakLog.day == today)
        )
    ).scalar_one_or_none()

    speed_runs = (
        await session.execute(
            select(func.count()).select_from(SpeedRun).where(SpeedRun.user_id == user.id)
        )
    ).scalar_one()
    best_speed = (
        await session.execute(
            select(func.max(SpeedRun.score)).where(SpeedRun.user_id == user.id)
        )
    ).scalar_one()

    duels_total = (
        await session.execute(
            select(func.count()).select_from(Duel).where(
                (Duel.challenger_id == user.id) | (Duel.opponent_id == user.id)
            )
        )
    ).scalar_one()
    duels_won = (
        await session.execute(
            select(func.count()).select_from(Duel).where(Duel.winner_id == user.id)
        )
    ).scalar_one()

    badges = (
        await session.execute(
            select(Badge).join(UserBadge, UserBadge.badge_code == Badge.code)
            .where(UserBadge.user_id == user.id)
        )
    ).scalars().all()

    return {
        "user_id": user.id,
        "total_answers": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "xp": user.xp or 0,
        "level": user.level or 1,
        "league": user.league or "bronze",
        "streak": user.streak or 0,
        "longest_streak": user.longest_streak or 0,
        "hearts": user.hearts,
        "gems": user.gems or 0,
        "vocab_learned": vocab,
        "cards_today": today_log.cards_done if today_log else 0,
        "daily_goal": user.daily_goal or 20,
        "speed_runs": speed_runs,
        "best_speed": int(best_speed or 0),
        "duels_total": duels_total,
        "duels_won": duels_won,
        "accuracy_by_day": accuracy_by_day,
        "activity_by_hour": by_hour,
        "badges": [BadgeOut.model_validate(b).model_dump() for b in badges],
    }


@router.get("/me/{user_id}", response_model=UserStatsOut)
async def my_stats(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        return UserStatsOut(user_id=user_id)
    data = await build_user_stats(session, user)
    return UserStatsOut(**data)


@router.get("/platform", response_model=PlatformStatsOut)
async def platform_stats(session: AsyncSession = Depends(get_session)):
    async def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for cond in where:
            stmt = stmt.where(cond)
        return (await session.execute(stmt)).scalar_one()

    today = date.today()
    active_today = (
        await session.execute(
            select(func.count()).select_from(StreakLog).where(StreakLog.day == today)
        )
    ).scalar_one()

    return PlatformStatsOut(
        users=await count(User),
        schools=await count(School),
        classes=await count(ClassGroup),
        fragments=await count(Fragment),
        translations=await count(Translation),
        confirmed_translations=await count(Translation, Translation.status == "confirmed"),
        expert_review=await count(Translation, Translation.status == "expert_review"),
        answers=await count(UserAnswer),
        speed_runs=await count(SpeedRun),
        duels=await count(Duel),
        active_today=active_today,
    )


@router.get("/badges", response_model=list[BadgeOut])
async def badge_catalog(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Badge).order_by(Badge.code))).scalars().all()
    return [BadgeOut.model_validate(b) for b in rows]


@router.get("/vocabulary/{user_id}")
async def vocabulary(user_id: int, limit: int = 100, session: AsyncSession = Depends(get_session)):
    """Словарь пользователя: что освоено, что ждёт повторения."""
    rows = (
        await session.execute(
            select(VocabProgress)
            .where(VocabProgress.user_id == user_id)
            .order_by(VocabProgress.mastery.asc(), VocabProgress.last_seen.asc())
            .limit(limit)
        )
    ).scalars().all()
    out = []
    for vp in rows:
        frag = await session.get(Fragment, vp.fragment_id)
        if not frag:
            continue
        out.append({
            "fragment_id": frag.id,
            "external_id": frag.fragment_id,
            "text_ba": frag.text_ba,
            "mastery": vp.mastery,
            "correct_count": vp.correct_count,
            "wrong_count": vp.wrong_count,
            "next_review": vp.next_review,
        })
    return out
