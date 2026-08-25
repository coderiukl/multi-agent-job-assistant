import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.job import NormalizedJob


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobStorageSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobWriteStatus(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class JobVersionRecord(JobStorageSchema):
    operation: JobWriteStatus
    stored_at: datetime = Field(default_factory=utc_now)
    job: NormalizedJob

    @field_validator("stored_at", mode="before")
    @classmethod
    def normalize_legacy_stored_at(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        legacy_match = re.fullmatch(
            r"(?P<date>\d{4}-\d{2}-\d{2})T0\.(?P<microsecond>\d{1,6})Z",
            value,
        )

        if legacy_match is None:
            return value

        microsecond = legacy_match.group("microsecond").ljust(6, "0")

        return f"{legacy_match.group('date')}T00:00:00.{microsecond}Z"


class JobUpsertResult(JobStorageSchema):
    job_id: str
    status: JobWriteStatus
    previous_content_hash: str | None = None
    current_content_hash: str


class JobUpsertSummary(JobStorageSchema):
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    results: list[JobUpsertResult] = Field(default_factory=list)
