from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.job import SeniorityLevel, WorkMode, normalize_single_line

SearchContextField = Literal["role", "location", "seniority", "work_mode"]


class ConversationSearchContext(BaseModel):
    role: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    seniority: SeniorityLevel | None = None
    work_mode: WorkMode | None = None

    @field_validator("role", "location")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = normalize_single_line(value)
        return normalized or None

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.role, self.location, self.seniority, self.work_mode)
        )


class SearchContextPatch(BaseModel):
    role: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    seniority: SeniorityLevel | None = None
    work_mode: WorkMode | None = None
    clear_fields: list[SearchContextField] = Field(default_factory=list)

    @field_validator("role", "location")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = normalize_single_line(value)
        return normalized or None

    @field_validator("clear_fields")
    @classmethod
    def deduplicate_clear_fields(
        cls, values: list[SearchContextField]
    ) -> list[SearchContextField]:
        return list(dict.fromkeys(values))


def apply_search_context_patch(
    current: ConversationSearchContext | dict | None,
    patch: SearchContextPatch,
) -> ConversationSearchContext:
    context = ConversationSearchContext.model_validate(current or {})
    values = context.model_dump()

    for field_name in patch.clear_fields:
        values[field_name] = None

    for field_name in ("role", "location", "seniority", "work_mode"):
        value = getattr(patch, field_name)
        if value is not None:
            values[field_name] = value

    return ConversationSearchContext.model_validate(values)


def format_search_context(context: ConversationSearchContext | None) -> str:
    if context is None or context.is_empty:
        return "No saved search constraints."

    values = context.model_dump(mode="json", exclude_none=True)
    return "\n".join(f"- {key}: {value}" for key, value in values.items())
