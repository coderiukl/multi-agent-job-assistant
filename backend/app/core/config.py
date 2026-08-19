from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


class Settings(BaseSettings):
    app_name: str = "Multi-Agent Job Assistant"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    api_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"
    log_format: Literal["console", "json"] = "console"

    backend_cors_origins: list[str] = Field(
        default_factory=lambda: DEFAULT_CORS_ORIGINS.copy(),
    )
    backend_cors_allow_credentials: bool = True

    llm_provider: Literal["openai", "openrouter"] = "openai"

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = Field(default=None, repr=False)

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = Field(default=None, repr=False)
    langsmith_project: str = "multi-agent-job-assistant"

    qdrant_url: str | None = None
    qdrant_api_key: str | None = Field(default=None, repr=False)

    max_upload_size_mb: int = 10
    allowed_cv_content_types: tuple[str, ...] = ("application/pdf",)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("backend_cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        normalized_origins: list[str] = []

        for origin in origins:
            normalized_origin = origin.rstrip("/")
            parsed_origin = urlsplit(normalized_origin)

            if (
                normalized_origin == "*"
                or parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError(f"Invalid CORS origin: {origin}")

            normalized_origins.append(normalized_origin)

        return normalized_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
