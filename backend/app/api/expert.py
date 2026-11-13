"""Экспертная проверка спорных переводов: /api/expert/reviews."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.db.base import get_session
from app.models import ExpertReview, Fragment, TranslationRecord, User

router = APIRouter(prefix="/expert", tags=["expert"])


class ExpertResolve(BaseModel):
    translation: str
    status: str = "confirmed"


@router.get("/reviews")
async def list_reviews(
    status: str = "pending",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("expert", "admin")),
) -> list[dict]:
    query = select(ExpertReview).order_by(ExpertReview.created_at.desc())
    if status:
        query = query.where(ExpertReview.status == status)
    rows = (await session.execute(query)).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "fragment_id": r.fragment_id,
            "lang_pair": r.lang_pair,
            "candidates": r.candidates,
            "status": r.status,
            "resolution": r.resolution,
            "expert_id": r.expert_id,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        })
    return out


@router.post("/reviews/{review_id}/resolve")
async def resolve_review(
    review_id: int,
    data: ExpertResolve,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("expert", "admin")),
) -> dict:
    review = (
        await session.execute(select(ExpertReview).where(ExpertReview.id == review_id))
    ).scalar_one_or_none()
    if not review:
        raise HTTPException(404, "Review not found")

    review.status = "resolved"
    review.resolution = data.translation
    review.expert_id = user.id
    review.resolved_at = datetime.utcnow()

    tr = (
        await session.execute(
            select(TranslationRecord).where(TranslationRecord.fragment_id == review.fragment_id)
        )
    ).scalar_one_or_none()
    if tr is None:
        frag = await session.get(Fragment, review.fragment_id)
        if frag is None:
            raise HTTPException(404, "Fragment not found")
        tr = TranslationRecord(
            fragment_id=frag.id,
            text_ba=frag.text_ba,
            lang_pair=review.lang_pair,
            translation=data.translation,
            status=data.status,
            confirmed_count=0,
        )
        session.add(tr)
    else:
        tr.translation = data.translation
        tr.status = data.status
        tr.updated_at = datetime.utcnow()

    await session.commit()
    return {"ok": True}
