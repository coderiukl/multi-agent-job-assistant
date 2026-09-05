from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.conversations_intent import IntentAnalysisResult
from app.schemas.job_search import JobSearchResult
from app.schemas.job_matching import JobMatchingResult
from app.schemas.cv_analysis import CVAnalysisResult

class ConversationRoute(StrEnum):
    CLARIFICATION = "clarification"
    SMALL_TALK = "small_talk"
    GENERAL_QUESTION = "general_question"
    OUT_OF_SCOPE = "out_of_scope"

    CV_ANALYSIS = "cv_analysis"
    JOB_SEARCH = "job_search"
    JOB_MATCHING = "job_matching"
    CAREER_ADVICE = "career_advice"
    COVER_LETTER = "cover_letter"

class ConversationStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    ROUTED = "routed"

class RequiredInput(StrEnum):
    CV = "cv"
    JOB_DESCRIPTION = "job_description"

class ConversationResponseData(BaseModel):
    assistant_message: str = Field(min_length=1)
    status: ConversationStatus
    route: ConversationRoute

    intent: IntentAnalysisResult

    cv_id: str | None = None
    missing_inputs: list[RequiredInput] = Field(default_factory=list)

    job_search_result: JobSearchResult | None = None
    job_matching_result: JobMatchingResult | None = None
    cv_analysis_result: CVAnalysisResult | None = None
    
    