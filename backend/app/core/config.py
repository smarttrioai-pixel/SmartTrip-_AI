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
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=True)

    # --- CORS ---
    # Accepts either a JSON array (`["https://a.com","https://b.com"]`) or a
    # plain comma-separated string (`https://a.com,https://b.com`) — the
    # latter is what most people naturally type into a dashboard env var
    # field, and pydantic-settings' default strict-JSON parsing for list
    # fields rejects it outright, which is what caused the SettingsError.
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # --- Firebase / Firestore (primary datastore) ---
    FIREBASE_PROJECT_ID: str = Field(..., description="GCP/Firebase project id")
    # Path to a service account JSON file. Leave unset to use Application
    # Default Credentials instead (recommended on Cloud Run/GCP).
    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = None

    # --- Redis (optional, used for refresh-token/session revocation) ---
    REDIS_URL: str | None = None

    # --- Gemini ---
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-1.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this, don't instantiate Settings() directly."""
    return Settings()  # type: ignore[call-arg]  # values come from environment / .env
