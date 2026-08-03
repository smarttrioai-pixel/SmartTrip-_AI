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
    # LLM Provider selection
    # Changing this value is the ONLY code-free way to switch AI providers.
    # Supported: "huggingface" (default) | "gemini"
    # ------------------------------------------------------------------
    LLM_PROVIDER: str = Field(
        default="huggingface",
        description="Active LLM provider: 'huggingface' (default) or 'gemini'",
    )

    # ------------------------------------------------------------------
    # Hugging Face Inference API
    # ------------------------------------------------------------------
    HF_API_TOKEN: str | None = Field(
        default=None,
        description="Hugging Face API token (required for text generation)",
    )

    HF_MODEL: str = Field(
        default="google/gemma-3-4b-it",
        description=(
            "Hugging Face model for text generation. "
            "Must be available on the HF Inference API (no local download). "
            "Default: google/gemma-3-4b-it (lightweight instruction-tuned Gemma)."
        ),
    )

    HF_EMBEDDING_MODEL: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Hugging Face model for text embeddings via feature_extraction.",
    )

    # ------------------------------------------------------------------
    # Gemini AI  — VISION ONLY
    # Gemini is used exclusively for multimodal Vision tasks:
    #   landmark recognition, image understanding, AR Explore, Vision Q&A.
    # All text generation uses the provider selected by LLM_PROVIDER above.
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description="Google Gemini API Key (required for Vision endpoints only)",
    )

    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model for Vision tasks only",
    )

    # ------------------------------------------------------------------
    # External integrations
    # ------------------------------------------------------------------
    OPENTRIPMAP_API_KEY: str | None = Field(
        default=None,
        description="OpenTripMap API key — POI search returns an empty result if unset, never a fabricated fallback",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    """
    return Settings()
