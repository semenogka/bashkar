"""Нарезка текста на фрагменты: /api/fragments/split."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.db.base import get_session
from app.models import Fragment, Source, User

router = APIRouter(prefix="/fragments", tags=["fragments"])


class SplitRequest(BaseModel):
    source_id: int
    text: str
    lang_pair: str = "ba-ru"
    auto_translations: list[str] | None = None


@router.post("/split")
async def split_text(
    data: SplitRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("teacher", "admin")),
) -> dict:
    source = await session.get(Source, data.source_id)
    if source is None:
        raise HTTPException(404, "Source not found")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", data.text) if s.strip()]
    created: list[int] = []
    for i, sent in enumerate(sentences):
        auto = ""
        if data.auto_translations and i < len(data.auto_translations):
            auto = data.auto_translations[i]
        frag = Fragment(
            source_id=data.source_id,
            text_ba=sent,
            auto_translation=auto or "[автоперевод]",
            lang_pair=data.lang_pair,
            order_index=i,
            source=source.title,
            source_type=source.source_type,
        )
        session.add(frag)
        await session.flush()
        created.append(frag.id)
    await session.commit()
    return {"created": len(created), "fragment_ids": created}
