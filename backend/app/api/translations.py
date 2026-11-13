"""База переводов: список, экспорт CSV/JSON."""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.base import get_session
from app.models import Fragment, TranslationRecord, User

router = APIRouter(prefix="/translations", tags=["translations"])


async def _to_row(tr: TranslationRecord, frag: Fragment | None, pair_code: str | None) -> dict:
    source_coords = tr.source_coords
    if source_coords:
        try:
            coords = json.loads(source_coords)
            src = coords if isinstance(coords, dict) else None
        except Exception:
            src = None
    else:
        src = None
    return {
        "id": tr.id,
        "fragment_id": tr.fragment_id,
        "text_ba": tr.text_ba,
        "lang_pair": tr.lang_pair,
        "translation": tr.translation,
        "source_coords": source_coords,
        "source": src,
        "confirmed_count": tr.confirmed_count,
        "status": tr.status,
        "updated_at": tr.updated_at,
    }


@router.get("", response_model=list[dict])
async def list_translations(
    lang_pair: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(TranslationRecord)
    if lang_pair:
        query = query.where(TranslationRecord.lang_pair == lang_pair)
    if status:
        query = query.where(TranslationRecord.status == status)
    if q:
        query = query.where(
            TranslationRecord.text_ba.contains(q) | TranslationRecord.translation.contains(q)
        )
    rows = (await session.execute(query.offset(offset).limit(limit))).all()
    out = []
    for tr in rows:
        frag = await session.get(Fragment, tr.fragment_id)
        out.append(await _to_row(tr, frag, tr.lang_pair))
    return out


@router.get("/export/csv")
async def export_csv(
    lang_pair: Optional[str] = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = select(TranslationRecord)
    if lang_pair:
        query = query.where(TranslationRecord.lang_pair == lang_pair)
    rows = (await session.execute(query)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "fragment_id", "text_ba", "lang_pair", "translation", "source_coords", "confirmed_count", "status"])
    for r in rows:
        w.writerow([r.id, r.fragment_id, r.text_ba, r.lang_pair, r.translation, r.source_coords, r.confirmed_count, r.status])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="translations.csv"'},
    )


@router.get("/export/json")
async def export_json(
    lang_pair: Optional[str] = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    query = select(TranslationRecord)
    if lang_pair:
        query = query.where(TranslationRecord.lang_pair == lang_pair)
    rows = (await session.execute(query)).all()
    return [
        {
            "id": r.id,
            "fragment_id": r.fragment_id,
            "text_ba": r.text_ba,
            "lang_pair": r.lang_pair,
            "translation": r.translation,
            "source_coords": r.source_coords,
            "confirmed_count": r.confirmed_count,
            "status": r.status,
        }
        for r in rows
    ]
