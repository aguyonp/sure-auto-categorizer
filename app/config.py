"""Application configuration, sourced exclusively from environment variables."""

from __future__ import annotations

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Loaded from env vars (and a local .env if present)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Sure Finance API (required) ---
    sure_url: HttpUrl = Field(..., description="Base URL of the Sure instance, e.g. https://sure.example.com")
    sure_api_key: str = Field(..., description="Sure API key with read_write scope")

    # --- LLM / Groq (required) ---
    groq_api_key: str = Field(..., description="Groq API key")
    groq_model: str = Field("llama-3.3-70b-versatile", description="Groq chat model id")
    groq_url: str = Field("https://api.groq.com/openai/v1", description="OpenAI-compatible base URL")

    # --- Behaviour (optional) ---
    sure_account_id: str | None = Field(
        None, description="Restrict to a single account id. If unset, all accounts are processed."
    )
    batch_size: int = Field(25, ge=1, le=100, description="Transactions sent to the LLM per request")
    run_interval_seconds: int = Field(
        3600, ge=0, description="Seconds between runs. 0 means run once and exit."
    )
    dry_run: bool = Field(False, description="Log proposed categories without writing them back")
    request_timeout: float = Field(60.0, gt=0, description="HTTP timeout in seconds")
    log_level: str = Field("INFO", description="Loguru log level")

    @property
    def sure_base(self) -> str:
        return str(self.sure_url).rstrip("/")
