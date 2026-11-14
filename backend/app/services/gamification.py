"""Геймификация: очки, уровни, серии, сердца, бейджи, ежедневные квесты, лиги."""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Badge,
    DailyTask,
    StreakLog,
    PointsEvent,
    User,
    UserAnswer,
    UserBadge,
)

# ---------------------------------------------------------------------------
# Каталог бейджей
# ---------------------------------------------------------------------------
BADGE_CATALOG: list[dict] = [
    {"code": "first_word", "name": "Первое слово", "emoji": "🐣", "criterion": "cards1", "xp_reward": 10,
     "description": "Первая правильная фраза"},
    {"code": "streak3", "name": "Три дня", "emoji": "🔥", "criterion": "streak3", "xp_reward": 20,
     "description": "3 дня подряд"},
    {"code": "streak7", "name": "Неделя", "emoji": "🔥", "criterion": "streak7", "xp_reward": 50,
     "description": "7 дней подряд"},
    {"code": "streak30", "name": "Месяц discipline", "emoji": "🏆", "criterion": "streak30", "xp_reward": 200,
     "description": "30 дней подряд"},
    {"code": "cards100", "name": "Сто фраз", "emoji": "📚", "criterion": "cards100", "xp_reward": 30,
     "description": "100 правильных фраз"},
    {"code": "cards1000", "name": "Тысяча фраз", "emoji": "📖", "criterion": "cards1000", "xp_reward": 150,
     "description": "1000 правильных фраз"},
    {"code": "xp500", "name": "500 XP", "emoji": "⭐", "criterion": "xp500", "xp_reward": 30,
     "description": "Накопи 500 XP"},
    {"code": "xp5000", "name": "5000 XP", "emoji": "🌟", "criterion": "xp5000", "xp_reward": 100,
     "description": "Накопи 5000 XP"},
    {"code": "speed100", "name": "Скорость 100", "emoji": "⚡", "criterion": "speed100", "xp_reward": 30,
     "description": "100 очков в быстром переводе"},
    {"code": "speed10", "name": "Быстрый ум", "emoji": "🎯", "criterion": "speed10", "xp_reward": 20,
     "description": "10 верных подряд в быстром режиме"},
    {"code": "duel_win", "name": "Дуэлянт", "emoji": "⚔️", "criterion": "duel_win", "xp_reward": 40,
     "description": "Победа в дуэли"},
    {"code": "perfect5", "name": "Идеально", "emoji": "💎", "criterion": "perfect5", "xp_reward": 40,
     "description": "5 верных подряд"},
    {"code": "early_bird", "name": "Ранняя пташка", "emoji": "🌅", "criterion": "early_bird", "xp_reward": 25,
     "description": "Занятие до 8 утра"},
    {"code": "night_owl", "name": "Сова", "emoji": "🦉", "criterion": "night_owl", "xp_reward": 25,
     "description": "Занятие после 23:00"},
    {"code": "goal7", "name": "Цель недели", "emoji": "🎯", "criterion": "goal7", "xp_reward": 60,
     "description": "7 дней подряд по цели"},
]

LEAGUES = [
    (0, "🥉 Bronze", "bronze"),
    (1000, "🥈 Silver", "silver"),
    (3000, "🥇 Gold", "gold"),
    (6000, "💎 Platinum", "platinum"),
    (12000, "👑 Diamond", "diamond"),
]


def level_for_xp(xp: int) -> int:
    """Уровень по опыту: чем дальше, тем дороже следующий уровень."""
    xp = max(0, xp)
    lvl = 1
    need = 100
    while xp >= need:
        xp -= need
        lvl += 1
        need = int(need * 1.25) + 50
    return lvl


def xp_for_level(level: int) -> int:
    total = 0
    need = 100
    for _ in range(level - 1):
        total += need
        need = int(need * 1.25) + 50
    return total


def league_for_xp(xp: int) -> str:
    league = "bronze"
    for threshold, _label, name in LEAGUES:
        if xp >= threshold:
            league = name
    return league


def xp_progress(xp: int) -> tuple[int, int, int]:
    """(уровень, xp в уровне, xpneeded в уровне)."""
    lvl = level_for_xp(xp)
    base = xp_for_level(lvl)
    need = xp_for_level(lvl + 1) - base
    return lvl, xp - base, need


# ---------------------------------------------------------------------------
# Сердца
# ---------------------------------------------------------------------------
def refill_hearts(user: User) -> bool:
    """Восстанавливает сердца по времени. True, если сердца изменились."""
    now = datetime.utcnow()
    elapsed = (now - (user.hearts_updated_at or now)).total_seconds()
    if elapsed < settings.hearts_refill_seconds:
        return False
    refill = int(elapsed // settings.hearts_refill_seconds)
    if user.hearts >= settings.hearts_max:
        user.hearts_updated_at = now
        return False
    user.hearts = min(settings.hearts_max, user.hearts + refill)
    user.hearts_updated_at = now + timedelta(seconds=refill * settings.hearts_refill_seconds - elapsed)
    return True


def spend_heart(user: User) -> bool:
    """Снимает сердце за ошибку. False — сердец нет (нужно подождать)."""
    refill_hearts(user)
    if user.hearts <= 0:
        return False
    user.hearts -= 1
    return True


# ---------------------------------------------------------------------------
# Серия (streak) и ежедневные квесты
# Сутки считаются по Уфе (UTC+5), как и рейтинги.
# ---------------------------------------------------------------------------
_UFA = timedelta(hours=5)


def ufa_today() -> date:
    return (datetime.utcnow() + _UFA).date()


def consecutive_streak(days: set[date], today: date) -> int:
    """Длина живой серии. Один заход серию не поднимает: нужно минимум два дня подряд.

    Серия жива, если последний заход был сегодня или вчера по Уфе.
    """
    if not days:
        return 0
    latest = max(days)
    if (today - latest).days > 1:
        return 0
    run = 0
    cursor = latest
    while cursor in days:
        run += 1
        cursor -= timedelta(days=1)
    return run if run >= 2 else 0


def longest_consecutive(days: set[date]) -> int:
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        run = 0
        cursor = day
        while cursor in days:
            run += 1
            cursor += timedelta(days=1)
        if run >= 2:
            best = max(best, run)
    return best


async def _get_or_create_streak_log(session: AsyncSession, user: User, today: date) -> StreakLog:
    log = (
        await session.execute(
            select(StreakLog).where(StreakLog.user_id == user.id, StreakLog.day == today)
        )
    ).scalar_one_or_none()
    if log is None:
        log = StreakLog(user_id=user.id, day=today, cards_done=0, xp_earned=0)
        session.add(log)
        await session.flush()
    return log


async def refresh_streak(session: AsyncSession, user: User) -> int:
    """Пересчитывает серию по дням заходов. Повторный заход в те же сутки ничего не добавляет."""
    rows = (
        await session.execute(select(StreakLog.day).where(StreakLog.user_id == user.id))
    ).scalars().all()
    days = set(rows)
    value = consecutive_streak(days, ufa_today())
    user.streak = value
    user.longest_streak = longest_consecutive(days)
    return value


async def mark_visit(session: AsyncSession, user: User) -> int:
    """Отмечает, что пользователь зашёл сегодня. Серия растёт только со второго дня подряд."""
    await _get_or_create_streak_log(session, user, ufa_today())
    return await refresh_streak(session, user)


async def touch_streak(session: AsyncSession, user: User, *, xp: int = 0) -> StreakLog:
    """Отмечает занятие за сегодня по Уфе и пересчитывает серию.

    Один день, даже с несколькими занятиями, серию не поднимает.
    Она становится равна числу дней только когда заходы идут подряд два дня и больше.
    Пропуск дня обнуляет серию.
    """
    today = ufa_today()
    log = await _get_or_create_streak_log(session, user, today)
    log.cards_done += 1
    log.xp_earned += xp
    if log.cards_done >= user.daily_goal:
        log.goal_reached = True

    user.last_active = datetime.utcnow()
    await refresh_streak(session, user)
    return log


async def ensure_daily_tasks(session: AsyncSession, user: User) -> list[DailyTask]:
    """Создаёт квесты дня, если их ещё нет."""
    today = date.today()
    existing = (
        await session.execute(
            select(DailyTask).where(DailyTask.user_id == user.id, DailyTask.day == today)
        )
    ).scalars().all()
    if existing:
        return list(existing)

    tasks = [
        DailyTask(user_id=user.id, day=today, code="cards", title="Пройдите карточки",
                  progress=0, target=settings.daily_cards_goal, xp_reward=30),
        DailyTask(user_id=user.id, day=today, code="speed", title="Скоростной забег",
                  progress=0, target=1, xp_reward=20),
        DailyTask(user_id=user.id, day=today, code="battle", title="Выиграйте состязание",
                  progress=0, target=1, xp_reward=30),
        DailyTask(user_id=user.id, day=today, code="accuracy", title="Точность 80%",
                  progress=0, target=80, xp_reward=25),
    ]
    for t in tasks:
        session.add(t)
    await session.flush()
    return tasks


async def update_daily_tasks(session: AsyncSession, user: User, *, card_done: bool = False,
                             accuracy: float | None = None, speed_done: bool = False,
                             battle_done: bool = False) -> list[DailyTask]:
    """Обновляет прогресс квестов дня и начисляет награды."""
    tasks = await ensure_daily_tasks(session, user)
    for t in tasks:
        if t.completed:
            continue
        if t.code == "cards" and card_done:
            t.progress += 1
        elif t.code == "speed" and speed_done:
            t.progress = min(t.target, t.progress + 1)
        elif t.code == "battle" and battle_done:
            t.progress = min(t.target, t.progress + 1)
        elif t.code == "accuracy" and accuracy is not None:
            t.progress = min(t.target, int(accuracy))
        if t.progress >= t.target:
            t.completed = True
            user.xp += t.xp_reward
    return tasks


# ---------------------------------------------------------------------------
# Бейджи
# ---------------------------------------------------------------------------
async def _criterion_value(session: AsyncSession, user: User, criterion: str) -> int:
    now = datetime.utcnow()
    if criterion == "cards1":
        return (
            await session.execute(
                select(func.count()).select_from(UserAnswer).where(
                    UserAnswer.user_id == user.id, UserAnswer.is_correct.is_(True)
                )
            )
        ).scalar_one()
    if criterion.startswith("cards"):
        n = int(criterion[5:])
        return (
            await session.execute(
                select(func.count()).select_from(UserAnswer).where(
                    UserAnswer.user_id == user.id, UserAnswer.is_correct.is_(True)
                )
            )
        ).scalar_one() // n if n else 0
    if criterion.startswith("xp"):
        n = int(criterion[2:])
        return (user.xp or 0) // n if n else 0
    if criterion.startswith("streak"):
        n = int(criterion[6:])
        return (user.streak or 0) // n if n else 0
    if criterion == "speed100":
        from app.models import SpeedRun
        best = (
            await session.execute(
                select(func.max(SpeedRun.score)).where(SpeedRun.user_id == user.id)
            )
        ).scalar_one()
        return int(best or 0) // 100
    if criterion == "speed10":
        from app.models import SpeedRun
        best = (
            await session.execute(
                select(func.max(SpeedRun.best_streak)).where(SpeedRun.user_id == user.id)
            )
        ).scalar_one()
        return int(best or 0) // 10
    if criterion == "duel_win":
        from app.models import Duel
        n = (
            await session.execute(
                select(func.count()).select_from(Duel).where(Duel.winner_id == user.id)
            )
        ).scalar_one()
        return n
    if criterion == "perfect5":
        best = _best_answer_streak(user)
        return best // 5
    if criterion == "goal7":
        n = (
            await session.execute(
                select(func.count()).select_from(StreakLog).where(
                    StreakLog.user_id == user.id, StreakLog.goal_reached.is_(True)
                )
            )
        ).scalar_one()
        return n
    if criterion == "early_bird":
        return 1 if now.hour < 8 else 0
    if criterion == "night_owl":
        return 1 if now.hour >= 23 else 0
    return 0


_ANSWER_STREAK_CACHE: dict[int, int] = {}


def _best_answer_streak(user: User) -> int:
    return _ANSWER_STREAK_CACHE.get(user.id, 0)


def note_answer_streak(user: User, correct: bool) -> int:
    """Считает текущую серию верных ответов (в кэше до сохранения)."""
    key = user.id
    cur = _ANSWER_STREAK_CACHE.get(key, 0)
    cur = cur + 1 if correct else 0
    _ANSWER_STREAK_CACHE[key] = cur
    return cur


async def award_badges(session: AsyncSession, user: User) -> list[Badge]:
    """Проверяет и выдаёт новые бейджи."""
    owned = set(
        (
            await session.execute(
                select(UserBadge.badge_code).where(UserBadge.user_id == user.id)
            )
        ).scalars().all()
    )
    earned: list[Badge] = []
    for spec in BADGE_CATALOG:
        if spec["code"] in owned:
            continue
        value = await _criterion_value(session, user, spec["criterion"])
        if value < 1:
            continue
        badge = await session.get(Badge, spec["code"])
        if badge is None:
            badge = Badge(**spec)
            session.add(badge)
            await session.flush()
        session.add(UserBadge(user_id=user.id, badge_code=badge.code, earned_at=datetime.utcnow()))
        reward = badge.xp_reward or 0
        user.xp = (user.xp or 0) + reward
        if reward and user.id:
            session.add(PointsEvent(user_id=user.id, points=reward, reason="badge"))
        earned.append(badge)
    return earned


def add_xp(user: User, amount: int, session: AsyncSession | None = None, reason: str = "activity") -> None:
    gained = max(0, int(amount or 0))
    user.xp = (user.xp or 0) + gained
    user.level = level_for_xp(user.xp)
    user.league = league_for_xp(user.xp)
    if session is not None and gained and user.id:
        session.add(PointsEvent(user_id=user.id, points=gained, reason=reason))
