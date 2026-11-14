"""Дуэли: кто быстрее и точнее переведёт фразу."""
from __future__ import annotations

import random
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import Duel, Fragment, LangPair, Translation, User
from app.schemas import DuelAnswerIn, DuelAnswerOut, DuelCreate, DuelOut
from app.services.agreement import normalize
from app.services.gamification import add_xp, award_badges

router = APIRouter(prefix="/duels", tags=["duels"])


def _code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def _pick_fragment(session: AsyncSession, pair_id: int) -> tuple[Fragment, Translation] | None:
    rows = (
        await session.execute(
            select(Fragment, Translation)
            .join(Translation, Translation.fragment_id == Fragment.id)
            .where(Translation.lang_pair_id == pair_id)
            .limit(200)
        )
    ).all()
    if not rows:
        return None
    return random.choice(rows)


async def _duel_out(duel: Duel, session: AsyncSession) -> DuelOut:
    frag = await session.get(Fragment, duel.fragment_id)
    pair = await session.get(LangPair, duel.lang_pair_id)
    return DuelOut(
        id=duel.id,
        code=duel.code,
        status=duel.status,
        lang_pair=pair.code if pair else "",
        fragment_id=duel.fragment_id,
        text_ba=frag.text_ba if frag else "",
        challenger_id=duel.challenger_id,
        opponent_id=duel.opponent_id,
        challenger_correct=duel.challenger_correct,
        opponent_correct=duel.opponent_correct,
        winner_id=duel.winner_id,
        created_at=duel.created_at,
    )


@router.post("", response_model=DuelOut)
async def create_duel(payload: DuelCreate, session: AsyncSession = Depends(get_session)):
    challenger = await session.get(User, payload.challenger_id)
    if not challenger:
        raise HTTPException(404, "Игрок не найден")
    pair_id = payload.lang_pair_id or challenger.lang_pair_id
    if not pair_id:
        raise HTTPException(400, "Не выбрана языковая пара")
    pair = await session.get(LangPair, pair_id)
    if not pair:
        raise HTTPException(404, "Пара не найдена")

    picked = await _pick_fragment(session, pair.id)
    if picked is None:
        raise HTTPException(404, "Нет фрагментов")
    frag, _tr = picked

    # Ищем соперника онлайн (кроме себя)
    opponent = None
    if payload.opponent_id:
        opponent = await session.get(User, payload.opponent_id)
    else:
        candidates = (
            await session.execute(
                select(User).where(
                    User.id != challenger.id,
                    User.last_active.is_not(None),
                ).order_by(User.last_active.desc()).limit(20)
            )
        ).scalars().all()
        if candidates:
            opponent = random.choice(candidates)

    duel = Duel(
        code=_code(),
        challenger_id=challenger.id,
        opponent_id=opponent.id if opponent else None,
        lang_pair_id=pair.id,
        fragment_id=frag.id,
        status="active" if opponent else "waiting",
    )
    session.add(duel)
    await session.commit()
    await session.refresh(duel)
    return await _duel_out(duel, session)


@router.get("/{code}", response_model=DuelOut)
async def get_duel(code: str, session: AsyncSession = Depends(get_session)):
    duel = (
        await session.execute(select(Duel).where(Duel.code == code))
    ).scalar_one_or_none()
    if not duel:
        raise HTTPException(404, "Дуэль не найдена")
    return await _duel_out(duel, session)


@router.post("/answer", response_model=DuelAnswerOut)
async def duel_answer(payload: DuelAnswerIn, session: AsyncSession = Depends(get_session)):
    duel = await session.get(Duel, payload.duel_id)
    if not duel:
        raise HTTPException(404, "Дуэль не найдена")

    tr = (
        await session.execute(
            select(Translation).where(
                Translation.fragment_id == duel.fragment_id,
                Translation.lang_pair_id == duel.lang_pair_id,
            )
        )
    ).scalar_one_or_none()
    correct_answer = tr.translation if tr else ""
    correct = normalize(payload.answer) == normalize(correct_answer)

    if payload.user_id == duel.challenger_id:
        duel.challenger_answer = payload.answer
        duel.challenger_time = payload.time_spent
        duel.challenger_correct = correct
    elif duel.opponent_id and payload.user_id == duel.opponent_id:
        duel.opponent_answer = payload.answer
        duel.opponent_time = payload.time_spent
        duel.opponent_correct = correct
    else:
        raise HTTPException(403, "Вы не участник дуэли")

    # Дуэль тоже считается активностью дня (серия).
    from app.services.gamification import touch_streak

    answering_user = await session.get(User, payload.user_id)
    if answering_user is not None:
        await touch_streak(session, answering_user, xp=0)

    finished = False
    winner_id = None
    if duel.challenger_answer and (duel.opponent_id is None or duel.opponent_answer):
        finished = True
        duel.status = "finished"
        duel.finished_at = datetime.utcnow()
        c_ok, o_ok = bool(duel.challenger_correct), bool(duel.opponent_correct)
        c_t = duel.challenger_time or 999.0
        o_t = duel.opponent_time or 999.0
        if c_ok and not o_ok:
            winner_id = duel.challenger_id
        elif o_ok and not c_ok:
            winner_id = duel.opponent_id
        elif c_ok and o_ok:
            winner_id = duel.challenger_id if c_t <= o_t else duel.opponent_id
        else:
            winner_id = None
        duel.winner_id = winner_id
        if winner_id:
            winner = await session.get(User, winner_id)
            if winner:
                add_xp(winner, 30, session, reason="duel")
    await session.commit()

    if winner_id:
        winner = await session.get(User, winner_id)
        if winner:
            await award_badges(session, winner)
            await session.commit()

    challenger = await session.get(User, duel.challenger_id)
    opponent = await session.get(User, duel.opponent_id) if duel.opponent_id else None
    return DuelAnswerOut(
        correct=correct,
        finished=finished,
        winner_id=winner_id,
        comparison={
            "correct_translation": correct_answer,
            "challenger": {
                "name": challenger.name if challenger else "?",
                "answer": duel.challenger_answer,
                "time": duel.challenger_time,
                "correct": duel.challenger_correct,
            },
            "opponent": {
                "name": opponent.name if opponent else "—",
                "answer": duel.opponent_answer,
                "time": duel.opponent_time,
                "correct": duel.opponent_correct,
            } if opponent else None,
        },
    )


@router.get("/user/{user_id}/history")
async def duel_history(user_id: int, limit: int = 20, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(Duel)
            .where(or_(Duel.challenger_id == user_id, Duel.opponent_id == user_id))
            .order_by(Duel.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    out = []
    for duel in rows:
        frag = await session.get(Fragment, duel.fragment_id)
        out.append({
            "id": duel.id,
            "code": duel.code,
            "status": duel.status,
            "text_ba": frag.text_ba if frag else "",
            "winner_id": duel.winner_id,
            "is_win": duel.winner_id == user_id,
            "created_at": duel.created_at,
        })
    return out
