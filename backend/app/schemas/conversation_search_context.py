import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.job import SeniorityLevel, WorkMode, normalize_single_line

SearchContextField = Literal["role", "location", "seniority", "work_mode"]
_LOCATION_SEPARATOR = re.compile(
    r"\s*(?:[,;|]|\b(?:và|hoặc|and|or)\b)\s*",
    flags=re.IGNORECASE,
)


class ConversationSearchContext(BaseModel):
    role: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    seniority: SeniorityLevel | None = None
    work_mode: WorkMode | None = None

    @field_validator("role", "location", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        value = _coerce_text_value(value)
        if value is None:
            return None

        normalized = normalize_single_line(value)
        return normalized or None

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, value: Any) -> SeniorityLevel | None:
        return _coerce_seniority(value)

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: Any) -> WorkMode | None:
        return _coerce_work_mode(value)

    @property
    def is_empty(self) -> bool:
        return not any((self.role, self.location, self.seniority, self.work_mode))


class SearchContextPatch(BaseModel):
    role: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    seniority: SeniorityLevel | None = None
    work_mode: WorkMode | None = None
    clear_fields: list[SearchContextField] = Field(default_factory=list)

    @field_validator("role", "location", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        value = _coerce_text_value(value)
        if value is None:
            return None

        normalized = normalize_single_line(value)
        return normalized or None

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, value: Any) -> SeniorityLevel | None:
        return _coerce_seniority(value)

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: Any) -> WorkMode | None:
        return _coerce_work_mode(value)

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


def split_search_locations(value: str | None) -> list[str]:
    if not value:
        return []

    locations: list[str] = []
    seen: set[str] = set()

    for item in _LOCATION_SEPARATOR.split(value):
        normalized = normalize_single_line(item)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue

        seen.add(key)
        locations.append(normalized)

    return locations


def _coerce_text_value(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple, set)):
        normalized_items = [
            normalize_single_line(item)
            for item in value
            if isinstance(item, str) and normalize_single_line(item)
        ]
        return ", ".join(dict.fromkeys(normalized_items)) or None

    return str(value)


_SENIORITY_ALIASES: dict[str, SeniorityLevel] = {
    "intern": SeniorityLevel.INTERN,
    "internship": SeniorityLevel.INTERN,
    "thuc tap": SeniorityLevel.INTERN,
    "thuc tap sinh": SeniorityLevel.INTERN,
    "fresher": SeniorityLevel.FRESHER,
    "entry level": SeniorityLevel.FRESHER,
    "graduate": SeniorityLevel.FRESHER,
    "new grad": SeniorityLevel.FRESHER,
    "new graduate": SeniorityLevel.FRESHER,
    "moi ra truong": SeniorityLevel.FRESHER,
    "sinh vien moi ra truong": SeniorityLevel.FRESHER,
    "junior": SeniorityLevel.JUNIOR,
    "middle": SeniorityLevel.MIDDLE,
    "mid": SeniorityLevel.MIDDLE,
    "mid level": SeniorityLevel.MIDDLE,
    "senior": SeniorityLevel.SENIOR,
    "lead": SeniorityLevel.LEAD,
    "leader": SeniorityLevel.LEAD,
    "team lead": SeniorityLevel.LEAD,
    "truong nhom": SeniorityLevel.LEAD,
    "manager": SeniorityLevel.MANAGER,
    "quan ly": SeniorityLevel.MANAGER,
    "director": SeniorityLevel.DIRECTOR,
    "giam doc": SeniorityLevel.DIRECTOR,
    "unknown": SeniorityLevel.UNKNOWN,
    "khong ro": SeniorityLevel.UNKNOWN,
}

_WORK_MODE_ALIASES: dict[str, WorkMode] = {
    "onsite": WorkMode.ONSITE,
    "on site": WorkMode.ONSITE,
    "office": WorkMode.ONSITE,
    "in office": WorkMode.ONSITE,
    "tai van phong": WorkMode.ONSITE,
    "remote": WorkMode.REMOTE,
    "work from home": WorkMode.REMOTE,
    "working from home": WorkMode.REMOTE,
    "wfh": WorkMode.REMOTE,
    "lam tu xa": WorkMode.REMOTE,
    "hybrid": WorkMode.HYBRID,
    "flexible": WorkMode.HYBRID,
    "ket hop": WorkMode.HYBRID,
    "unknown": WorkMode.UNKNOWN,
    "khong ro": WorkMode.UNKNOWN,
}


def _coerce_seniority(value: Any) -> SeniorityLevel | None:
    if value is None or isinstance(value, SeniorityLevel):
        return value

    candidates = value if isinstance(value, (list, tuple, set)) else [value]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue

        key = _normalize_enum_label(candidate)
        if not key:
            continue

        mapped = _SENIORITY_ALIASES.get(key)
        if mapped is not None:
            return mapped

    return SeniorityLevel.UNKNOWN


def _coerce_work_mode(value: Any) -> WorkMode | None:
    if value is None or isinstance(value, WorkMode):
        return value

    candidates = value if isinstance(value, (list, tuple, set)) else [value]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue

        key = _normalize_enum_label(candidate)
        if not key:
            continue

        mapped = _WORK_MODE_ALIASES.get(key)
        if mapped is not None:
            return mapped

    return WorkMode.UNKNOWN


def _normalize_enum_label(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[\s_-]+", " ", ascii_value.casefold()).strip()
