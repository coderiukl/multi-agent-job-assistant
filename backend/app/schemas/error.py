from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorPayload
    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
