"""Application configuration loaded from environment variables.

Secrets (JWT secret, Sarvam key, Flagsmith key, NudgeBee credentials) are only
ever read on the backend. Nothing here is shipped to the frontend.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("festiveplate.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./festiveplate.db"

    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 240

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    upload_dir: str = "./uploads"
    max_image_bytes: int = 5 * 1024 * 1024
    max_audio_bytes: int = 10 * 1024 * 1024

    # Rate limiting (requests per window per client IP)
    rate_limit_auth_per_minute: int = 20
    rate_limit_ai_per_minute: int = 30
    rate_limit_default_per_minute: int = 300

    # Sarvam AI
    sarvam_api_key: Optional[str] = None
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saarika:v2.5"
    sarvam_stt_translate_model: str = "saaras:v2.5"
    sarvam_translate_model: str = "mayura:v1"
    sarvam_chat_model: str = "sarvam-m"
    sarvam_timeout_seconds: float = 30.0

    # Flagsmith
    flagsmith_environment_key: Optional[str] = None
    flagsmith_api_url: str = "https://edge.api.flagsmith.com/api/v1/"
    flagsmith_cache_seconds: int = 60

    # NudgeBee
    nudgebee_enabled: bool = False
    nudgebee_webhook_url: Optional[str] = None
    nudgebee_api_key: Optional[str] = None
    metrics_token: Optional[str] = None

    # Matching / safety tuning
    emergency_window_minutes: int = 120
    volunteer_speed_kmph: float = 18.0

    @field_validator("database_url")
    @classmethod
    def _normalise_pg(cls, v: str) -> str:
        # Accept postgres:// and postgresql:// and route them through psycopg 3.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def flagsmith_configured(self) -> bool:
        return bool(self.flagsmith_environment_key)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.jwt_secret:
        if s.is_production:
            raise RuntimeError("JWT_SECRET must be set in production")
        s.jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET not set: using an ephemeral development secret (tokens reset on restart)")
    return s
