"""Конфигурация приложения (env + .env)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Башкирская языковая школа"
    api_prefix: str = "/api"
    debug: bool = True

    # --- JWT (веб-аутентификация) ---
    secret_key: str = "bashkar-dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- PostgreSQL (диск D) ---
    database_url: str = "postgresql+asyncpg://bashkar:bashkar@127.0.0.1:5432/bashkar"
    db_echo: bool = False

    # --- LLM ---
    llm_api_base_url: str = "https://api.groq.com/openai/v1/chat/completions"
    llm_model: str = "llama3-8b-8192"
    llm_api_key: str = ""
    llm_timeout: float = 90.0

    # --- TTS / ASR ---
    tts_model: str = "facebook/mms-tts-bak"
    asr_model: str = "AigizK/GigaAM-Bashkir-CV25-ONNX"
    hf_home: str = "D:/hf-cache"

    # --- Файлы ---
    data_dir: str = str(BASE_DIR.parent / "data")
    static_dir: str = str(BASE_DIR / "static")
    frontend_dir: str = str(BASE_DIR.parent / "frontend" / "хакатон")
    dataset_file: str = str(BASE_DIR.parent / "data" / "phrasebooks.jsonl")

    # --- Геймификация ---
    hearts_max: int = 5
    hearts_refill_seconds: int = 3600
    daily_cards_goal: int = 20
    xp_per_correct: int = 10
    xp_per_speed_correct: int = 15
    xp_per_duel_win: int = 30


settings = Settings()

os.environ.setdefault("HF_HOME", settings.hf_home)
os.environ.setdefault("HF_HUB_CACHE", f"{settings.hf_home}/hub")

Path(settings.static_dir).mkdir(parents=True, exist_ok=True)
