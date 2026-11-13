import os, json, uuid, re
os.environ.setdefault("HF_HOME", "D:/hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "D:/hf-cache/hub")
from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List

from app.services.llm_client import LLMClient

router = APIRouter(prefix="/chat", tags=["chat"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")
os.makedirs(STATIC_DIR, exist_ok=True)

_tts_cache = {}


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatIn(BaseModel):
    user_id: Optional[int] = None
    message: str
    target_lang: str = "ru"  # ru, kk, zh
    history: List[ChatMessage] = []
    voice_input: bool = False


class ChatOut(BaseModel):
    text_ba: str
    translation: str
    audio_url: Optional[str] = None
    voice_input: bool = False
    clarify: bool = False           # бот уточняет, что имел в виду ученик
    proper: Optional[str] = None    # правильное написание (только по прямой просьбе)


LANG_NAMES = {"ru": "русский", "kk": "казахский", "zh": "китайский"}

FIELDS = ("BA", "TR", "CLARIFY", "PROPER")

# Кириллические "двойники" латинских букв — модель иногда пишет «ТR:» вместо «TR:»
HOMOGLYPHS = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y",
}


def _normalize_key(line: str) -> str:
    """Меняет кириллические двойники на латинские только в префиксе до двоеточия."""
    line = line.replace(" ", " ").replace("﻿", "")
    i = line.find(":")
    if i <= 0:
        return line
    head = line[:i]
    tail = line[i:]
    head = "".join(HOMOGLYPHS.get(ch, ch) for ch in head)
    return head + tail


def _parse_fields(raw: str) -> dict:
    """Разбирает ответ вида 'BA: ...\nTR: ...' построчно (устойчиво к двоеточиям и markdown)."""
    fields = {}
    if not raw:
        return fields
    current = None
    for line in raw.splitlines():
        line = _normalize_key(line)
        m = re.match(r"^[\s>*`#-]*\**\s*(BA|TR|CLARIFY|PROPER)\s*\**\s*[:：]\s*(.*)$", line, re.I)
        if m:
            current = m.group(1).upper()
            fields[current] = m.group(2).strip()
        elif current and line.strip():
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields


def _parse_reply(raw: str) -> tuple[str, str, bool, Optional[str]]:
    fields = _parse_fields(raw)
    if fields.get("BA"):
        cl = (fields.get("CLARIFY") or "").strip().lower()
        clarify = cl in ("да", "yes", "true", "1")
        proper = (fields.get("PROPER") or "").strip() or None
        return fields["BA"].strip(), (fields.get("TR") or "").strip(), clarify, proper

    # JSON-фолбэк
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start:end + 1])
            return ((data.get("ba") or "").strip(),
                    (data.get("translation") or "").strip(),
                    bool(data.get("clarify")),
                    (data.get("proper") or None))
        except Exception:
            pass

    ba = tr = ""
    m = re.search(r'"ba"\s*:\s*"(.*?)"\s*(?:,|$)', raw, re.S)
    if m:
        ba = m.group(1)
    m = re.search(r'"translation"\s*:\s*"(.*?)"\s*(?:,|})', raw, re.S)
    if m:
        tr = m.group(1)
    if not ba and not tr:
        ba = raw.strip()
    return ba.strip(), tr.strip(), False, None


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
    "(слова «нисек әйтергә», «нисек дә», «нисек уҡлы», «как правильно», «как произнести», "
    "«как сказать», «как это будет по-башкирски») — впиши в PROPER правильную фразу/слово "
    "на башкирском. Иначе PROPER: пусто.\n"
    "ФОРМАТ ОТВЕТА (строго, две строки, ничего больше, без markdown, метки ЛАТИНСКИМИ буквами):\n"
    "CLARIFY: <да или нет>\n"
    "PROPER: <текст на башкирском или пусто>\n"
    "ПРИМЕРЫ:\n"
    "Реплика «Күн» нисек әйтәргә керек? → CLARIFY: нет / PROPER: көн\n"
    "Реплика «минем атым атким» → CLARIFY: нет / PROPER: (пусто) — это просто опечатка\n"
    "Реплика «хәлдәр... һмм... кта...» → CLARIFY: да / PROPER: (пусто) — обрывок\n"
    "Реплика «һәр кем күрә алған әсәр» → CLARIFY: нет / PROPER: (пусто) — просто новая тема\n"
    "Реплика «бүгенгә һауа ҡарата» → CLARIFY: нет / PROPER: (пусто) — новая тема"
)


async def _run_controller(client: LLMClient, history, message: str) -> tuple[bool, Optional[str]]:
    """Отдельный вызов LLM: нужен ли уточняющий вопрос и просил ли ученик произношение."""
    convo = ""
    for m in history[-6:]:
        who = "Ученик" if m.role == "user" else "Репетитор"
        convo += f"{who}: {m.content}\n"
    convo += f"Ученик: {message}"

    try:
        raw = await client.chat_completion(
            [{"role": "system", "content": CONTROLLER_PROMPT}, {"role": "user", "content": convo}],
            temperature=0.0, max_tokens=200,
        )
        fields = _parse_fields(raw or "")
        cl = (fields.get("CLARIFY") or "").strip().lower()
        clarify = cl in ("да", "yes", "true", "1")
        proper = (fields.get("PROPER") or "").strip() or None
        return clarify, proper
    except Exception as e:
        print(f"Controller error: {e}", flush=True)
        return False, None


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn):
    client = LLMClient()
    target = LANG_NAMES.get(payload.target_lang, "русский")

    # 1) Контроллер: нужен ли уточняющий вопрос / просил ли произношение
    clarify, proper = await _run_controller(client, payload.history, payload.message)

    extra = ""
    if clarify:
        extra += (
            "Контроллер определил, что реплику ученика нельзя уверенно понять по контексту. "
            "Ответь ТОЛЬКО уточняющим вопросом и ничего больше: "
            "«Наверное, ты имел в виду «…»?» — предположи наиболее вероятный вариант. "
            "Не давай развёрнутого ответа, не объясняй тему.\n"
        )
    if proper:
        extra += (
            f"Ученик попросил правильное произношение. Правильный вариант: «{proper}». "
            "Обязательно проговори его в ответе и поясни разницу, если нужно.\n"
        )

    system_prompt = (
        "Ты — дружелюбный репетитор башкирского языка. Ты общаешься с учеником на башкирском языке. "
        "Ты отлично знаешь башкирскую грамматику и орфографию — пиши грамотно, без ошибок.\n"
        "ПРАВИЛА:\n"
        "1) Не здоровайся в каждом ответе. Приветствуй только в самом начале диалога.\n"
        "2) Учитывай всю предыдущую историю диалога, отвечай по контексту разговора.\n"
        "3) Отвечай коротко (1-3 предложения), живым разговорным башкирским языком.\n"
        "4) Если в реплике ученика опечатка или неловкая формулировка — НЕ переспрашивай, "
        "просто отвечай по делу и мягко, в самом тексте ответа, поправь слово "
        "(например «атким» → «атым»).\n"
        "5) Всегда отвечай по существу: даже если тема новая — отвечай и поддержи беседу.\n"
        + extra +
        f"6) Затем переведи свой ответ на {target} язык.\n"
        "ФОРМАТ ОТВЕТА (строго, без markdown, без звёздочек, без JSON, каждое поле с новой строки). "
        "Метки пиши ЛАТИНСКИМИ буквами BA и TR:\n"
        "BA: <текст на башкирском>\n"
        "TR: <перевод>"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for m in payload.history:
        role = "assistant" if m.role == "assistant" else "user"
        messages.append({"role": role, "content": m.content})
    messages.append({"role": "user", "content": payload.message})

    raw = ""
    text_ba = translation = ""
    try:
        raw = await client.chat_completion(messages, temperature=0.7, max_tokens=512)
        text_ba, translation, _c, _p = _parse_reply(raw)
        if not text_ba:
            raise ValueError("empty reply")
        if not translation:
            print(f"Missing TR. raw={raw[:400]!r}", flush=True)
    except Exception as e:
        print(f"LLM parse error: {e} | raw={raw[:200]!r}", flush=True)
        text_ba, translation = (raw or "").strip(), ""
        if not text_ba:
            text_ba = "Сәләм! Мин һиңә ярҙам итә алам."
            translation = "Привет! Я могу тебе помочь."

    # TTS — при голосовом вводе озвучка обязательна
    audio_url = None
    try:
        from transformers import VitsModel, AutoTokenizer
        import torch, scipy.io.wavfile

        if "tts" not in _tts_cache:
            _tts_cache["tts"] = (
                AutoTokenizer.from_pretrained("facebook/mms-tts-bak"),
                VitsModel.from_pretrained("facebook/mms-tts-bak"),
            )
        tokenizer, model = _tts_cache["tts"]
        inputs = tokenizer(text_ba, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform
        fname = f"{uuid.uuid4().hex}.wav"
        fpath = os.path.join(STATIC_DIR, fname)
        scipy.io.wavfile.write(fpath, rate=model.config.sampling_rate,
                               data=(waveform.squeeze().cpu().numpy() * 32767).astype("int16"))
        audio_url = f"/static/{fname}"
    except Exception as e:
        print(f"TTS error: {e}", flush=True)

    await client.close()
    return ChatOut(text_ba=text_ba, translation=translation, audio_url=audio_url,
                   voice_input=payload.voice_input, clarify=clarify, proper=proper)


@router.get("/tts/{filename}")
def get_audio(filename: str):
    fpath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(fpath):
        return {"error": "not found"}
    return FileResponse(fpath, media_type="audio/wav")
