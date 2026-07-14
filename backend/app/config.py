"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider
    llm_provider: str = "mock"  # mock | bedrock | anthropic

    # Bedrock
    aws_region: str = "us-west-2"
    bedrock_model_id: str = "us.anthropic.claude-opus-4-8"
    bedrock_model_id_moderator: str = ""
    # Fallback model used if the primary Bedrock model errors (throttling,
    # access, deprecated param, etc.). Empty = no fallback.
    bedrock_model_id_fallback: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Anthropic direct
    anthropic_api_key: str = ""
    anthropic_model_id: str = "claude-sonnet-4-20250514"

    # Data providers
    finnhub_api_key: str = ""
    alphavantage_api_key: str = ""
    newsapi_key: str = ""
    gnews_api_key: str = ""  # gnews.io — company news by name, any market incl. India

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regex to allow a family of frontend origins (e.g. your CDN domain).
    # Empty = default to allowing *.cloudfront.net.
    cors_origin_regex: str = ""

    debate_rounds: int = 2

    # ---- Optional OIDC / JWT auth ----
    # When true, every /api and /ws request must carry a valid OIDC id_token
    # (Authorization: Bearer <id_token>). Off by default so local/mock dev needs
    # no auth. Works with any OIDC provider (Cognito, Auth0, Okta, Google, ...).
    require_auth: bool = False
    oidc_issuer: str = ""       # e.g. https://your-tenant.auth0.com/
    oidc_jwks_url: str = ""     # e.g. https://your-tenant.auth0.com/.well-known/jwks.json
    # Optional: comma-separated audiences (client_ids) to accept. Empty = skip
    # audience check (still verifies signature + issuer + expiry).
    oidc_audience: str = ""

    @property
    def oidc_audience_list(self) -> list[str]:
        return [a.strip() for a in self.oidc_audience.split(",") if a.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
