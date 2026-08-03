from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multi-Agent Job Assistant"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")

    api_v1_prefix: str = "/api/v1"

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"  

    llm_provider: Literal["openai", "9router"] = "openai"
    llm_model: str = "cx/gpt-5.5"
    llm_temperature: int | None = None
    llm_max_tokens: int | None = None

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = Field(default=None, repr=False)

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = Field(default=None, repr=False)
    langsmith_project: str = "multi-agent-job-assistant"

    qdrant_url: str | None = None
    qdrant_api_key: str | None = Field(default=None, repr=False)

    max_upload_size_mb: int = 10
    allowed_cv_content_types: tuple[str, ...] = ("application/pdf",)

    max_pdf_pages: int = 5
    pdf_render_dpi: int = 200
    ocr_enabled: bool = True
    ocr_languages: tuple[str, ...] = ("vi", "en")
    allowed_cv_extensions: tuple[str, ...] = (".pdf",)

    min_text_length_for_digital_page: int = 80
    min_text_blocks_for_digital_page: int = 3
    scan_image_coverage_threshold: float = 0.70
    hybrid_image_coverage_threshold: float = 0.10
    min_ocr_region_area_ratio: float = 0.02
    dedup_bbox_iou_threshold: float = 0.60
    dedup_text_similarity_threshold: float = 0.85
    accepted_confidence_threshold: float = 0.90
    warning_confidence_threshold: float = 0.70
    
    cv_pipeline_version: str = "cv-pipeline-v1"
    cv_prompt_version: str = "cv-profile-parser-v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    backend_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    storage_dir: str = "storage"
    upload_dir: str = "storage/uploads"

@lru_cache
def get_settings() -> Settings:
    return Settings()