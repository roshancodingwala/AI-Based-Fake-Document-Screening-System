"""
Central configuration for the SENTRY-ID backend.

All values can be overridden with environment variables (see .env.example).
Kept deliberately simple for a prototype — a real deployment should pull
secrets from a proper secret manager, not a .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SENTRY-ID Backend"
    environment: str = "prototype"

    # --- Auth -----------------------------------------------------------
    # Simple static API key auth for the prototype. Replace with OAuth2 /
    # mTLS / an identity provider before this ever touches real traffic.
    api_key: str = "demo-officer-key-12345"
    api_key_header_name: str = "X-API-Key"

    # --- Database ---------------------------------------------------------
    # SQLite by default so the prototype runs with zero external services.
    # Swap DATABASE_URL for a real Postgres DSN in production, e.g.:
    #   postgresql+psycopg2://user:password@host:5432/sentry_id
    database_url: str = "sqlite:///./sentry_id.db"

    # --- File upload limits & document formats ----------------------------
    max_upload_size_mb: int = 10
    allowed_content_types: tuple = (
        "image/jpeg",
        "image/jpg",
        "image/pjpeg",
        "image/png",
        "application/pdf",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "application/octet-stream",
    )
    extracted_faces_dir: str = "extracted_faces"

    # --- Risk engine thresholds --------------------------------------------
    risk_low_max: int = 39
    risk_medium_max: int = 74
    # anything above risk_medium_max is HIGH

    # --- Identity search -----------------------------------------------
    identity_match_threshold: float = 0.80  # below this we don't surface a match at all
    identity_review_threshold: float = 0.90  # above this we flag for mandatory officer review

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SENTRY_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
