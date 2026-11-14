s = open('app/api/v1.py', encoding='utf-8').read()

marker = '@router.get("/profile")'
assert marker in s, 'profile marker not found'

block = r'''
# ---------------------------------------------------------------------------
# PvP matchmaking + WebSocket
# ---------------------------------------------------------------------------
import uuid as _uuid

_PVP_WAITING: dict[str, dict] = {}
_PVP_MATCHES: dict[str, dict] = {}
_USER_MATCH: dict[str, str] = {}
_PVP_WS: dict[str, WebSocket] = {}
_PVP_WS_WAITING: set[str] = set()
_PVP_WS_MATCHES: dict[str, dict] = {}
_PVP_WS_USER_MATCH: dict[str, str] = {}


def _client_id(telegram_id: str | None, client_id: str | None) -> str:
    return client_id or telegram_id or "guest"


async def _build_pvp_prompt(session: AsyncSession) -> dict:
    card = await _random_card(session)
    if card is None:
        raise HTTPException(404, "Нет карточек")
    frag, tr = card
    correct = tr.translation
    options = [correct]
    attempts = 0
    while len(options) < 2 and attempts < 20:
        trap = _make_trap(correct)
        if trap and trap not in options and trap != correct:
            options.append(trap)
        attempts += 1
    while len(options) < 2:
        options.append(correct + ".")
    random.shuffle(options)
    correct_index = options.index(correct)
    return {
        "pvp_bashkir_phrase": frag.text_ba,
        "options": options,
        "correct_index": correct_index,
        "fragment_id": frag.id,
    }


@router.post("/pvp/find")
async def pvp_find(
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)

    if uid in _USER_MATCH:
        mid = _USER_MATCH[uid]
        match = _PVP_MATCHES.get(mid)
        if match:
            return {
                "status": "matched",
                "match_id": mid,
                "questions": match["questions"],
                "started_at": match["started_at"].isoformat(),
                "duration": match["duration"],
                "finished": bool(match.get("finished")),
            }
        _USER_MATCH.pop(uid, None)

    now = dt.datetime.utcnow()
    for oid, info in list(_PVP_WAITING.items()):
        if (now - info["joined_at"]).total_seconds() > 60:
            _PVP_WAITING.pop(oid, None)

    opponent = None
    for oid in list(_PVP_WAITING.keys()):
        if oid != uid:
            opponent = oid
            break

    if opponent is not None:
        _PVP_WAITING.pop(opponent, None)
        _PVP_WAITING.pop(uid, None)
        questions = [await _build_pvp_prompt(session) for _ in range(10)]
        mid = _uuid.uuid4().hex
        _PVP_MATCHES[mid] = {
            "users": [uid, opponent],
            "questions": questions,
            "started_at": now,
            "duration": 60,
            "progress": {
                uid: {"index": 0, "score": 0, "done": False},
                opponent: {"index": 0, "score": 0, "done": False},
            },
            "finished": False,
        }
        _USER_MATCH[uid] = mid
        _USER_MATCH[opponent] = mid
        return {
            "status": "matched",
            "match_id": mid,
            "questions": questions,
            "started_at": now.isoformat(),
            "duration": 60,
            "finished": False,
        }

    _PVP_WAITING[uid] = {"joined_at": now}
    return {"status": "searching"}


@router.get("/pvp/status")
async def pvp_status(
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    if uid in _USER_MATCH:
        mid = _USER_MATCH[uid]
        match = _PVP_MATCHES.get(mid)
        if match:
            now = dt.datetime.utcnow()
            elapsed = (now - match["started_at"]).total_seconds()
            finished = elapsed >= match["duration"] or all(p.get("done") for p in match["progress"].values())
            opp_uid = [u for u in match["users"] if u != uid][0]
            winner = None
            winner_is_you = False
            if finished:
                s_you = match["progress"][uid]["score"]
                s_opp = match["progress"][opp_uid]["score"]
                if s_you > s_opp:
                    winner = uid
                    winner_is_you = True
                elif s_opp > s_you:
                    winner = opp_uid
                else:
                    winner = "draw"
            return {
                "status": "finished" if finished else "matched",
                "match_id": mid,
                "questions": match["questions"],
                "started_at": match["started_at"].isoformat(),
                "duration": match["duration"],
                "your_progress": match["progress"][uid],
                "opponent_progress": {
                    "index": match["progress"][opp_uid]["index"],
                    "score": match["progress"][opp_uid]["score"],
                    "done": match["progress"][opp_uid]["done"],
                },
                "winner": winner,
                "winner_is_you": winner_is_you,
            }
        _USER_MATCH.pop(uid, None)
    if uid in _PVP_WAITING:
        return {"status": "searching"}
    return {"status": "idle"}


class PvpProgressIn(BaseModel):
    index: int = 0
    score: int = 0
    done: bool = False


@router.post("/pvp/progress")
async def pvp_progress(
    data: PvpProgressIn,
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    if uid not in _USER_MATCH:
        raise HTTPException(404, "Нет активного матча")
    mid = _USER_MATCH[uid]
    match = _PVP_MATCHES.get(mid)
    if not match or uid not in match["progress"]:
        raise HTTPException(404, "Матч не найден")
    match["progress"][uid]["index"] = int(data.index)
    match["progress"][uid]["score"] = int(data.score)
    match["progress"][uid]["done"] = bool(data.done)
    opp_uid = [u for u in match["users"] if u != uid][0]
    return {
        "ok": True,
        "opponent_progress": {
            "index": match["progress"][opp_uid]["index"],
            "score": match["progress"][opp_uid]["score"],
            "done": match["progress"][opp_uid]["done"],
        },
    }


@router.post("/pvp/cancel")
async def pvp_cancel(
    telegram_id: str | None = Header(default=None),
    client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    uid = _client_id(telegram_id, client_id)
    _PVP_WAITING.pop(uid, None)
    mid = _USER_MATCH.pop(uid, None)
    if mid and mid in _PVP_MATCHES:
        match = _PVP_MATCHES.pop(mid, None)
        if match:
            for u in match.get("users", []):
                _USER_MATCH.pop(u, None)
    return {"status": "cancelled"}


async def _ws_finish(match: dict, session: AsyncSession | None = None, winner_uid: str | None = None):
    if match.get("finished"):
        return
    match["finished"] = True
    users = match["users"]
    scores = {u: match["progress"][u]["score"] for u in users}
    if winner_uid is None:
        u1, u2 = users
        if scores[u1] > scores[u2]:
            winner_uid = u1
        elif scores[u2] > scores[u1]:
            winner_uid = u2
        else:
            winner_uid = "draw"
    for u in users:
        ws = _PVP_WS.get(u)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "finished",
                    "winner": winner_uid,
                    "winner_is_you": winner_uid == u,
                    "your_score": scores[u],
                    "opponent_score": scores[[x for x in users if x != u][0]],
                })
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
    for u in users:
        _PVP_WS.pop(u, None)
        _PVP_WS_USER_MATCH.pop(u, None)


@router.websocket("/pvp/ws")
async def pvp_websocket(
    websocket: WebSocket,
    client_id: str | None = Query(default=None),
    telegram_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    uid = _client_id(client_id, telegram_id)
    await websocket.accept()

    old = _PVP_WS.get(uid)
    if old is not None and old is not websocket:
        try:
            await old.close()
        except Exception:
            pass
    _PVP_WS[uid] = websocket

    try:
        while True:
            data = await websocket.receive_json()
            typ = data.get("type")

            if typ == "find":
                if uid in _PVP_WS_USER_MATCH:
                    mid = _PVP_WS_USER_MATCH[uid]
                    match = _PVP_WS_MATCHES.get(mid)
                    if match:
                        opp_uid = [u for u in match["users"] if u != uid][0]
                        finished = bool(match.get("finished"))
                        winner = None
                        winner_is_you = False
                        if finished:
                            scores = {u: match["progress"][u]["score"] for u in match["users"]}
                            if scores[uid] > scores[opp_uid]:
                                winner = uid
                                winner_is_you = True
                            elif scores[opp_uid] > scores[uid]:
                                winner = opp_uid
                            else:
                                winner = "draw"
                        await websocket.send_json({
                            "type": "matched",
                            "match_id": mid,
                            "questions": match["questions"],
                            "started_at": match["started_at"].isoformat(),
                            "duration": match["duration"],
                            "finished": finished,
                            "winner": winner,
                            "winner_is_you": winner_is_you,
                            "your_score": match["progress"][uid]["score"],
                            "opponent_score": match["progress"][opp_uid]["score"],
                            "opponent_progress": {
                                "index": match["progress"][opp_uid]["index"],
                                "score": match["progress"][opp_uid]["score"],
                                "done": match["progress"][opp_uid]["done"],
                            },
                        })
                        if finished:
                            await websocket.send_json({
                                "type": "finished",
                                "winner": winner,
                                "winner_is_you": winner_is_you,
                                "your_score": match["progress"][uid]["score"],
                                "opponent_score": match["progress"][opp_uid]["score"],
                            })
                        continue

                _PVP_WS_WAITING.discard(uid)
                opponent = None
                for oid in list(_PVP_WS_WAITING):
                    if oid != uid and oid in _PVP_WS:
                        opponent = oid
                        break

                if opponent is not None:
                    _PVP_WS_WAITING.discard(opponent)
                    questions = [await _build_pvp_prompt(session) for _ in range(10)]
                    mid = _uuid.uuid4().hex
                    now = dt.datetime.utcnow()
                    _PVP_WS_MATCHES[mid] = {
                        "users": [uid, opponent],
                        "questions": questions,
                        "started_at": now,
                        "duration": 60,
                        "progress": {
                            uid: {"index": 0, "score": 0, "done": False},
                            opponent: {"index": 0, "score": 0, "done": False},
                        },
                        "finished": False,
                    }
                    _PVP_WS_USER_MATCH[uid] = mid
                    _PVP_WS_USER_MATCH[opponent] = mid
                    payload = {
                        "type": "matched",
                        "match_id": mid,
                        "questions": questions,
                        "started_at": now.isoformat(),
                        "duration": 60,
                        "finished": False,
                        "opponent_progress": {"index": 0, "score": 0, "done": False},
                    }
                    for u in (uid, opponent):
                        ws = _PVP_WS.get(u)
                        if ws is not None:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                else:
                    _PVP_WS_WAITING.add(uid)
                    await websocket.send_json({"type": "searching"})

            elif typ == "progress":
                mid = _PVP_WS_USER_MATCH.get(uid)
                match = _PVP_WS_MATCHES.get(mid) if mid else None
                if not match or match.get("finished"):
                    continue
                match["progress"][uid] = {
                    "index": int(data.get("index", 0)),
                    "score": int(data.get("score", 0)),
                    "done": bool(data.get("done", False)),
                }
                opp_uid = [u for u in match["users"] if u != uid][0]
                opp_ws = _PVP_WS.get(opp_uid)
                if opp_ws is not None:
                    try:
                        await opp_ws.send_json({
                            "type": "opponent_progress",
                            "index": match["progress"][uid]["index"],
                            "score": match["progress"][uid]["score"],
                            "done": match["progress"][uid]["done"],
                        })
                    except Exception:
                        pass

                if match["progress"][uid].get("done"):
                    await _ws_finish(match, session)

            elif typ == "time_up":
                mid = _PVP_WS_USER_MATCH.get(uid)
                match = _PVP_WS_MATCHES.get(mid) if mid else None
                if match and not match.get("finished"):
                    await _ws_finish(match, session)

            elif typ == "cancel":
                _PVP_WS_WAITING.discard(uid)
                await websocket.send_json({"type": "cancelled"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        _PVP_WS.pop(uid, None)
        _PVP_WS_WAITING.discard(uid)
        mid = _PVP_WS_USER_MATCH.get(uid)
        if mid:
            match = _PVP_WS_MATCHES.get(mid)
            if match and not match.get("finished"):
                opp_uid = [u for u in match["users"] if u != uid][0]
                opp_ws = _PVP_WS.get(opp_uid)
                if opp_ws is not None:
                    try:
                        await opp_ws.send_json({"type": "opponent_left"})
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# Начисление XP (спринт, PvP и т.п.)
# ---------------------------------------------------------------------------
class XpAwardIn(BaseModel):
    amount: int
    reason: str = ""


@router.post("/xp/award")
async def award_xp(
    data: XpAwardIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    from app.services.gamification import add_xp, touch_streak, update_daily_tasks

    amount = max(0, int(data.amount or 0))
    if amount:
        add_xp(user, amount)
        await touch_streak(session, user, xp=amount)
        await update_daily_tasks(session, user, card_done=True)
        await session.commit()
    return {"xp": user.xp or 0, "level": user.level or 1, "amount": amount}


class SprintFinishIn(BaseModel):
    score: int = 0


@router.post("/sprint/finish")
async def sprint_finish(
    data: SprintFinishIn,
    session: AsyncSession = Depends(get_session),
    telegram_id: str | None = Header(default=None),
    telegram_name: str | None = Header(default=None),
) -> dict:
    user = await _resolve_user(session, telegram_id, telegram_name)
    from app.services.gamification import add_xp, touch_streak, update_daily_tasks

    amount = max(0, int(data.score or 0))
    if amount:
        add_xp(user, amount)
        await touch_streak(session, user, xp=amount)
        await update_daily_tasks(session, user, speed_done=True)
        await session.commit()
    return {"xp": user.xp or 0, "level": user.level or 1, "amount": amount}


'''

marker = '@router.get("/profile")'
assert marker in s
s = s.replace(marker, block + marker, 1)

open('app/api/v1.py', 'w', encoding='utf-8').write(s)
print('done')
