from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str
    app_version: str
    debug: bool

    host: str
    port: int

    database_url: str

    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    gemini_api_key: str
    gemini_model: str

    groq_api_key: str | None = None
    groq_model: str | None = None

    primary_provider: str = "gemini"
    fallback_provider: str | None = None 

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings()