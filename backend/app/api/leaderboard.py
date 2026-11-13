"""Рейтинги: игроки, классы, школы, скорость."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import ClassGroup, Duel, School, SpeedRun, User, UserAnswer
from app.schemas import GroupRow, LeaderboardRow

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/users", response_model=list[LeaderboardRow])
async def users_leaderboard(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(select(User).order_by(User.xp.desc()).limit(limit))
    ).scalars().all()
    result = []
    for rank, user in enumerate(rows, start=1):
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
        best_speed = (
            await session.execute(
                select(func.max(SpeedRun.score)).where(SpeedRun.user_id == user.id)
            )
        ).scalar_one()
        wins = (
            await session.execute(
                select(func.count()).select_from(Duel).where(Duel.winner_id == user.id)
            )
        ).scalar_one()
        result.append(LeaderboardRow(
            rank=rank,
            user_id=user.id,
            name=user.name or f"Ученик {user.id}",
            avatar=user.avatar,
            xp=user.xp or 0,
            level=user.level or 1,
            league=user.league or "bronze",
            streak=user.streak or 0,
            accuracy=round(correct / total * 100, 1) if total else 0.0,
            best_speed=int(best_speed or 0),
            wins=int(wins),
        ))
    return result


@router.get("/classes", response_model=list[GroupRow])
async def classes_leaderboard(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(
                ClassGroup.id,
                ClassGroup.name,
                School.name,
                func.count(User.id),
                func.coalesce(func.sum(User.xp), 0),
            )
            .join(User, User.class_id == ClassGroup.id, isouter=True)
            .join(School, School.id == ClassGroup.school_id, isouter=True)
            .group_by(ClassGroup.id, ClassGroup.name, School.name)
            .order_by(func.coalesce(func.sum(User.xp), 0).desc())
            .limit(limit)
        )
    ).all()
    result = []
    for rank, (cid, name, school_name, students, xp) in enumerate(rows, start=1):
        result.append(GroupRow(
            rank=rank, id=cid, name=name, school_name=school_name,
            xp=int(xp or 0), students=int(students or 0),
        ))
    return result


@router.get("/schools", response_model=list[GroupRow])
async def schools_leaderboard(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(
                School.id,
                School.name,
                func.count(User.id),
                func.coalesce(func.sum(User.xp), 0),
            )
            .join(User, User.school_id == School.id, isouter=True)
            .group_by(School.id, School.name)
            .order_by(func.coalesce(func.sum(User.xp), 0).desc())
            .limit(limit)
        )
    ).all()
    return [
        GroupRow(rank=rank, id=sid, name=name, school_name=name,
                 xp=int(xp or 0), students=int(students or 0))
        for rank, (sid, name, students, xp) in enumerate(rows, start=1)
    ]


@router.get("/streak")
async def streak_leaderboard(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(User).order_by(User.streak.desc(), User.xp.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "rank": rank,
            "user_id": user.id,
            "name": user.name or f"Ученик {user.id}",
            "avatar": user.avatar,
            "streak": user.streak or 0,
            "longest_streak": user.longest_streak or 0,
            "xp": user.xp or 0,
        }
        for rank, user in enumerate(rows, start=1)
    ]
