"""LMS-модели: источники, задания, ответы, перевод-рекорды, события очков, экспертные проверки."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Source(Base):
    """Источник материала (phrasebook / book / audio)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="text")
    author: Mapped[str | None] = mapped_column(String(200))
    file_name: Mapped[str | None] = mapped_column(String(300))
    chapter: Mapped[str | None] = mapped_column(String(200))
    time_start: Mapped[str | None] = mapped_column(String(20))
    time_end: Mapped[str | None] = mapped_column(String(20))
    license_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskAssignment(Base):
    """Ежедневное задание: фрагмент + эталонный/возможный вариант перевода."""

    __tablename__ = "task_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    variant_translation: Mapped[str] = mapped_column(Text, nullable=False)
    is_corrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_date: Mapped[date] = mapped_column(Date, nullable=False)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Answer(Base):
    """Ответ пользователя на задание/фрагмент (вариант перевода)."""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("task_assignments.id", ondelete="SET NULL"), nullable=True)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(16), default="confirm")  # confirm / correct
    is_corrupted_variant: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_consensus: Mapped[bool] = mapped_column(Boolean, default=False)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TranslationRecord(Base):
    """Рекорд подтверждённого перевода (консенсус экспертов/пользователей)."""

    __tablename__ = "translation_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False, unique=True)
    text_ba: Mapped[str] = mapped_column(Text, nullable=False)
    lang_pair: Mapped[str] = mapped_column(String(16), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    source_coords: Mapped[str | None] = mapped_column(Text)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / confirmed / expert_review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PointsEvent(Base):
    """Событие начисления очков (история для периодных рейтингов)."""

    __tablename__ = "points_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExpertReview(Base):
    """Спорный перевод — на review эксперта."""

    __tablename__ = "expert_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    lang_pair: Mapped[str] = mapped_column(String(16), nullable=False)
    candidates: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / resolved
    resolution: Mapped[str | None] = mapped_column(Text)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
