"""Озвучка (TTS) и распознавание речи (ASR)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.schemas import AsrOut, TtsOut
from app.services.speech import synthesize, to_int16_wav, transcribe

router = APIRouter(prefix="/speech", tags=["speech"])


class TtsRequest(BaseModel):
    text: str
    lang: str = "ba"


@router.post("/tts", response_model=TtsOut)
async def tts(payload: TtsRequest):
    """Синтез речи. Для башкирского используется MMS-TTS."""
    if not payload.text or not payload.text.strip():
        raise HTTPException(400, "Пустой текст")
    result = await synthesize(payload.text.strip())
    if result is None:
        raise HTTPException(500, "Не удалось синтезировать речь")
    return TtsOut(**result)


@router.get("/tts")
async def tts_get(text: str, lang: str = "ba"):
    if not text or not text.strip():
        raise HTTPException(400, "Пустой текст")
    result = await synthesize(text.strip())
    if result is None:
        raise HTTPException(500, "Не удалось синтезировать речь")
    return TtsOut(**result)


@router.post("/asr", response_model=AsrOut)
async def asr(file: UploadFile = File(...)):
    """Распознавание башкирской речи (wav/webm/mp3)."""
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    wav_path = tmp_path + ".16k.wav"
    try:
        converted = to_int16_wav(tmp_path, wav_path)
        text = await transcribe(converted)
        return AsrOut(text=text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Ошибка распознавания: {exc}") from exc
    finally:
        for path in (tmp_path, wav_path):
            try:
                Path(path).unlink()
            except OSError:
                pass
