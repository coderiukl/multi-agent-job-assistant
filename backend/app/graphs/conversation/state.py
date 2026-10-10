from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.schemas.career_advice import CareerAdviceResult
from app.schemas.conversation import (
    ConversationRoute,
    ConversationStatus,
    RequiredInput,
)
from app.schemas.conversation_search_context import ConversationSearchContext
from app.schemas.conversations_intent import IntentAnalysisResult
from app.schemas.cover_letter import CoverLetterResult
from app.schemas.cv_analysis import CVAnalysisResult
from app.schemas.cv_profile import CVProfile
from app.schemas.human_review import HumanReviewDecision, HumanReviewRequest
from app.schemas.job_matching import JobMatchingResult, JobMatchTarget
from app.schemas.job_search import JobSearchResult
from app.schemas.workflow import (
    MatchingExecutionSummary,
    WorkflowJobMatch,
    WorkflowJobMatchOutcome,
    WorkflowPlan,
)


class ConversationState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]

    # Dữ liệu từ request
    message: str
    turn_id: str
    contextual_message: str
    conversation_history: str

    cv_id: str | None
    cv_name: str | None
    job_description: str | None

    # Context được backend xác thực
    cv_profile: CVProfile | None
    has_cv: bool
    has_jd: bool
    search_context: ConversationSearchContext

    # Kết quả Intent Analysis
    intent: IntentAnalysisResult

    # Workflow
    workflow: WorkflowPlan | None

    # Kết quả điều phối
    route: ConversationRoute
    status: ConversationStatus
    missing_inputs: list[RequiredInput]

    # Kết quả của các business agent
    cv_analysis_result: CVAnalysisResult | None
    career_advice_result: CareerAdviceResult | None
    job_search_result: JobSearchResult | None
    job_matching_result: JobMatchingResult | None
    workflow_job_matches: list[WorkflowJobMatch]
    workflow_job_match_outcomes: list[WorkflowJobMatchOutcome]
    matching_execution: MatchingExecutionSummary | None
    cover_letter_result: CoverLetterResult | None

    # Nội dung trả về người dùng
    assistant_message: str

    # Human-in-the-loop
    human_review_request: HumanReviewRequest | None
    human_review_decision: HumanReviewDecision | None
    cover_letter_job: JobMatchTarget | None
    cover_letter_instructions: str | None
    cover_letter_draft_review: HumanReviewRequest | None
    cover_letter_draft_decision: HumanReviewDecision | None
