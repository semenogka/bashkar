"""Справочники для фронтенда: источники, школы, классы, языковые пары."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import ClassGroup, LangPair, School, Source

router = APIRouter(tags=["misc"])


@router.get("/lang-pairs")
async def list_lang_pairs(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(LangPair).order_by(LangPair.id))).scalars().all()
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


@router.get("/schools")
async def list_schools(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(School).order_by(School.id))).scalars().all()
    return [{"id": s.id, "name": s.name} for s in rows]


@router.get("/classes")
async def list_classes(
    school_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(ClassGroup)
    if school_id:
        query = query.where(ClassGroup.school_id == school_id)
    rows = (await session.execute(query.order_by(ClassGroup.id))).scalars().all()
    return [{"id": c.id, "name": c.name, "school_id": c.school_id} for c in rows]


@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(Source).order_by(Source.id))).scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "source_type": s.source_type,
            "author": s.author,
            "chapter": s.chapter,
            "time_start": s.time_start,
            "time_end": s.time_end,
        }
        for s in rows
    ]
