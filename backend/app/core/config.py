from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "bashkar-backend"
    debug: bool = False
    database_url: str = "sqlite:///./app.db"
    secret_key: str = "change-me"
    llm_api_base_url: str = "https://api.groq.com/openai/v1/chat/completions"
    llm_model: str = "llama3-8b-8192"
    llm_api_key: str = ""


settings = Settings()