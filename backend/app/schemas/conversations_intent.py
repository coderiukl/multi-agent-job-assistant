from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

class ConversationIntent(StrEnum):
    CV_ANALYSIS = "cv_analysis"
    JOB_SEARCH = "job_search"
    JOB_MATCHING = "job_matching"
    CAREER_ADVICE = "career_advice"
    COVER_LETTER = "cover_letter"
    GENERAL_QUESTION = "general_question"
    CLARIFICATION = "clarification"

class IntentAnalysisInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="Message sent by the user.")
    has_cv: bool = Field(default=False, description="Whether the request contains a CV.")
    has_jd: bool = Field(default=False, description="Whether the request contains a job description.")

class IntentAnalysisResult(BaseModel):
    primary_intent: ConversationIntent
    secondary_intents: list[ConversationIntent] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score of the intent classification.",)
    requires_cv: bool = False
    requires_jd: bool = False

    needs_clarification: bool = False
    clarification_question: str | None = None

    @model_validator(mode="after")
    def validate_clarification(self) -> "IntentAnalysisResult":
        if self.needs_clarification and not self.clarification_question:
            raise ValueError(
                "clarification_question is required when "
                "needs_clarification is true."
            )

        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError(
                "clarification_question must be null when "
                "needs_clarification is false."
            )

        return self

