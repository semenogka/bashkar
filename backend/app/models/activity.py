"""Модели активности: ответы, серии, скоростные забеги, дуэли, достижения."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.content import Fragment
from app.models.users import User


class UserAnswer(Base):
    __tablename__ = "user_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    lang_pair_id: Mapped[int] = mapped_column(ForeignKey("lang_pairs.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    time_spent: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String(24), default="normal")  # normal / speed / duel / chat
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])
    fragment: Mapped["Fragment | None"] = relationship(foreign_keys=[fragment_id])

    __table_args__ = (
        Index("ix_answers_user_created", "user_id", "created_at"),
        Index("ix_answers_fragment_pair", "fragment_id", "lang_pair_id"),
    )


class StreakLog(Base):
    """Отметка активности по дням — основа серии (streak)."""

    __tablename__ = "streak_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    cards_done: Mapped[int] = mapped_column(Integer, default=0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    goal_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_streak_user_day"),)


class SpeedRun(Base):
    """Забег «быстрый перевод» на 60 секунд."""

    __tablename__ = "speed_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lang_pair_id: Mapped[int] = mapped_column(ForeignKey("lang_pairs.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=60.0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])

    __table_args__ = (Index("ix_speed_score", "score"),)


class Duel(Base):
    """Состязание: кто быстрее и точнее переведёт фразу."""

    __tablename__ = "duels"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opponent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lang_pair_id: Mapped[int] = mapped_column(ForeignKey("lang_pairs.id"), nullable=False)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id"), nullable=False)

    challenger_answer: Mapped[str | None] = mapped_column(Text)
    opponent_answer: Mapped[str | None] = mapped_column(Text)
    challenger_time: Mapped[float | None] = mapped_column(Float)
    opponent_time: Mapped[float | None] = mapped_column(Float)
    challenger_correct: Mapped[bool | None] = mapped_column(Boolean)
    opponent_correct: Mapped[bool | None] = mapped_column(Boolean)

    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting/active/finished
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    fragment: Mapped["Fragment | None"] = relationship(foreign_keys=[fragment_id])
    challenger: Mapped["User | None"] = relationship(foreign_keys=[challenger_id])
    opponent: Mapped["User | None"] = relationship(foreign_keys=[opponent_id])

    __table_args__ = (Index("ix_duels_status", "status"),)


class Badge(Base):
    """Каталог достижений (бейджи)."""

    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(160))
    emoji: Mapped[str] = mapped_column(String(8), default="🏅")
    criterion: Mapped[str] = mapped_column(String(64), nullable=False)  # streak3, xp100, speed100...
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)
    rarity: Mapped[str] = mapped_column(String(16), default="common")


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    badge_code: Mapped[str] = mapped_column(ForeignKey("badges.code", ondelete="CASCADE"), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    badge: Mapped[Badge] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "badge_code", name="uq_user_badge"),)


class DailyTask(Base):
    """Ежедневное задание (квест) — возвращает игрока каждый день."""

    __tablename__ = "daily_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)  # cards / streak / speed / accuracy
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    target: Mapped[int] = mapped_column(Integer, default=1)
    xp_reward: Mapped[int] = mapped_column(Integer, default=20)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("user_id", "day", "code", name="uq_daily_task"),)


class VocabProgress(Base):
    """Прогресс по конкретному слову/фразе — «дерево навыков» и повторения."""

    __tablename__ = "vocab_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    lang_pair_id: Mapped[int] = mapped_column(ForeignKey("lang_pairs.id"), nullable=False)
    mastery: Mapped[int] = mapped_column(Integer, default=0)  # 0..5
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    next_review: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("user_id", "fragment_id", "lang_pair_id", name="uq_vocab_progress"),
    )
