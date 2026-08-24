from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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