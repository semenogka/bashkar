s = open('app/api/v1.py', encoding='utf-8').read()

s = s.replace(
    "from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile",
    "from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Query",
    1,
)

s = s.replace(
    '_VOTES = {"approve": 0, "reject": 0}\n\n\n@router.post("/daily/vote")',
    '_VOTES = {"approve": 0, "reject": 0}\n_DAILY_VOTES: dict[dt.date, dict[str, set[int]]] = {}\n\n\n@router.post("/daily/vote")',
    1,
)

old_daily_vote = '''@router.post("/daily/vote")
async def daily_vote(data: DailyVoteIn) -> dict:
    _VOTES["approve" if data.approved else "reject"] += 1
    total = sum(_VOTES.values()) or 1
    return {
        "approvePercent": round(_VOTES["approve"] / total * 100),
        "rejectPercent": round(_VOTES["reject"] / total * 100),
    }'''
new_daily_vote = '''@router.post("/daily/vote")
async def daily_vote(
    data: DailyVoteIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    _VOTES["approve" if data.approved else "reject"] += 1
    bucket = _DAILY_VOTES.setdefault(dt.date.today(), {"approve": set(), "reject": set()})
    bucket["approve" if data.approved else "reject"].add(user.id)
    total = sum(_VOTES.values()) or 1
    return {
        "approvePercent": round(_VOTES["approve"] / total * 100),
        "rejectPercent": round(_VOTES["reject"] / total * 100),
    }'''
assert old_daily_vote in s
s = s.replace(old_daily_vote, new_daily_vote, 1)

old_dt = '''    user = await _resolve_user(session, telegram_id, telegram_name)
    today = dt.date.today()

    challenge = (
        await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id, DailyChallenge.day == today
            )
        )
    ).scalar_one_or_none()

    if challenge is None:'''
new_dt = '''    user = await _resolve_user(session, telegram_id, telegram_name)
    today = dt.date.today()

    for day, votes in list(_DAILY_VOTES.items()):
        if day < today:
            await _process_daily_votes(session, day, votes)
            _DAILY_VOTES.pop(day, None)

    challenge = (
        await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id, DailyChallenge.day == today
            )
        )
    ).scalar_one_or_none()

    if challenge is None:'''
assert old_dt in s
s = s.replace(old_dt, new_dt, 1)

func = '''async def _process_daily_votes(session: AsyncSession, day: dt.date, votes: dict) -> None:
    approve = votes.get("approve", set())
    reject = votes.get("reject", set())
    if not approve and not reject:
        return
    majority = approve if len(approve) >= len(reject) else reject
    from app.services.gamification import add_xp, touch_streak

    for uid in majority:
        user = await session.get(User, uid)
        if user is not None:
            add_xp(user, 15)
            await touch_streak(session, user, xp=15)
    await session.commit()


'''
marker = "async def daily_task("
assert marker in s
s = s.replace(marker, func + marker, 1)

open('app/api/v1.py', 'w', encoding='utf-8').write(s)
print('done')
