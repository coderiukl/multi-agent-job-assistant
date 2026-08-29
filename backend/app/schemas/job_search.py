from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.schemas.job import (
    EmploymentType,
    JobSchema,
    NormalizedJob,
    SeniorityLevel,
    WorkMode,
    normalize_single_line,
)


class JobSearchSort(StrEnum):
    RELEVANCE = "relevance"
    NEWEST = "newest"


class JobSearchStrategy(StrEnum):
    POSTGRES = "postgres"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class JobSearchFilters(JobSchema):
    locations: list[str] = Field(default_factory=list, max_length=20)
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=10)
    work_modes: list[WorkMode] = Field(default_factory=list, max_length=10)
    seniority_levels: list[SeniorityLevel] = Field(default_factory=list, max_length=10)
    skills: list[str] = Field(default_factory=list, max_length=50)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    posted_after: datetime | None = None
    include_expired: bool = False

    @field_validator("locations", "skills")
    @classmethod
    def normalize_text_values(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = normalize_single_line(value)
            key = normalized.casefold()

            if not normalized or key in seen:
                continue

            seen.add(key)
            normalized_values.append(normalized)

        return normalized_values

    @field_validator(
        "employment_types",
        "work_modes",
        "seniority_levels",
    )
    @classmethod
    def deduplicate_enum_values(cls, values: list[StrEnum]) -> list[StrEnum]:
        return list(dict.fromkeys(values))

    @field_validator("salary_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("posted_after")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError(
                "posted_after must include timezone information."
            )

        return value

    @model_validator(mode="after")
    def validate_salary_filter(self) -> Self:
        if self.salary_min is not None and self.salary_currency is None:
            raise ValueError(
                "salary_currency is required when salary_min is provided."
            )

        return self


class JobSearchRequest(JobSchema):
    query: str = Field(min_length=1, max_length=2_000)
    filters: JobSearchFilters = Field(default_factory=JobSearchFilters)
    sort: JobSearchSort = JobSearchSort.RELEVANCE
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = normalize_single_line(value)

        if not normalized:
            raise ValueError("query must not be empty.")

        return normalized


class JobSearchPlan(JobSchema):
    original_query: str = Field(min_length=1, max_length=2_000)
    semantic_query: str = Field(min_length=1, max_length=2_000)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    filters: JobSearchFilters = Field(default_factory=JobSearchFilters)
    strategy: JobSearchStrategy = JobSearchStrategy.HYBRID
    sort: JobSearchSort = JobSearchSort.RELEVANCE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("original_query", "semantic_query")
    @classmethod
    def normalize_queries(cls, value: str) -> str:
        normalized = normalize_single_line(value)

        if not normalized:
            raise ValueError("search query must not be empty.")

        return normalized

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = normalize_single_line(value)
            key = normalized.casefold()

            if not normalized or key in seen:
                continue

            seen.add(key)
            normalized_values.append(normalized)

        return normalized_values


class JobSearchScore(JobSchema):
    semantic: float | None = Field(default=None, ge=0.0, le=1.0)
    keyword: float = Field(default=0.0, ge=0.0, le=1.0)
    filter_match: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness: float = Field(default=0.0, ge=0.0, le=1.0)
    final: float = Field(ge=0.0, le=1.0)


class JobSearchHit(JobSchema):
    job: NormalizedJob
    score: JobSearchScore
    matched_terms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @field_validator("matched_terms", "reasons")
    @classmethod
    def normalize_explanations(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = normalize_single_line(value)
            key = normalized.casefold()

            if not normalized or key in seen:
                continue

            seen.add(key)
            normalized_values.append(normalized)

        return normalized_values

class JobVectorSearchHit(JobSchema):
    job_id: str = Field(min_length=64, max_length=64, pattern=r"^{0-9a-z}{64}$")
    score: float = Field(ge=-1.0, le=1.0)

class JobSearchResult(JobSchema):
    query: str = Field(min_length=1, max_length=2_000)
    strategy: JobSearchStrategy
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    items: list[JobSearchHit] = Field(default_factory=list)

class JobSearchPage(JobSchema):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    jobs: list[NormalizedJob] = Field(default_factory=list)