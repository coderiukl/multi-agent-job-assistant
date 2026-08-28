from pydantic import Field

from app.schemas.job import JobSchema


class JobIndexingSummary(JobSchema):
    received: int = Field(ge=0)
    indexed: int = Field(ge=0)
    batches: int = Field(ge=0)


class JobIndexSyncSummary(JobSchema):
    source: str | None = None
    scanned: int = Field(ge=0)
    indexed: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    batches: int = Field(ge=0)
