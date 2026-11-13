"""Модели контента: языки, языковые пары, фрагменты и переводы."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Language(Base):
    __tablename__ = "languages"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(64))
    flag: Mapped[str | None] = mapped_column(String(8))
    is_source: Mapped[bool] = mapped_column(Boolean, default=False)

    pairs_as_source: Mapped[list["LangPair"]] = relationship(
        back_populates="source_lang_rel", foreign_keys="LangPair.source_lang"
    )


class LangPair(Base):
    __tablename__ = "lang_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # ba-ru
    source_lang: Mapped[str] = mapped_column(ForeignKey("languages.code"), nullable=False)
    target_lang: Mapped[str] = mapped_column(ForeignKey("languages.code"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    native_label: Mapped[str | None] = mapped_column(String(64))

    source_lang_rel: Mapped[Language] = relationship(
        back_populates="pairs_as_source", foreign_keys=[source_lang]
    )
    target_lang_rel: Mapped[Language] = relationship(foreign_keys=[target_lang])

    __table_args__ = (UniqueConstraint("source_lang", "target_lang", name="uq_lang_pair"),)


class Fragment(Base):
    """Фрагмент исходного текста на башкирском с координатами источника."""

    __tablename__ = "fragments"

    id: Mapped[int] = mapped_column(primary_key=True)
    fragment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    text_ba: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(256))
    source_type: Mapped[str | None] = mapped_column(String(32))  # phrasebook / book / audio
    topic: Mapped[str | None] = mapped_column(String(64))
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    lang_pair: Mapped[str | None] = mapped_column(String(16))
    auto_translation: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    translations: Mapped[list["Translation"]] = relationship(
        back_populates="fragment", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_fragments_difficulty", "difficulty"),)


class Translation(Base):
    """Перевод фрагмента на конкретный язык (в т.ч. автоперевод)."""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    fragment_id: Mapped[int] = mapped_column(ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False)
    lang_pair_id: Mapped[int] = mapped_column(ForeignKey("lang_pairs.id"), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="auto")  # auto/confirmed/expert_review
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    is_machine: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    fragment: Mapped[Fragment] = relationship(back_populates="translations")
    lang_pair: Mapped[LangPair] = relationship()

    __table_args__ = (
        UniqueConstraint("fragment_id", "lang_pair_id", name="uq_fragment_pair"),
        Index("ix_translations_pair_status", "lang_pair_id", "status"),
    )
