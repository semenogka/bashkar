import os, json, uuid
os.environ.setdefault("HF_HOME", "D:/hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "D:/hf-cache/hub")
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db import get_db
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/chat", tags=["chat"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")
os.makedirs(STATIC_DIR, exist_ok=True)


class ChatIn(BaseModel):
    user_id: Optional[int] = None
    message: str
    target_lang: str = "ru"  # ru, kk, zh


class ChatOut(BaseModel):
    text_ba: str
    translation: str
    audio_url: Optional[str] = None


LANG_NAMES = {"ru": "русский", "kk": "казахский", "zh": "китайский"}


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn):
    client = LLMClient()
    target = LANG_NAMES.get(payload.target_lang, "русский")

    system_prompt = (
        "Ты — дружелюбный помощник, который общается на башкирском языке. "
        "Ответь на сообщение пользователя на башкирском (2-4 предложения). "
        f"Затем переведи свой ответ на {target} язык. "
        "Верни ТОЛЬКО JSON без markdown: {\"ba\": \"текст на башкирском\", \"translation\": \"перевод\"}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload.message},
    ]

    try:
        raw = await client.chat_completion(messages, temperature=0.7, max_tokens=512)
        # Парсим JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        text_ba = data.get("ba", raw)
        translation = data.get("translation", "")
    except Exception as e:
        text_ba = "Сәләм! Мин һиңә ярҙам итә алам."
        translation = "Привет! Я могу тебе помочь."
        print(f"LLM error: {e}", flush=True)

    # TTS
    audio_url = None
    try:
        from transformers import VitsModel, AutoTokenizer
        import torch, scipy.io.wavfile
        import numpy as np
        tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-bak")
        model = VitsModel.from_pretrained("facebook/mms-tts-bak")
        inputs = tokenizer(text_ba, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform
        fname = f"{uuid.uuid4().hex}.wav"
        fpath = os.path.join(STATIC_DIR, fname)
        scipy.io.wavfile.write(fpath, rate=model.config.sampling_rate,
                               data=(waveform.squeeze().cpu().numpy() * 32767).astype("int16"))
        audio_url = f"/static/{fname}"
    except Exception as e:
        print(f"TTS error: {e}")

    await client.close()
    return ChatOut(text_ba=text_ba, translation=translation, audio_url=audio_url)


@router.get("/tts/{filename}")
def get_audio(filename: str):
    fpath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(fpath):
        return {"error": "not found"}
    return FileResponse(fpath, media_type="audio/wav")