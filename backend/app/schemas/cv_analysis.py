from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.cv_profile import CVProfile
from app.schemas.job import normalize_multiline, normalize_single_line


class CVAnalysisSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class CVAnalysisDimension(StrEnum):
    COMPLETENESS = "completeness"
    PROFESSIONAL_SUMMARY = "professional_summary"
    SKILLS = "skills"
    WORK_EXPERIENCE = "work_experience"
    PROJECTS = "projects"
    EDUCATION_AND_CREDENTIALS = "education_and_credentials"


class CVSection(StrEnum):
    PERSONAL_INFORMATION = "personal_information"
    PROFESSIONAL_SUMMARY = "professional_summary"
    SKILLS = "skills"
    WORK_EXPERIENCE = "work_experience"
    EDUCATION = "education"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"
    GENERAL = "general"


class ImprovementPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CVQualityLevel(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs_improvement"
    WEAK = "weak"


class CVAnalysisInput(CVAnalysisSchema):
    cv_profile: CVProfile
    user_request: str = Field(min_length=1, max_length=2000)

    @field_validator("user_request")
    @classmethod
    def normalize_user_request(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("user_request must not be empty.")

        return normalized


class CVAnalysisBreakdown(CVAnalysisSchema):
    completeness: float = Field(ge=0.0, le=100.0)
    professional_summary: float = Field(ge=0.0, le=100.0)
    skills: float = Field(ge=0.0, le=100.0)
    work_experience: float = Field(ge=0.0, le=100.0)
    projects: float = Field(ge=0.0, le=100.0)
    education_and_credentials: float = Field(ge=0.0, le=100.0)


class CVAnalysisFinding(CVAnalysisSchema):
    dimension: CVAnalysisDimension
    section: CVSection
    finding: str = Field(min_length=1, max_length=1000)
    cv_evidence: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("finding")
    @classmethod
    def normalize_finding(cls, value: str) -> str:
        normalized = normalize_single_line(value)

        if not normalized:
            raise ValueError("finding must not be empty.")

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


class CVImprovementSuggestion(CVAnalysisSchema):
    section: CVSection
    priority: ImprovementPriority
    issue: str = Field(min_length=1, max_length=1000)
    suggestion: str = Field(min_length=1, max_length=2000)
    example: str | None = Field(default=None, max_length=2000)

    @field_validator("issue", "suggestion")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("Value must not be empty.")

        return normalized

    @field_validator("example")
    @classmethod
    def normalize_optional_example(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = normalize_multiline(value)
        return normalized or None


class CVAnalysisAssessment(CVAnalysisSchema):
    breakdown: CVAnalysisBreakdown
    strengths: list[CVAnalysisFinding] = Field(default_factory=list, max_length=15)
    weaknesses: list[CVAnalysisFinding] = Field(default_factory=list, max_length=15)
    improvements: list[CVImprovementSuggestion] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("summary must not be empty.")

        return normalized


class CVAnalysisResult(CVAnalysisAssessment):
    overall_score: float = Field(ge=0.0, le=100.0)
    quality_level: CVQualityLevel