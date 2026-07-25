"""
Centralized application configuration.

All environment-dependent values are read once here via pydantic-settings
so the rest of the codebase never touches `os.environ` directly.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_NAME: str = "SmartTrip AI 2.0"
    ENVIRONMENT: str = Field(
        default="development",
        description="development | staging | production",
    )
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=True)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value):
        """
        Supports either:
        1. JSON array:
           ["https://site1.com","https://site2.com"]

        2. Comma-separated string:
           https://site1.com,https://site2.com
        """
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # ------------------------------------------------------------------
    # Firebase
    # ------------------------------------------------------------------
    FIREBASE_PROJECT_ID: str = Field(
        ...,
        description="Firebase Project ID",
    )

    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = Field(
        default=None,
        description="Firebase Service Account JSON",
    )

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str | None = None

    # ------------------------------------------------------------------
    # Gemini AI
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description="Google Gemini API Key",
    )

    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    """
    return Settings()
