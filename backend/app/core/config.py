"""Конфигурация приложения (env + .env)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
ROOT_DIR = Path(__file__).resolve().parents[3]  # bashkar root
_ENV_FILE = ROOT_DIR / ".env"


def _project_path(value: str) -> str:
    """Относительные пути считаются от корня проекта, не от текущей папки."""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((ROOT_DIR / path).resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Башкирская языковая школа"
    api_prefix: str = "/api"
    debug: bool = True

    # --- JWT (веб-аутентификация) ---
    secret_key: str = "bashkar-dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- Telegram бот ---
    bot_username: str = ""  # например: bashkar_school_bot (без @)

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://bashkar:bashkar@127.0.0.1:5432/bashkar"
    db_echo: bool = False

    # --- LLM ---
    llm_api_base_url: str = "https://api.groq.com/openai/v1/chat/completions"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: str = ""
    llm_timeout: float = 90.0

    # --- TTS / ASR ---
    tts_model: str = "facebook/mms-tts-bak"
    asr_model: str = "AigizK/GigaAM-Bashkir-CV25-ONNX"
    hf_home: str = ".cache/huggingface"

    # --- Файлы (относительно корня проекта) ---
    data_dir: str = "data"
    static_dir: str = "backend/static"
    frontend_dir: str = "frontend"
    dataset_file: str = "data/phrasebooks.jsonl"

    @field_validator("data_dir", "static_dir", "frontend_dir", "dataset_file", "hf_home")
    @classmethod
    def resolve_project_path(cls, value: str) -> str:
        return _project_path(value)

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
