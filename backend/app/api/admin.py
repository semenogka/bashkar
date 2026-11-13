"""Админ-панель: статистика платформы и пересидирование демо-данных."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.db.base import get_session
from app.models import ExpertReview, Fragment, Translation, User, UserAnswer

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def stats(
    session: AsyncSession = Depends(get_session),
    user=Depends(require_role("admin")),
) -> dict:
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    fragments = (await session.execute(select(func.count()).select_from(Fragment))).scalar_one()
    translations = (await session.execute(select(func.count()).select_from(Translation))).scalar_one()
    confirmed = (
        await session.execute(
            select(func.count()).select_from(Translation).where(Translation.status == "confirmed")
        )
    ).scalar_one()
    expert_pending = (
        await session.execute(
            select(func.count()).select_from(ExpertReview).where(ExpertReview.status == "pending")
        )
    ).scalar_one()
    answers = (await session.execute(select(func.count()).select_from(UserAnswer))).scalar_one()
    return {
        "users": users,
        "fragments": fragments,
        "translations": translations,
        "confirmed": confirmed,
        "expert_pending": expert_pending,
        "answers": answers,
    }


@router.post("/reseed")
async def reseed(
    session: AsyncSession = Depends(get_session),
    user=Depends(require_role("admin")),
) -> dict:
    from app.services.lms_seeding import seed_all

    await seed_all(session)
    return {"ok": True}
