"""Чат-репетитор: LLM отвечает на башкирском, переводит, озвучивает и капает XP."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import User
from app.schemas import BadgeOut, ChatIn, ChatOut
from app.services.gamification import add_xp, award_badges, touch_streak, update_daily_tasks
from app.services.llm_client import LLMClient, parse_reply
from app.services.speech import synthesize

logger = logging.getLogger("bashkar.chat")
router = APIRouter(prefix="/chat", tags=["chat"])

LANG_NAMES = {"ru": "русский", "kk": "казахский", "zh": "китайский"}

CONTROLLER_PROMPT = (
    "Ты — контроллер диалога башкирского репетитора. Ниже история диалога и последняя реплика ученика.\n"
    "Твоя задача — решить, нужно ли уточнять реплику. По умолчанию НЕ уточнять.\n"
    "Ответь «CLARIFY: да» ТОЛЬКО в двух случаях:\n"
    "  а) реплику ФИЗИЧЕСКИ НЕВОЗМОЖНО понять: она оборвана, состоит из обрывков, "
    "междометий или шума («хмм... кта...», «ааа», «ну...»);\n"
    "  б) реплика явно относится к ДРУГОМУ ЧЕЛОВЕКУ/СИТУАЦИИ, а не к ученику-репетитору "
    "(например, «передай Маше, что я опоздал» или «купи хлеб» — это не задание репетитору).\n"
    "Во ВСЕХ остальных случаях — «CLARIFY: нет». В частности НЕ уточняй, если:\n"
    "  - есть опечатка или неловкая формулировка;\n"
    "  - реплика меняет тему разговора (это нормально, просто отвечай по существу);\n"
    "  - реплика — обычный вопрос или утверждение на любом языке.\n"
    "Отдельно: если ученик прямо просит правильное написание или произношение "
    "(«нисек әйтергә», «нисек дә», «нисек уҡлы», «как правильно», «как произнести», "
    "«как сказать», «как это будет по-башкирски») — впиши в PROPER правильную фразу/слово "
    "на башкирском. Иначе PROPER: пусто.\n"
    "ФОРМАТ ОТВЕТА (строго, две строки, ничего больше, без markdown, метки ЛАТИНСКИМИ буквами):\n"
    "CLARIFY: <да или нет>\n"
    "PROPER: <текст на башкирском или пусто>"
)


async def _controller(client: LLMClient, history: list[dict], message: str) -> tuple[bool, str | None]:
    convo = ""
    for item in history[-6:]:
        who = "Ученик" if item.get("role") == "user" else "Репетитор"
        convo += f"{who}: {item.get('content', '')}\n"
    convo += f"Ученик: {message}"
    try:
        raw = await client.chat(
            [{"role": "system", "content": CONTROLLER_PROMPT}, {"role": "user", "content": convo}],
            temperature=0.0, max_tokens=200,
        )
        from app.services.llm_client import parse_fields

        fields = parse_fields(raw or "")
        cl = (fields.get("CLARIFY") or "").strip().lower()
        clarify = cl in ("да", "yes", "true", "1")
        proper = (fields.get("PROPER") or "").strip() or None
        return clarify, proper
    except Exception as exc:  # noqa: BLE001
        logger.warning("Controller failed: %s", exc)
        return False, None


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn, session: AsyncSession = Depends(get_session)):
    client = LLMClient()
    target = LANG_NAMES.get(payload.target_lang, "русский")

    try:
        clarify, proper = await _controller(client, payload.history, payload.message)
    except Exception:  # noqa: BLE001
        clarify, proper = False, None

    extra = ""
    if clarify:
        extra += (
            "Контроллер определил, что реплику ученика нельзя уверенно понять по контексту. "
            "Ответь ТОЛЬКО уточняющим вопросом и ничего больше: "
            "«Наверное, ты имел в виду «…»?» — предположи наиболее вероятный вариант.\n"
        )
    if proper:
        extra += (
            f"Ученик попросил правильное произношение. Правильный вариант: «{proper}». "
            "Обязательно проговори его в ответе и поясни разницу, если нужно.\n"
        )

    system_prompt = (
        "Ты — дружелюбный репетитор башкирского языка, носитель башкирского языка. "
        "Ты общаешься с учеником на башкирском языке.\n"
        "Ты отлично знаешь башкирскую грамматику и орфографию — пиши грамотно, без ошибок. "
        "Используй только настоящие башкирские буквы (Ә Ө Ү Ҡ Ң Һ Ҫ Ә Җ) и правильные окончания.\n"
        "ПРАВИЛА:\n"
        "1) Не здоровайся в каждом ответе. Приветствуй только в самом начале диалога.\n"
        "2) Учитывай всю предыдущую историю диалога, отвечай по контексту разговора.\n"
        "3) Отвечай коротко (1-3 предложения), живым разговорным башкирским языком.\n"
        "4) Если в реплике ученика опечатка или неловкая формулировка — НЕ переспрашивай, "
        "просто отвечай по делу и мягко, в самом тексте ответа, поправь слово "
        "(например «атким» → «атым»).\n"
        "5) Всегда отвечай по существу: даже если тема новая — отвечай и поддержи беседу.\n"
        "ПРИМЕРЫ ТВОИХ ОТВЕТОВ (стиль):\n"
        "Ученик: «Бүгенгә һауа ҡарата» → BA: Бүгөн һауа ҡарата: көн тик көтә, һылыу бар.\n"
        "Ученик: «Минем исемем Хәмит» → BA: Рәхим итегеҙ, Хәмит! Ҡасан даулашаһың?\n"
        + extra
        + f"6) Затем переведи свой ответ на {target} язык.\n"
        "ФОРМАТ ОТВЕТА (строго, без markdown, без звёздочек, без JSON, каждое поле с новой строки). "
        "Метки пиши ЛАТИНСКИМИ буквами BA и TR:\n"
        "BA: <текст на башкирском>\n"
        "TR: <перевод>"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for item in payload.history:
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = item.get("content") or ""
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": payload.message})

    text_ba = ""
    translation = ""
    try:
        raw = await client.chat(messages, temperature=0.7, max_tokens=512)
        text_ba, translation, _c, _p = parse_reply(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM failed: %s", exc)
    finally:
        await client.close()

    if not text_ba:
        text_ba = "Сәләм! Мин һиңә ярҙам итә алам."
        translation = "Привет! Я могу тебе помочь."

    # Озвучка ответа
    audio = await synthesize(text_ba)

    # Геймификация: практика языка тоже даёт XP
    xp_gained = 0
    level, streak, badges = 1, 0, []
    if payload.user_id:
        user = await session.get(User, payload.user_id)
        if user:
            xp_gained = 5
            add_xp(user, xp_gained)
            await touch_streak(session, user, xp=xp_gained)
            await update_daily_tasks(session, user, card_done=True)
            await session.commit()
            badges = await award_badges(session, user)
            await session.commit()
            level = user.level
            streak = user.streak

    return ChatOut(
        text_ba=text_ba,
        translation=translation,
        audio=audio,
        clarify=clarify,
        proper=proper,
        xp_gained=xp_gained,
        level=level,
        streak=streak,
        new_badges=[BadgeOut.model_validate(b) for b in badges],
    )
