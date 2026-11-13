"""Согласование переводов: большинство голосов фиксирует вариант, спорные — экспертам."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fragment, Translation, UserAnswer

PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """Нормализация для сравнения вариантов: регистр, пунктуация, лишние пробелы."""
    text = (text or "").lower().replace("ё", "е")
    text = PUNCT.sub(" ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    """Простое сходство (коэффициент Жаккара по словам)."""
    sa, sb = set(normalize(a).split()), set(normalize(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


async def collect_votes(session: AsyncSession, fragment_id: int, lang_pair_id: int) -> list[str]:
    rows = (
        await session.execute(
            select(UserAnswer.answer).where(
                UserAnswer.fragment_id == fragment_id,
                UserAnswer.lang_pair_id == lang_pair_id,
                UserAnswer.is_correct.is_(True),
            )
        )
    ).scalars().all()
    return list(rows)


async def reconcile(session: AsyncSession, fragment_id: int, lang_pair_id: int) -> dict:
    """Пересчитывает статус перевода по ответам пользователей."""
    votes = await collect_votes(session, fragment_id, lang_pair_id)
    translation = (
        await session.execute(
            select(Translation).where(
                Translation.fragment_id == fragment_id,
                Translation.lang_pair_id == lang_pair_id,
            )
        )
    ).scalar_one_or_none()
    if translation is None:
        return {"status": "missing", "votes": 0}

    if not votes:
        translation.status = "auto"
        translation.confirmed_count = 0
        return {"status": "auto", "votes": 0}

    counts = Counter(normalize(v) for v in votes)
    top_norm, top_count = counts.most_common(1)[0]
    total = sum(counts.values())
    share = top_count / total

    # Кластеризуем похожие варианты (синонимичность)
    best_text, best_votes = None, 0
    for candidate in counts:
        cluster = 0
        for vote in votes:
            if similarity(vote, candidate) >= 0.8:
                cluster += 1
        if cluster > best_votes:
            best_votes, best_text = cluster, candidate

    if best_votes >= 3 and share >= 0.6:
        original = next((v for v in votes if normalize(v) == best_text), best_text)
        translation.translation = original
        translation.status = "confirmed"
        translation.confirmed_count = best_votes
        translation.rejected_count = total - best_votes
        translation.updated_at = datetime.utcnow()
        return {
            "status": "confirmed",
            "votes": total,
            "confirmed_count": best_votes,
            "translation": original,
        }

    if len(counts) > 1 and best_votes >= 2:
        translation.status = "expert_review"
        translation.confirmed_count = best_votes
        translation.rejected_count = total - best_votes
        return {
            "status": "expert_review",
            "votes": total,
            "variants": counts.most_common(),
        }

    translation.status = "auto"
    translation.confirmed_count = best_votes
    return {"status": "auto", "votes": total}


async def disputed_list(session: AsyncSession, limit: int = 100) -> list[dict]:
    """Список спорных случаев для передачи экспертам (УФИЦ РАН)."""
    rows = (
        await session.execute(
            select(Translation, Fragment)
            .join(Fragment, Fragment.id == Translation.fragment_id)
            .where(Translation.status == "expert_review")
            .limit(limit)
        )
    ).all()
    result = []
    for tr, frag in rows:
        votes = await collect_votes(session, frag.id, tr.lang_pair_id)
        result.append({
            "translation_id": tr.id,
            "fragment_id": frag.fragment_id,
            "text_ba": frag.text_ba,
            "source": frag.source,
            "translation": tr.translation,
            "confirmed_count": tr.confirmed_count,
            "rejected_count": tr.rejected_count,
            "variants": Counter(normalize(v) for v in votes).most_common(),
        })
    return result
