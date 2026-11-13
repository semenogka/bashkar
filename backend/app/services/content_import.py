"""Импорт датасета trilingual-parallel-phrasebooks-bgpu в базу."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Fragment, LangPair, Language, Translation

logger = logging.getLogger("bashkar.import")

LANG_META = {
    "ba": ("Башкирский", "Башҡорт теле", "🇷🇺"),
    "ru": ("Русский", "Русский", "🇷🇺"),
    "kk": ("Казахский", "Қазақ тілі", "🇰🇿"),
    "zh": ("Китайский", "中文", "🇨🇳"),
    "alt": ("Алтайский", "Алтай язык", "🇷🇺"),
    "ar": ("Арабский", "العربية", "🇸🇦"),
    "sah": ("Якутский (саха)", "Сахалыы", "🇷🇺"),
}

# Активные языковые пары, которые мы открываем пользователям
ACTIVE_PAIRS = [("ba", "ru"), ("ba", "kk"), ("ba", "zh")]


async def ensure_language(session: AsyncSession, code: str) -> Language:
    lang = await session.get(Language, code)
    if lang is None:
        name, native, flag = LANG_META.get(code, (code, code, "🏳️"))
        lang = Language(code=code, name=name, native_name=native, flag=flag,
                        is_source=(code == "ba"))
        session.add(lang)
        await session.flush()
    return lang


async def ensure_lang_pair(session: AsyncSession, source: str, target: str) -> LangPair:
    code = f"{source}-{target}"
    pair = (
        await session.execute(select(LangPair).where(LangPair.code == code))
    ).scalar_one_or_none()
    if pair is None:
        await ensure_language(session, source)
        await ensure_language(session, target)
        _, native, flag = LANG_META.get(target, (target, target, "🏳️"))
        pair = LangPair(code=code, source_lang=source, target_lang=target, enabled=True,
                        native_label=f"{flag} {native}")
        session.add(pair)
        await session.flush()
    return pair


async def seed_reference_data(session: AsyncSession) -> None:
    """Языки, языковые пары и каталог бейджей."""
    from app.models import Badge
    from app.services.gamification import BADGE_CATALOG

    for code in LANG_META:
        await ensure_language(session, code)
    for src, dst in ACTIVE_PAIRS:
        await ensure_lang_pair(session, src, dst)

    for spec in BADGE_CATALOG:
        exists = await session.get(Badge, spec["code"])
        if exists is None:
            session.add(Badge(**spec))
    await session.commit()


async def import_phrasebooks(
    session: AsyncSession, path: str | None = None, *, batch: int = 500
) -> dict:
    """Импортирует jsonl-датасет. Возвращает статистику."""
    file_path = Path(path or settings.dataset_file)
    if not file_path.exists():
        logger.warning("Файл датасета не найден: %s", file_path)
        return {"error": "dataset_not_found", "path": str(file_path)}

    await seed_reference_data(session)

    created_fragments = 0
    created_translations = 0
    skipped = 0
    total = 0

    buffer: list[dict] = []
    with file_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            buffer.append(json.loads(line))
            if len(buffer) >= batch:
                c, t = await _flush(session, buffer)
                created_fragments += c
                created_translations += t
                total += len(buffer)
                buffer.clear()
                logger.info("Импортировано %s фрагментов", total)
    if buffer:
        c, t = await _flush(session, buffer)
        created_fragments += c
        created_translations += t
        total += len(buffer)

    await session.commit()
    return {
        "total_rows": total,
        "created_fragments": created_fragments,
        "created_translations": created_translations,
        "skipped": skipped,
    }


async def _flush(session: AsyncSession, rows: list[dict]) -> tuple[int, int]:
    created_fragments = 0
    created_translations = 0

    existing_ids = set(
        (
            await session.execute(
                select(Fragment.fragment_id).where(
                    Fragment.fragment_id.in_([r.get("id") for r in rows if r.get("id")])
                )
            )
        ).scalars().all()
    )

    fragments: dict[str, Fragment] = {}
    for row in rows:
        ext_id = row.get("id")
        text_ba = (row.get("text_ba") or "").strip()
        if not ext_id or not text_ba:
            continue
        if ext_id in existing_ids:
            frag = (
                await session.execute(
                    select(Fragment).where(Fragment.fragment_id == ext_id)
                )
            ).scalar_one_or_none()
            if frag is None:
                continue
        else:
            frag = Fragment(
                fragment_id=ext_id,
                text_ba=text_ba,
                source=f"phrasebook bgpu, {ext_id}",
                source_type="phrasebook",
                topic="phrases",
                difficulty=1 + (len(text_ba) // 40),
            )
            session.add(frag)
            await session.flush()
            existing_ids.add(ext_id)
            created_fragments += 1
        fragments[ext_id] = frag

    # Переводы
    pairs: dict[str, LangPair] = {}
    for src, dst in ACTIVE_PAIRS + [("ba", "alt"), ("ba", "ar"), ("ba", "sah")]:
        pairs[f"{src}-{dst}"] = await ensure_lang_pair(session, src, dst)

    for row in rows:
        frag = fragments.get(row.get("id"))
        if frag is None:
            continue
        candidates: list[tuple[str, str]] = []
        if row.get("text_ru"):
            candidates.append(("ba-ru", row["text_ru"]))
        other = row.get("lang_other")
        if row.get("text_other") and other:
            candidates.append((f"ba-{other}", row["text_other"]))
        for code, text in candidates:
            pair = pairs.get(code)
            if pair is None:
                continue
            text = (text or "").strip()
            if not text:
                continue
            exists = (
                await session.execute(
                    select(Translation.id).where(
                        Translation.fragment_id == frag.id,
                        Translation.lang_pair_id == pair.id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    Translation(
                        fragment_id=frag.id,
                        lang_pair_id=pair.id,
                        translation=text,
                        status="auto",
                        is_machine=True,
                    )
                )
                created_translations += 1
    await session.flush()
    return created_fragments, created_translations


async def content_stats(session: AsyncSession) -> dict:
    fragments = (await session.execute(select(func.count()).select_from(Fragment))).scalar_one()
    translations = (await session.execute(select(func.count()).select_from(Translation))).scalar_one()
    confirmed = (
        await session.execute(
            select(func.count()).select_from(Translation).where(Translation.status == "confirmed")
        )
    ).scalar_one()
    review = (
        await session.execute(
            select(func.count()).select_from(Translation).where(Translation.status == "expert_review")
        )
    ).scalar_one()
    return {
        "fragments": fragments,
        "translations": translations,
        "confirmed": confirmed,
        "expert_review": review,
    }
