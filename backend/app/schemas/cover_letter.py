from enum import StrEnum

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.schemas.cv_profile import CVProfile
from app.schemas.job import normalize_multiline, normalize_single_line
from app.schemas.job_matching import JobMatchTarget


class CoverLetterSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class CoverLetterLanguage(StrEnum):
    VIETNAMESE = "vi"
    ENGLISH = "en"


class CoverLetterTone(StrEnum):
    PROFESSIONAL = "professional"
    CONFIDENT = "confident"
    ENTHUSIASTIC = "enthusiastic"


class CoverLetterInput(CoverLetterSchema):
    user_request: str = Field(min_length=1, max_length=2000)
    cv_profile: CVProfile
    job: JobMatchTarget

    @field_validator("user_request")
    @classmethod
    def normalize_user_request(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("user_request must not be empty.")

        return normalized


class CoverLetterDraft(CoverLetterSchema):
    language: CoverLetterLanguage
    tone: CoverLetterTone

    subject: str = Field(min_length=1, max_length=300)
    salutation: str = Field(min_length=1, max_length=300)
    opening_paragraph: str = Field(min_length=1, max_length=2000)
    body_paragraphs: list[str] = Field(min_length=1, max_length=3)
    closing_paragraph: str = Field(min_length=1, max_length=2000)
    complimentary_close: str = Field(min_length=1, max_length=300)
    signature_name: str | None = Field(default=None, max_length=300)
    cv_evidence_used: list[str] = Field(default_factory=list, max_length=10)
    job_requirements_addressed: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator(
        "subject",
        "salutation",
        "complimentary_close",
    )
    @classmethod
    def normalize_short_text(cls, value: str) -> str:
        normalized = normalize_single_line(value)

        if not normalized:
            raise ValueError("Cover letter field must not be empty.")

        return normalized

    @field_validator(
        "opening_paragraph",
        "closing_paragraph",
    )
    @classmethod
    def normalize_paragraph(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("Cover letter paragraph must not be empty.")

        return normalized

    @field_validator(
        "body_paragraphs",
        "cv_evidence_used",
        "job_requirements_addressed",
    )
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = normalize_multiline(value)
            key = normalized.casefold()

            if not normalized or key in seen:
                continue

            seen.add(key)
            normalized_values.append(normalized)

        return normalized_values


class CoverLetterResult(CoverLetterDraft):
    full_text: str = Field(min_length=1, max_length=10_000)
    word_count: int = Field(ge=1, le=2000)
    is_personalized: bool = True