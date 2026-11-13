"""Контент: импорт датасета, статистика базы, спорные случаи для экспертов."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SessionFactory, get_session
from app.models import Fragment, LangPair, Translation
from app.schemas import ImportStatus
from app.services.agreement import disputed_list
from app.services.content_import import content_stats, import_phrasebooks

logger = logging.getLogger("bashkar.content")
router = APIRouter(prefix="/content", tags=["content"])

_state: ImportStatus = ImportStatus()


@router.post("/import", response_model=ImportStatus)
async def trigger_import(background_tasks: BackgroundTasks):
    """Запускает импорт датасета в фоне."""
    if _state.running:
        return _state
    _state.running = True
    _state.finished = False
    _state.error = None

    async def _run():
        try:
            async with SessionFactory() as session:
                result = await import_phrasebooks(session)
            _state.total_rows = result.get("total_rows", 0)
            _state.created_fragments = result.get("created_fragments", 0)
            _state.created_translations = result.get("created_translations", 0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Import failed")
            _state.error = str(exc)
        finally:
            _state.running = False
            _state.finished = True

    background_tasks.add_task(_run)
    return _state


@router.get("/import/status", response_model=ImportStatus)
async def import_status():
    return _state


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    return await content_stats(session)


@router.get("/disputed")
async def disputed(limit: int = Query(100, ge=1, le=500), session: AsyncSession = Depends(get_session)):
    """Спорные переводы — список для экспертов (УФИЦ РАН)."""
    return await disputed_list(session, limit)


@router.get("/fragments")
async def list_fragments(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    lang_pair: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        Translation.__table__.select()
        .join(Fragment.__table__, Fragment.id == Translation.fragment_id)
        .select_from(Fragment)
    )
    rows_query = select(Fragment).order_by(Fragment.id).limit(limit).offset(offset)
    if lang_pair:
        pair = (
            await session.execute(select(LangPair).where(LangPair.code == lang_pair))
        ).scalar_one_or_none()
        if pair is None:
            raise HTTPException(404, "Пара не найдена")
        rows_query = (
            select(Fragment)
            .join(Translation, Translation.fragment_id == Fragment.id)
            .where(Translation.lang_pair_id == pair.id)
            .order_by(Fragment.id)
            .limit(limit)
            .offset(offset)
        )
    rows = (await session.execute(rows_query)).scalars().all()
    return [
        {
            "id": f.id,
            "fragment_id": f.fragment_id,
            "text_ba": f.text_ba,
            "source": f.source,
            "difficulty": f.difficulty,
        }
        for f in rows
    ]


@router.post("/translations/{translation_id}/resolve")
async def resolve_translation(
    translation_id: int,
    correct_text: str,
    session: AsyncSession = Depends(get_session),
):
    """Эксперт утверждает вариант перевода вручную."""
    tr = await session.get(Translation, translation_id)
    if not tr:
        raise HTTPException(404, "Перевод не найден")
    tr.translation = correct_text
    tr.status = "confirmed"
    tr.is_machine = False
    tr.confirmed_count = max(1, tr.confirmed_count)
    await session.commit()
    return {"ok": True, "translation_id": translation_id, "status": tr.status}
