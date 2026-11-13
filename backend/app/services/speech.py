"""Синтез речи (TTS) и распознавание речи (ASR) — асинхронно, с ленивой загрузкой моделей."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("bashkar.speech")

_tts_lock = threading.Lock()
_tts_state: dict[str, object] = {}
_asr_lock = threading.Lock()
_asr_state: dict[str, object] = {}


def _write_wav(path: Path, rate: int, samples) -> None:
    import numpy as np
    import scipy.io.wavfile

    data = np.asarray(samples, dtype="float32")
    peak = float(np.max(np.abs(data))) or 1.0
    if peak > 1.0:
        data = data / peak
    pcm = (data * 32767).astype("int16")
    scipy.io.wavfile.write(path, rate=rate, data=pcm)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def _tts_load():
    from transformers import AutoTokenizer, VitsModel

    tokenizer = AutoTokenizer.from_pretrained(settings.tts_model)
    model = VitsModel.from_pretrained(settings.tts_model)
    model.eval()
    return tokenizer, model


def _tts_sync(text: str, out_path: Path) -> tuple[int, float]:
    import torch

    with _tts_lock:
        if "tokenizer" not in _tts_state:
            logger.info("Загружаю TTS-модель %s", settings.tts_model)
            tokenizer, model = _tts_load()
            _tts_state["tokenizer"] = tokenizer
            _tts_state["model"] = model
        tokenizer = _tts_state["tokenizer"]
        model = _tts_state["model"]

        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform
        rate = int(model.config.sampling_rate)
        samples = waveform.squeeze().cpu().numpy()
        _write_wav(out_path, rate, samples)
        return rate, float(len(samples) / rate)


async def synthesize(text: str, *, folder: str | None = None) -> dict | None:
    """Синтезирует речь. Возвращает {url, filename, duration, sample_rate}."""
    text = (text or "").strip()
    if not text:
        return None
    target_dir = Path(folder or settings.static_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.wav"
    out_path = target_dir / name
    try:
        rate, duration = await asyncio.to_thread(_tts_sync, text, out_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("TTS failed: %s", exc)
        return None
    return {
        "url": f"/static/{name}",
        "filename": name,
        "duration": round(duration, 2),
        "sample_rate": rate,
    }


# ---------------------------------------------------------------------------
# ASR
# ---------------------------------------------------------------------------
def _asr_load():
    import onnx_asr

    return onnx_asr.load_model(settings.asr_model)


def _asr_sync(path: str) -> str:
    with _asr_lock:
        if "model" not in _asr_state:
            logger.info("Загружаю ASR-модель %s", settings.asr_model)
            _asr_state["model"] = _asr_load()
        model = _asr_state["model"]
        return model.recognize(path)


async def transcribe(path: str) -> str:
    """Распознаёт башкирскую речь из wav-файла."""
    text = await asyncio.to_thread(_asr_sync, path)
    return (text or "").strip()


def to_int16_wav(src: str, dst: str) -> str:
    """Переводит произвольный звук в WAV 16-bit (нужно для ASR)."""
    import numpy as np
    import scipy.io.wavfile as wav

    try:
        rate, data = wav.read(src)
    except Exception:  # noqa: BLE001
        return src
    if data.dtype != np.int16:
        if np.issubdtype(data.dtype, np.floating):
            data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        else:
            data = data.astype(np.int16)
        wav.write(dst, rate, data)
        return dst
    return src
