"""Чат-репетитор: LLM отвечает на башкирском, переводит, озвучивает и капает XP."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import User
from app.schemas import BadgeOut, ChatIn, ChatOut
from app.services.gamification import add_xp, award_badges, touch_streak, update_daily_tasks
from app.services.tutor import tutor_reply

logger = logging.getLogger("bashkar.chat")
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn, session: AsyncSession = Depends(get_session)):
    reply = await tutor_reply(payload.message, payload.history, payload.target_lang)
    text_ba = reply["text_ba"]
    translation = reply["translation"]
    audio = reply["audio"]
    clarify = reply["clarify"]
    proper = reply["proper"]

    xp_gained = 0
    level, streak, badges = 1, 0, []
    if payload.user_id:
        user = await session.get(User, payload.user_id)
        if user:
            xp_gained = 5
            add_xp(user, xp_gained, session, reason="chat")
            await touch_streak(session, user, xp=xp_gained)
            await update_daily_tasks(session, user, card_done=True)
            await session.commit()
            badges = await award_badges(session, user)
            await session.commit()
            level = user.level
            streak = user.streak

    return ChatOut(
        text_ba=text_ba,
        translation=translation,
        audio=audio,
        clarify=clarify,
        proper=proper,
        xp_gained=xp_gained,
        level=level,
        streak=streak,
        new_badges=[BadgeOut.model_validate(b) for b in badges],
    )
