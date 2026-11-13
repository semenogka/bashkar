import os, json, uuid
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


LANG_NAMES = {"ru": "русский", "kk": "казахский", "zh": "китайский"}


def _parse_reply(raw: str) -> tuple[str, str]:
    """Разбирает ответ модели: сначала формат 'BA: ... TR: ...', затем JSON."""
    if not raw:
        return "", ""
    import re

    # 1) Формат BA:/TR:
    ba_m = re.search(r"BA\s*:\s*(.+?)(?=\n\s*TR\s*:|\Z)", raw, re.S)
    tr_m = re.search(r"TR\s*:\s*(.+?)(?=\n\s*BA\s*:|\Z)", raw, re.S)
    if ba_m:
        ba = ba_m.group(1).strip().strip('"').strip()
        tr = tr_m.group(1).strip().strip('"').strip() if tr_m else ""
        return ba, tr

    # 2) JSON
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start:end + 1])
            return (data.get("ba") or "").strip(), (data.get("translation") or "").strip()
        except Exception:
            pass

    # 3) Регулярка по JSON-полям
    return _extract_fields(raw)


def _extract_fields(raw: str) -> tuple[str, str]:
    """Достаёт ba/translation из нестрогого ответа модели."""
    if not raw:
        return "", ""
    import re
    ba = ""
    tr = ""
    m = re.search(r'"ba"\s*:\s*"(.*?)"\s*(?:,|$)', raw, re.S)
    if m:
        ba = m.group(1)
    m = re.search(r'"translation"\s*:\s*"(.*?)"\s*(?:,|})', raw, re.S)
    if m:
        tr = m.group(1)
    if not ba and not tr:
        # Модель ответила просто текстом — считаем его башкирским ответом
        ba = raw.strip()
    return ba.strip(), tr.strip()


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn):
    client = LLMClient()
    target = LANG_NAMES.get(payload.target_lang, "русский")

    system_prompt = (
        "Ты — дружелюбный репетитор башкирского языка. Ты общаешься с учеником на башкирском языке. "
        "ПРАВИЛА:\n"
        "1) Не здоровайся в каждом ответе. Приветствуй только в самом начале диалога.\n"
        "2) Учитывай всю предыдущую историю диалога, отвечай по контексту разговора.\n"
        "3) Отвечай коротко (1-3 предложения), живым разговорным башкирским языком.\n"
        "4) Если ученик сделал ошибку — мягко поправь её.\n"
        f"5) Затем переведи свой ответ на {target} язык.\n"
        "ФОРМАТ ОТВЕТА (строго, без других символов и без JSON):\n"
        "BA: <текст на башкирском>\n"
        "TR: <перевод>"
    )

    messages = [{"role": "system", "content": system_prompt}]
    # История диалога
    for m in payload.history:
        role = "assistant" if m.role == "assistant" else "user"
        messages.append({"role": role, "content": m.content})
    messages.append({"role": "user", "content": payload.message})

    raw = ""
    try:
        raw = await client.chat_completion(messages, temperature=0.7, max_tokens=512)
        raw = (raw or "").strip()
        text_ba, translation = _parse_reply(raw)
        if not text_ba:
            raise ValueError("empty reply")
    except Exception as e:
        print(f"LLM parse error: {e} | raw={raw[:200]!r}", flush=True)
        text_ba, translation = _extract_fields(raw)
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
                   voice_input=payload.voice_input)


@router.get("/tts/{filename}")
def get_audio(filename: str):
    fpath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(fpath):
        return {"error": "not found"}
    return FileResponse(fpath, media_type="audio/wav")
