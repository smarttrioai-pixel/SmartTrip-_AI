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
    # ------------------------------------------------------------------
    LLM_PROVIDER: str = Field(
        default="gemini",
        description="Primary LLM provider: 'gemini' (default)",
    )

    # ------------------------------------------------------------------
    # PDF export
    # ------------------------------------------------------------------
    DIARY_PDF_ENABLED: bool = Field(
        default=True,
        description="Enable real PDF export via reportlab",
    )

    # ------------------------------------------------------------------
    # Hugging Face Inference API  — EMBEDDINGS ONLY
    # HuggingFace is used exclusively for sentence-transformer embeddings
    # (MemoryEngine similarity search). Text generation uses Groq above.
    # ------------------------------------------------------------------
    HF_API_TOKEN: str | None = Field(
        default=None,
        description="Hugging Face API token (required for embedding service)",
    )

    HF_EMBEDDING_MODEL: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Hugging Face model for text embeddings via feature_extraction.",
    )

    # ------------------------------------------------------------------
    # Gemini AI  — PRIMARY LLM + VISION
    # ALL text generation (itinerary, chat, diary, Q&A) routes through Gemini.
    # Vision stays in app/integrations/gemini_vision_service.py.
    #
    # MULTI-KEY ROTATION:
    #   Set GEMINI_API_KEYS as a comma-separated list of API keys.
    #   Example: GEMINI_API_KEYS=AIzaKey1,AIzaKey2,AIzaKey3
    #   The provider rotates to the next key automatically on 429 / quota errors.
    #   GEMINI_API_KEY (single key) is also supported as a fallback.
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description=(
            "Single Google Gemini API Key. Used if GEMINI_API_KEYS is not set. "
            "For multi-key rotation, use GEMINI_API_KEYS instead."
        ),
    )

    GEMINI_API_KEYS: str | None = Field(
        default=None,
        description=(
            "Comma-separated list of Google Gemini API Keys for automatic key rotation. "
            "Example: AIzaKey1,AIzaKey2,AIzaKey3. "
            "When a key hits its quota (429), the provider automatically tries the next key."
        ),
    )

    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model for all text generation and vision tasks.",
    )

    def get_gemini_api_keys(self) -> list[str]:
        """
        Return the list of Gemini API keys for multi-key rotation.
        Prefers GEMINI_API_KEYS (comma-separated) over single GEMINI_API_KEY.
        """
        if self.GEMINI_API_KEYS:
            keys = [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]
            if keys:
                return keys
        if self.GEMINI_API_KEY:
            return [self.GEMINI_API_KEY]
        return []

    # ------------------------------------------------------------------
    # External integrations
    # ------------------------------------------------------------------

    # OpenTripMap — kept for backward-compat with existing .env files.
    # No longer used in the active runtime place-discovery path.
    OPENTRIPMAP_API_KEY: str | None = Field(
        default=None,
        description="OpenTripMap API key — retained for backward compatibility, superseded by Geoapify",
    )

    # ------------------------------------------------------------------
    # Geoapify Places API  — PRIMARY place discovery / verification
    # Qwen proposes intent; Geoapify verifies real geographic places.
    # Never expose this key to frontend code.
    # ------------------------------------------------------------------
    GEOAPIFY_API_KEY: str | None = Field(
        default=None,
        description=(
            "Geoapify API key — required for place enrichment, attraction search, "
            "restaurant discovery, and geocoding. If unset the enrichment service "
            "returns controlled empty results; the app continues to run."
        ),
    )

    GEOAPIFY_BASE_URL: str = Field(
        default="https://api.geoapify.com",
        description="Geoapify API base URL",
    )

    GEOAPIFY_TIMEOUT_SECONDS: int = Field(
        default=10,
        description="HTTP timeout in seconds for Geoapify API requests",
    )

    # ------------------------------------------------------------------
    # Google Places API (New)  — PRIMARY place discovery / enrichment
    # Uses places.googleapis.com/v1/places:searchNearby and :searchText.
    # Requires "Places API (New)" enabled in Google Cloud Console.
    # Geoapify is used as fallback when Google is unavailable or returns
    # insufficient results.
    # NEVER expose this key to frontend code or logs.
    # ------------------------------------------------------------------
    GOOGLE_PLACES_API_KEY: str | None = Field(
        default=None,
        description=(
            "Google Places API (New) key. Required for primary place discovery. "
            "If unset, the system falls back to Geoapify automatically."
        ),
    )

    GOOGLE_PLACES_BASE_URL: str = Field(
        default="https://places.googleapis.com/v1",
        description="Google Places API (New) base URL",
    )

    GOOGLE_PLACES_TIMEOUT_SECONDS: int = Field(
        default=10,
        description="HTTP timeout in seconds for Google Places API requests",
    )

    # ------------------------------------------------------------------
    # Place provider selection
    # ------------------------------------------------------------------
    PLACE_PROVIDER: str = Field(
        default="google",
        description=(
            "Primary place provider: 'google' (default) | 'geoapify'. "
            "Set to 'geoapify' to skip Google and use only Geoapify."
        ),
    )

    ENABLE_GEOAPIFY_FALLBACK: bool = Field(
        default=True,
        description=(
            "When True, Geoapify is used as fallback if Google Places fails "
            "or returns 0 results. Set False to disable Geoapify entirely."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    """
    return Settings()
