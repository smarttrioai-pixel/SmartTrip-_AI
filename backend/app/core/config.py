"""
Centralized application configuration.

All environment-dependent values are read once here via pydantic-settings
so the rest of the codebase never touches `os.environ` directly.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "SmartTrip AI 2.0"
    ENVIRONMENT: str = Field(default="development")
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=True)

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # --- Firebase / Firestore ---
    FIREBASE_PROJECT_ID: str = Field(..., description="GCP/Firebase project id")
    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = None

    # --- Redis (optional) ---
    REDIS_URL: str | None = None

    # --- Gemini ---
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-1.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this, don't instantiate Settings() directly."""
    return Settings()  # type: ignore[call-arg]
