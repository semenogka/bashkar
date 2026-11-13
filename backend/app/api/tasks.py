"""Ежедневные задания: /api/tasks/daily + история."""
from __future__ import annotations

import datetime as dt
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.base import get_session
from app.models import Fragment, LangPair, Source, TaskAssignment, User

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _corrupt(text: str) -> str:
    replacements = {
        "моя": "твоя", "мой": "твой", "лучший": "худший",
        "близкий": "далёкий", "родная": "чужая", "будущее": "прошлое",
        "большое": "малое", "самый": "самый", "основа": "преграда",
    }
    words = text.split()
    out = []
    for w in words:
        low = w.lower().strip(".,!?")
        if low in replacements and random.random() < 0.4:
            w = w.replace(low, replacements[low])
        out.append(w)
    if len(out) > 3 and random.random() < 0.3:
        del out[random.randrange(len(out))]
    return " ".join(out)


async def _task_payload(assign: TaskAssignment, frag: Fragment, pair: LangPair, session: AsyncSession) -> dict:
    source = None
    if frag.source_id:
        source = await session.get(Source, frag.source_id)
    return {
        "assignment_id": assign.id,
        "fragment": {
            "id": frag.id,
            "source_id": frag.source_id,
            "text_ba": frag.text_ba,
            "auto_translation": frag.auto_translation or "",
            "lang_pair": frag.lang_pair or pair.code,
            "order_index": frag.order_index or 0,
            "source": (
                {
                    "id": source.id,
                    "title": source.title,
                    "source_type": source.source_type,
                    "author": source.author,
                    "chapter": source.chapter,
                    "time_start": source.time_start,
                    "time_end": source.time_end,
                }
                if source
                else None
            ),
        },
        "variant_translation": assign.variant_translation,
        "is_corrupted": assign.is_corrupted,
    }


@router.get("/daily")
async def daily_task(
    lang_pair: str = "ba-ru",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    today = dt.date.today()
    existing = (
        await session.execute(
            select(TaskAssignment).where(
                TaskAssignment.user_id == user.id,
                TaskAssignment.assigned_date == today,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        frag = await session.get(Fragment, existing.fragment_id)
        if frag is None:
            raise HTTPException(404, "Fragment not found")
        pair = (
            await session.execute(select(LangPair).where(LangPair.code == lang_pair))
        ).scalar_one_or_none()
        payload = await _task_payload(existing, frag, pair, session)
        payload["assignment_id"] = existing.id
        payload["variant_translation"] = existing.variant_translation
        payload["is_corrupted"] = existing.is_corrupted
        return payload

    pair = (
        await session.execute(select(LangPair).where(LangPair.code == lang_pair))
    ).scalar_one_or_none()
    if pair is None:
        raise HTTPException(404, "Language pair not found")
    frags = (
        (await session.execute(select(Fragment).where(Fragment.lang_pair == lang_pair)))
    ).scalars().all()
    if not frags:
        raise HTTPException(404, "No fragments available")
    frag = random.choice(list(frags))
    is_corrupted = random.random() < 0.4
    variant = _corrupt(frag.auto_translation) if is_corrupted else (frag.auto_translation or "")
    assign = TaskAssignment(
        user_id=user.id,
        fragment_id=frag.id,
        variant_translation=variant,
        is_corrupted=is_corrupted,
        assigned_date=today,
    )
    session.add(assign)
    await session.flush()
    return await _task_payload(assign, frag, pair, session)


@router.get("/history")
async def task_history(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    assigns = (
        await session.execute(
            select(TaskAssignment)
            .where(TaskAssignment.user_id == user.id)
            .order_by(TaskAssignment.created_at.desc())
            .limit(30)
        )
    ).scalars().all()
    out = []
    for a in assigns:
        frag = await session.get(Fragment, a.fragment_id)
        out.append({
            "assignment_id": a.id,
            "fragment_id": a.fragment_id,
            "text_ba": frag.text_ba if frag else None,
            "variant": a.variant_translation,
            "is_corrupted": a.is_corrupted,
            "answered": a.answered,
            "date": a.assigned_date,
        })
    return out
