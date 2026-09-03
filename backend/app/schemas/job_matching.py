from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.cv_profile import CVProfile
from app.schemas.job import (
    NormalizedJob,
    SeniorityLevel,
    WorkMode,
    normalize_multiline,
    normalize_single_line,
)

class JobMatchingSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True
    )

class MatchDimension(StrEnum):
    TECHNICAL_SKILLS = "technical_skills"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    PROJECTS = "projects"
    LANGUAGES_AND_CERTIFICATIONS = "language_and_certifications"

class MatchStatus(StrEnum):
    MATCHED = "matched"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"

class MatchRecommendation(StrEnum):
    STRONG_MATCH = "strong_match"
    GOOD_MATCH = "good_match"
    PARTIAL_MATCH = "partial_match"
    LOW_MATCH = "low_match"

class JobMatchTarget(JobMatchingSchema):
    job_id: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    title: str | None = Field(default=None, max_length=500)
    company: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list, max_length=100)
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    location: str | None = Field(default=None, max_length=500)
    work_mode: WorkMode = WorkMode.UNKNOWN

    @field_validator("title", "company", "location")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = normalize_single_line(value)
        return normalized or None

    @field_validator("description") 
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("description must not be empty.")

        return normalized

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, values: list[str]) -> list[str]:
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

    @classmethod
    def from_normalized_job(cls, job: NormalizedJob) -> Self:
        return cls(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            description=job.description,
            skills=job.skills,
            seniority_level=job.seniority_level,
            location=job.location,
            work_mode=job.work_mode,
        )

class JobMatchingInput(JobMatchingSchema):
    cv_profile: CVProfile
    job: JobMatchTarget

class JobMatchingBreakDown(JobMatchingSchema):
    technical_skills: float = Field(ge=0.0, le=100.0)
    experience: float = Field(ge=0.0, le=100.0)
    education: float = Field(ge=0.0, le=100.0)
    projects: float = Field(ge=0.0, le=100.0)
    language_and_certifications: float = Field(ge=0.0, le=100.0)

class MatchEvidence(JobMatchingSchema):
    dimension: MatchDimension
    requirement: str = Field(min_length=1, max_length=1000)
    cv_evidence: list[str] = Field(default_factory=list, max_length=10)
    status: MatchStatus
    explanation: str = Field(min_length=1, max_length=2000)

    @field_validator("requirement", "explanation")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = normalize_single_line(value)

        if not normalized:
            raise ValueError("Value must not be empty.")

        return normalized

    @field_validator("cv_evidence")
    @classmethod
    def normalize_cv_evidence(cls, values: list[str]) -> list[str]:
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

class JobMatchingAssessment(JobMatchingSchema):
    breakdown: JobMatchingBreakDown
    strengths: list[str] = Field(default_factory=list, max_length=20)
    gaps: list[str] = Field(default_factory=list, max_length=20)
    evidence: list[MatchEvidence] = Field(default_factory=list, max_length=30)
    summary: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("strengths", "gaps")
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

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("summary must not be empty.")

        return normalized

class JobMatchingResult(JobMatchingAssessment):
    job_id: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    overall_score: float = Field(ge=0.0, le=100.0)
    recommendation: MatchRecommendation
    