from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


ROOT_DIR = Path(__file__).resolve().parents[2]  # bashkar root
_ENV_FILE = ROOT_DIR / ".env"

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr

    PLATFORM_API_URL: str = ""
    MINI_APP_URL: str = ""
    BOT_USERNAME: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://bashkar:bashkar@127.0.0.1:5432/bashkar"

    DEBUG: bool = True

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
