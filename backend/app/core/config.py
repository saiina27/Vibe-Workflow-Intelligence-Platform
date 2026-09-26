from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str
    app_version: str
    debug: bool

    host: str
    port: int

    cors_origins: str = "http://localhost:5173"

    database_url: str

    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    gemini_api_key: str
    gemini_model: str

    groq_api_key: str | None = None
    groq_model: str | None = None

    tavily_api_key: str | None = None

    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_redirect_uri: str | None = None
    github_oauth_scope: str = "read:user"

    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_redirect_uri: str | None = None
    slack_oauth_scope: str = (
        "search:read"
    )
    slack_mcp_url: str = "https://mcp.slack.com/mcp"
    oauth_encryption_key: str | None = None

    primary_provider: str = "gemini"
    fallback_provider: str | None = None 

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings()