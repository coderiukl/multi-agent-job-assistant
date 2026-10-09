from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.schemas.job import NormalizedJob
from app.schemas.job_matching import JobMatchingResult


class WorkflowType(StrEnum):
    SINGLE_AGENT = "single_agent"
    JOB_DISCOVERY = "job_discovery"
    JOB_RECOMMENDATION = "job_recommendation"
    FULL_CAREER = "full_career"


class WorkflowStep(StrEnum):
    RESOLVE_CONTEXT = "resolve_context"
    INTENT_ANALYSIS = "intent_analysis"
    CV_ANALYSIS = "cv_analysis"
    JOB_SEARCH = "job_search"
    JOB_MATCHING = "job_matching"
    CAREER_ADVICE = "career_advice"
    COVER_LETTER = "cover_letter"
    COMPLETED = "completed"


class WorkflowJobMatch(BaseModel):
    job: NormalizedJob
    match: JobMatchingResult


class WorkflowJobMatchStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowExecutionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class WorkflowJobMatchOutcome(BaseModel):
    job: NormalizedJob
    status: WorkflowJobMatchStatus
    match: JobMatchingResult | None = None
    error_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_outcome(self) -> "WorkflowJobMatchOutcome":
        if self.status == WorkflowJobMatchStatus.SUCCESS and self.match is None:
            raise ValueError("Successful matching outcomes require a match.")
        if self.status != WorkflowJobMatchStatus.SUCCESS and self.match is not None:
            raise ValueError("Failed or skipped outcomes cannot contain a match.")
        return self


class MatchingExecutionSummary(BaseModel):
    status: WorkflowExecutionStatus
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)

    @property
    def reliability_ratio(self) -> float:
        return self.succeeded / self.total if self.total else 0.0

    @model_validator(mode="after")
    def validate_counts(self) -> "MatchingExecutionSummary":
        if self.succeeded + self.failed + self.skipped != self.total:
            raise ValueError("Matching execution counts must equal total.")
        if self.status == WorkflowExecutionStatus.SUCCESS:
            if self.total == 0 or self.succeeded != self.total:
                raise ValueError("Success requires every job to succeed.")
        if self.status == WorkflowExecutionStatus.PARTIAL_SUCCESS:
            if not 0 < self.succeeded < self.total:
                raise ValueError("Partial success requires mixed outcomes.")
        if self.status == WorkflowExecutionStatus.FAILED and self.succeeded:
            raise ValueError("Failed execution cannot contain successes.")
        return self


class WorkflowPlan(BaseModel):
    workflow_type: WorkflowType = WorkflowType.SINGLE_AGENT
    steps: list[WorkflowStep] = Field(default_factory=list)
    current_step: WorkflowStep | None = None
    completed_steps: list[WorkflowStep] = Field(default_factory=list)
