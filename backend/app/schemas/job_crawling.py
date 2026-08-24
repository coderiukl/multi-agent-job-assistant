from pydantic import BaseModel, ConfigDict, Field


class JobCrawlingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobNormalizationFailure(JobCrawlingSchema):
    source_job_id: str
    error_type: str
    message: str = "Invalid or incomplete source record."


class JobCrawlResult(JobCrawlingSchema):
    source: str
    batch_id: str

    fetched_count: int = Field(ge=0)
    normalized_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

    inserted_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)

    raw_file_path: str

    current_cursor: str | None = None
    next_cursor: str | None = None

    failures: list[JobNormalizationFailure] = Field(
        default_factory=list,
    )