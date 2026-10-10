from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class HumanReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"

class HumanReviewRequest(BaseModel):
    review_id: str = Field(pattern=r"^review_[0-9a-f]{16}$")
    review_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)

class HumanReviewDecision(BaseModel):
    review_id: str = Field(pattern=r"^review_[0-9a-f]{16}$")
    action: HumanReviewAction
    feedback: str | None = None
    selected_job_id: str | None = Field(default=None, max_length=100)
    input_overrides: dict[str, str] = Field(default_factory=dict)
    edited_draft: str | None = Field(default=None, max_length=10_000)

    @field_validator("input_overrides")
    @classmethod
    def validate_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"job_title", "company", "job_description", "instructions"}
        if set(value) - allowed:
            raise ValueError("Unsupported cover-letter input override.")
        return {
            key: normalized
            for key, item in value.items()
            if (normalized := item.strip())
        }

class ResumeConversationRequest(BaseModel):
    thread_id: UUID
    turn_id: UUID = Field(default_factory=uuid4)
    decision: HumanReviewDecision
