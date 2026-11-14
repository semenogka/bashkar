"""Прямой доступ бота к PostgreSQL, без HTTP-запросов к API."""
from __future__ import annotations

import datetime as dt
from typing import Any

import asyncpg

from app.api.interfaces import PlatformClient


class _Ufa(dt.tzinfo):
    """Уфа, UTC+5. С методами localize/normalize, их ждёт планировщик."""

    def utcoffset(self, moment: dt.datetime | None) -> dt.timedelta:
        return dt.timedelta(hours=5)

    def dst(self, moment: dt.datetime | None) -> dt.timedelta:
        return dt.timedelta(0)

    def tzname(self, moment: dt.datetime | None) -> str:
        return "UFA"

    def localize(self, moment: dt.datetime, is_dst: bool | None = None) -> dt.datetime:
        return moment.replace(tzinfo=self)

    def normalize(self, moment: dt.datetime) -> dt.datetime:
        return moment


UFA = _Ufa()


def period_start(period: str) -> dt.datetime:
    """Начало дня, месяца или года по времени Уфы, в наивном UTC."""
    now = dt.datetime.now(UFA)
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(dt.timezone.utc).replace(tzinfo=None)


def ufa_today() -> dt.date:
    return dt.datetime.now(UFA).date()


def studied_today(last_active: dt.datetime | None) -> bool:
    if last_active is None:
        return False
    moment = last_active if last_active.tzinfo else last_active.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(UFA).date() == ufa_today()


def _dsn(database_url: str) -> str:
    url = (database_url or "").strip()
    if not url:
        raise ValueError("Не задан DATABASE_URL")
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


class DbPlatformClient(PlatformClient):
    def __init__(self, database_url: str):
        self._dsn = _dsn(database_url)
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _lang_pair_id(self, conn: asyncpg.Connection) -> int | None:
        return await conn.fetchval("SELECT id FROM lang_pairs WHERE code = 'ba-ru'")

    async def _fetch_user(self, conn: asyncpg.Connection, telegram_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            SELECT id, external_id, name, username, xp, level, streak, longest_streak,
                   league, hearts, class_id, school_id, last_active
            FROM users
            WHERE external_id = $1
            """,
            str(telegram_id),
        )

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            existing = await self._fetch_user(conn, telegram_id)
            if existing is not None:
                return {"success": True, "is_new": False, "user": dict(existing)}

            pair_id = await self._lang_pair_id(conn)
            now = dt.datetime.utcnow()
            handle = username or f"tg_{telegram_id}"
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (
                        external_id, username, name, role, avatar, lang_pair_id,
                        xp, level, streak, longest_streak, gems, hearts,
                        hearts_updated_at, daily_goal, league, created_at
                    ) VALUES (
                        $1, $2, $3, 'student', '🐝', $4,
                        0, 1, 0, 0, 0, 5,
                        $5, 20, 'bronze', $5
                    )
                    RETURNING id, external_id, name, username, xp, level, streak, league, hearts
                    """,
                    str(telegram_id),
                    handle,
                    first_name or "Ученик",
                    pair_id,
                    now,
                )
            except asyncpg.UniqueViolationError:
                row = await self._fetch_user(conn, telegram_id)
                if row is None:
                    raise
                return {"success": True, "is_new": False, "user": dict(row)}

            return {"success": True, "is_new": True, "user": dict(row)}

    async def _require_user(self, conn: asyncpg.Connection, telegram_id: int) -> asyncpg.Record:
        user = await self._fetch_user(conn, telegram_id)
        if user is None:
            raise ValueError("Пользователь не найден. Сначала отправьте команду /start.")
        return user

    async def get_user_profile(self, telegram_id: int) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            return {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
                "xp": user["xp"] or 0,
                "level": user["level"] or 1,
                "streak": user["streak"] or 0,
                "longest_streak": user["longest_streak"] or 0,
                "league": user["league"] or "bronze",
                "hearts": user["hearts"],
            }

    async def get_user_rating(self, telegram_id: int) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            position = await conn.fetchval(
                "SELECT COUNT(*) + 1 FROM users WHERE xp > $1",
                user["xp"] or 0,
            )
            return {"position": int(position), "points": user["xp"] or 0}

    async def ensure_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_notices (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    kind VARCHAR(32) NOT NULL,
                    sent_on DATE NOT NULL,
                    UNIQUE (user_id, kind, sent_on)
                )
                """
            )

    async def get_leaderboard(self, telegram_id: int, period: str = "day") -> dict[str, Any]:
        period = period if period in {"day", "month", "year"} else "day"
        start = period_start(period)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            rows = await conn.fetch(
                """
                SELECT u.name, SUM(pe.points) AS pts
                FROM points_events pe
                JOIN users u ON u.id = pe.user_id
                WHERE pe.created_at >= $1 AND pe.points > 0
                GROUP BY u.id, u.name
                ORDER BY pts DESC, u.id
                LIMIT 10
                """,
                start,
            )
            mine = await conn.fetchval(
                """
                SELECT COALESCE(SUM(points), 0)
                FROM points_events
                WHERE user_id = $1 AND created_at >= $2 AND points > 0
                """,
                user["id"],
                start,
            )
            mine = int(mine or 0)
            position = None
            if mine > 0:
                position = await conn.fetchval(
                    """
                    SELECT COUNT(*) + 1 FROM (
                        SELECT user_id
                        FROM points_events
                        WHERE created_at >= $1 AND points > 0
                        GROUP BY user_id
                        HAVING SUM(points) > $2
                    ) ahead
                    """,
                    start,
                    mine,
                )
            class_rank = await self._group_rank(conn, "class", user["class_id"])
            school_rank = await self._group_rank(conn, "school", user["school_id"])
            return {
                "period": period,
                "top": [{"name": row["name"] or "Ученик", "xp": int(row["pts"] or 0)} for row in rows],
                "position": int(position) if position is not None else None,
                "points": mine,
                "class_rank": class_rank,
                "school_rank": school_rank,
            }

    async def _group_rank(self, conn: asyncpg.Connection, kind: str, group_id: int | None) -> dict[str, Any] | None:
        if not group_id:
            return None
        if kind == "class":
            row = await conn.fetchrow(
                """
                WITH scored AS (
                    SELECT c.id, c.name, COALESCE(s.name, '') AS school_name,
                           COALESCE(SUM(u.xp) FILTER (WHERE u.role = 'student'), 0) AS xp
                    FROM classes c
                    LEFT JOIN users u ON u.class_id = c.id
                    LEFT JOIN schools s ON s.id = c.school_id
                    GROUP BY c.id, c.name, s.name
                )
                SELECT name, school_name, xp,
                       (SELECT COUNT(*) + 1 FROM scored x WHERE x.xp > scored.xp) AS rank
                FROM scored
                WHERE id = $1
                """,
                group_id,
            )
        else:
            row = await conn.fetchrow(
                """
                WITH scored AS (
                    SELECT s.id, s.name,
                           COALESCE(SUM(u.xp) FILTER (WHERE u.role = 'student'), 0) AS xp
                    FROM schools s
                    LEFT JOIN users u ON u.school_id = s.id
                    GROUP BY s.id, s.name
                )
                SELECT name, '' AS school_name, xp,
                       (SELECT COUNT(*) + 1 FROM scored x WHERE x.xp > scored.xp) AS rank
                FROM scored
                WHERE id = $1
                """,
                group_id,
            )
        if row is None:
            return None
        return {
            "name": row["name"],
            "school_name": row["school_name"] or "",
            "xp": int(row["xp"] or 0),
            "rank": int(row["rank"]),
        }

    async def list_notify_users(self) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, external_id, name, streak, last_active
                FROM users
                WHERE external_id ~ '^[0-9]+$'
                """
            )
            return [
                {
                    "id": row["id"],
                    "chat_id": int(row["external_id"]),
                    "name": row["name"] or "Ученик",
                    "streak": row["streak"] or 0,
                    "studied_today": studied_today(row["last_active"]),
                }
                for row in rows
            ]

    async def claim_notice(self, user_id: int, kind: str, day: dt.date) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO bot_notices (user_id, kind, sent_on)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, kind, sent_on) DO NOTHING
                RETURNING id
                """,
                user_id,
                kind,
                day,
            )
            return row is not None

    async def release_notice(self, user_id: int, kind: str, day: dt.date) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM bot_notices WHERE user_id = $1 AND kind = $2 AND sent_on = $3",
                user_id,
                kind,
                day,
            )

    async def get_user_statistics(self, telegram_id: int) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            user_id = user["id"]
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM user_answers WHERE user_id = $1",
                user_id,
            )
            correct = await conn.fetchval(
                "SELECT COUNT(*) FROM user_answers WHERE user_id = $1 AND is_correct IS TRUE",
                user_id,
            )
            vocab = await conn.fetchval(
                "SELECT COUNT(*) FROM vocab_progress WHERE user_id = $1 AND mastery >= 3",
                user_id,
            )
            total = int(total or 0)
            correct = int(correct or 0)
            return {
                "total_answers": total,
                "correct": correct,
                "accuracy": round(correct / total * 100, 1) if total else 0.0,
                "vocab_learned": int(vocab or 0),
                "level": user["level"] or 1,
                "xp": user["xp"] or 0,
                "streak": user["streak"] or 0,
            }

    async def get_user_schedule(self, telegram_id: int) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            rows = await conn.fetch(
                """
                SELECT dc.day, f.text_ba, dc.proposed_translation, dc.is_correct
                FROM daily_challenges dc
                JOIN fragments f ON f.id = dc.fragment_id
                WHERE dc.user_id = $1
                ORDER BY dc.day DESC
                LIMIT 7
                """,
                user["id"],
            )
            return [
                {
                    "day": row["day"].isoformat(),
                    "bashkir": row["text_ba"],
                    "proposed": row["proposed_translation"],
                    "is_correct": row["is_correct"],
                }
                for row in rows
            ]

    async def get_user_tasks(self, telegram_id: int) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            user = await self._require_user(conn, telegram_id)
            rows = await conn.fetch(
                """
                SELECT day, code, title, progress, target, xp_reward, completed
                FROM daily_tasks
                WHERE user_id = $1 AND day = CURRENT_DATE
                ORDER BY id
                """,
                user["id"],
            )
            return [
                {
                    "day": row["day"].isoformat(),
                    "code": row["code"],
                    "title": row["title"],
                    "progress": row["progress"],
                    "target": row["target"],
                    "xp_reward": row["xp_reward"],
                    "completed": row["completed"],
                }
                for row in rows
            ]
