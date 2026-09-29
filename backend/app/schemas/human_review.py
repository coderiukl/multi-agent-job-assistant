from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

class HumanReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"

class HumanReviewRequest(BaseModel):
    review_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)

class HumanReviewDecision(BaseModel):
    action: HumanReviewAction
    feedback: str | None = None

class ResumeConversationRequest(BaseModel):
    thread_id: UUID
    decision: HumanReviewDecision