from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.cv_profile import CVProfile


class CVTaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CVTaskAcceptedData(BaseModel):
    task_id: UUID
    cv_id: str
    file_name: str
    file_size: int = Field(ge=1)
    content_type: str
    status: CVTaskStatus


class CVTaskStatusData(CVTaskAcceptedData):
    attempt_count: int = Field(ge=0)
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    profile: CVProfile | None = None
