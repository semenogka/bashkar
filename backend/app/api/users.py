"""Пользователи, профиль, классы и школы."""
from __future__ import annotations

import random
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import Badge, ClassGroup, LangPair, School, User, UserBadge
from app.schemas import (
    BadgeOut,
    ClassCreate,
    ClassOut,
    JoinClass,
    LangPairChange,
    LangPairOut,
    UserCreate,
    UserOut,
    UserProfileOut,
)
from app.services.gamification import refill_hearts, xp_progress

router = APIRouter(tags=["users"])


def _invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def _user_payload(user: User, session: AsyncSession) -> dict:
    lvl, in_level, needed = xp_progress(user.xp or 0)
    pair_code = None
    if user.lang_pair_id:
        pair = await session.get(LangPair, user.lang_pair_id)
        pair_code = pair.code if pair else None
    return {
        "id": user.id,
        "external_id": user.external_id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "avatar": user.avatar,
        "lang_pair_id": user.lang_pair_id,
        "lang_pair_code": pair_code,
        "school_id": user.school_id,
        "class_id": user.class_id,
        "xp": user.xp or 0,
        "level": lvl,
        "league": user.league or "bronze",
        "streak": user.streak or 0,
        "longest_streak": user.longest_streak or 0,
        "gems": user.gems or 0,
        "hearts": user.hearts,
        "hearts_updated_at": user.hearts_updated_at,
        "daily_goal": user.daily_goal or 20,
        "xp_in_level": in_level,
        "xp_needed": needed,
        "created_at": user.created_at,
    }


async def session_pair(pair_id: int) -> LangPair | None:
    """Совместимость-хелпер: пара по id в отдельной сессии."""
    from app.db.base import SessionFactory

    async with SessionFactory() as s:
        return await s.get(LangPair, pair_id)


@router.get("/lang-pairs", response_model=list[LangPairOut])
async def list_lang_pairs(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(select(LangPair).where(LangPair.enabled.is_(True)).order_by(LangPair.id))
    ).scalars().all()
    return [
        LangPairOut(
            id=p.id,
            code=p.code,
            source_lang=p.source_lang,
            target_lang=p.target_lang,
            native_label=p.native_label,
            enabled=p.enabled,
        )
        for p in rows
    ]


@router.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    if payload.external_id:
        existing = (
            await session.execute(select(User).where(User.external_id == payload.external_id))
        ).scalar_one_or_none()
        if existing:
            return UserOut(**await _user_payload(existing, session))

    pair_id = None
    if payload.lang_pair_code:
        pair = (
            await session.execute(
                select(LangPair).where(LangPair.code == payload.lang_pair_code)
            )
        ).scalar_one_or_none()
        if pair:
            pair_id = pair.id

    school_id = class_id = None
    if payload.school_name:
        school = School(name=payload.school_name)
        session.add(school)
        await session.flush()
        school_id = school.id
    if payload.class_name:
        klass = ClassGroup(name=payload.class_name, school_id=school_id, invite_code=_invite_code())
        session.add(klass)
        await session.flush()
        class_id = klass.id

    user = User(
        external_id=payload.external_id,
        name=payload.name or "Ученик",
        username=payload.username,
        role=payload.role,
        avatar=payload.avatar,
        lang_pair_id=pair_id,
        school_id=school_id,
        class_id=class_id,
        hearts=5,
        hearts_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserOut(**await _user_payload(user, session))


@router.get("/users/{user_id}", response_model=UserProfileOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    refill_hearts(user)
    await session.commit()

    badges = (
        await session.execute(
            select(Badge).join(UserBadge, UserBadge.badge_code == Badge.code)
            .where(UserBadge.user_id == user_id)
        )
    ).scalars().all()

    from app.api.stats import build_user_stats

    stats = await build_user_stats(session, user)
    data = await _user_payload(user, session)
    data["badges"] = [BadgeOut.model_validate(b) for b in badges]
    data["stats"] = stats
    return UserProfileOut(**data)


@router.patch("/users/{user_id}/lang-pair")
async def change_lang_pair(
    user_id: int, payload: LangPairChange, session: AsyncSession = Depends(get_session)
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    pair = (
        await session.execute(select(LangPair).where(LangPair.code == payload.lang_pair_code))
    ).scalar_one_or_none()
    if not pair:
        raise HTTPException(404, "Языковая пара не найдена")
    user.lang_pair_id = pair.id
    await session.commit()
    return {"ok": True, "lang_pair_id": pair.id}


@router.patch("/users/{user_id}/daily-goal")
async def change_daily_goal(
    user_id: int, goal: int = 20, session: AsyncSession = Depends(get_session)
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.daily_goal = max(5, min(100, goal))
    await session.commit()
    return {"ok": True, "daily_goal": user.daily_goal}


@router.post("/users/{user_id}/hearts/refill")
async def refill(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    changed = refill_hearts(user)
    await session.commit()
    return {"ok": True, "changed": changed, "hearts": user.hearts}


@router.post("/classes", response_model=ClassOut)
async def create_class(payload: ClassCreate, session: AsyncSession = Depends(get_session)):
    school_id = None
    if payload.school_name:
        school = (
            await session.execute(select(School).where(School.name == payload.school_name))
        ).scalar_one_or_none()
        if school is None:
            school = School(name=payload.school_name)
            session.add(school)
            await session.flush()
        school_id = school.id
    klass = ClassGroup(
        name=payload.name,
        school_id=school_id,
        teacher_id=payload.teacher_id,
        invite_code=_invite_code(),
    )
    session.add(klass)
    await session.commit()
    await session.refresh(klass)
    school_name = None
    if school_id:
        school = await session.get(School, school_id)
        school_name = school.name if school else None
    return ClassOut(
        id=klass.id,
        name=klass.name,
        school_id=klass.school_id,
        school_name=school_name,
        invite_code=klass.invite_code,
        student_count=0,
    )


@router.get("/classes", response_model=list[ClassOut])
async def list_classes(session: AsyncSession = Depends(get_session)):
    classes = (await session.execute(select(ClassGroup))).scalars().all()
    result = []
    for klass in classes:
        count = (
            await session.execute(
                select(func.count()).select_from(User).where(User.class_id == klass.id)
            )
        ).scalar_one()
        school_name = None
        if klass.school_id:
            school = await session.get(School, klass.school_id)
            school_name = school.name if school else None
        result.append(ClassOut(
            id=klass.id, name=klass.name, school_id=klass.school_id,
            school_name=school_name, invite_code=klass.invite_code, student_count=count,
        ))
    return result


@router.post("/users/{user_id}/join-class")
async def join_class(user_id: int, payload: JoinClass, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    klass = (
        await session.execute(
            select(ClassGroup).where(ClassGroup.invite_code == payload.invite_code)
        )
    ).scalar_one_or_none()
    if not klass:
        raise HTTPException(404, "Класс не найден")
    user.class_id = klass.id
    user.school_id = klass.school_id
    await session.commit()
    return {"ok": True, "class_id": klass.id}
