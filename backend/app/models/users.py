"""Модели пользователей, школ и классов."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.content import LangPair


class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    classes: Mapped[list["ClassGroup"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )


class ClassGroup(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"))
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    invite_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    school: Mapped[School | None] = relationship(back_populates="classes")
    teacher: Mapped["User | None"] = relationship(foreign_keys=[teacher_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # telegram id / web id
    name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default="student")  # student / teacher
    avatar: Mapped[str] = mapped_column(String(8), default="🐝")

    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"))
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    lang_pair_id: Mapped[int | None] = mapped_column(ForeignKey("lang_pairs.id"))

    # Аутентификация (веб/бот)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(200))

    # Геймификация
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    gems: Mapped[int] = mapped_column(Integer, default=0)
    hearts: Mapped[int] = mapped_column(Integer, default=5)
    hearts_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    daily_goal: Mapped[int] = mapped_column(Integer, default=20)
    league: Mapped[str] = mapped_column(String(24), default="bronze")

    last_active: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    school: Mapped[School | None] = relationship(foreign_keys=[school_id])
    class_group: Mapped[ClassGroup | None] = relationship(foreign_keys=[class_id])
    lang_pair: Mapped["LangPair | None"] = relationship(foreign_keys=[lang_pair_id])

    # Совместимость: «points» — это то же самое, что «xp».
    @property
    def points(self) -> int:
        return self.xp or 0

    @points.setter
    def points(self, value: int) -> None:
        self.xp = value or 0

    @property
    def lang_pair_code(self) -> str | None:
        return self.lang_pair.code if self.lang_pair else None

    __table_args__ = (
        UniqueConstraint("external_id", name="uq_user_external"),
        Index("ix_users_xp", "xp"),
        Index("ix_users_class", "class_id"),
    )
