from enum import StrEnum

from app.graphs.conversation.state import ConversationState
from app.schemas.conversation import ConversationRoute, RequiredInput
from app.schemas.conversations_intent import ConversationIntent
from app.schemas.workflow import WorkflowStep, WorkflowType
from app.schemas.human_review import HumanReviewAction

INTENT_TO_STATE: dict[ConversationIntent, ConversationRoute] = {
    ConversationIntent.CV_ANALYSIS: ConversationRoute.CV_ANALYSIS,
    ConversationIntent.JOB_SEARCH: ConversationRoute.JOB_SEARCH,
    ConversationIntent.JOB_MATCHING: ConversationRoute.JOB_MATCHING,
    ConversationIntent.CAREER_ADVICE: ConversationRoute.CAREER_ADVICE,
    ConversationIntent.COVER_LETTER: ConversationRoute.COVER_LETTER,
    ConversationIntent.GENERAL_QUESTION: ConversationRoute.GENERAL_QUESTION,
    ConversationIntent.SMALL_TALK: ConversationRoute.SMALL_TALK,
    ConversationIntent.OUT_OF_SCOPE: ConversationRoute.OUT_OF_SCOPE,
    ConversationIntent.CLARIFICATION: ConversationRoute.CLARIFICATION,
}

class IntentGateRoute(StrEnum):
    CLARIFICATION = "clarification"
    PLAN_WORKFLOW = "plan_workflow"

class WorkflowRoute(StrEnum):
    JOB_SEARCH = "job_search"
    JOB_MATCHING = "job_matching"
    CAREER_ADVICE = "career_advice"
    CV_ANALYSIS = "cv_analysis"
    COVER_LETTER = "cover_letter"
    END = "end"

class HumanReviewRoute(StrEnum):
    WORKFLOW_COVER_LETTER = "workflow_cover_letter"
    SINGLE_COVER_LETTER = "single_cover_letter"
    REJECTED = "rejected"

def collect_missing_inputs(state: ConversationState) -> list[RequiredInput]:
    intent = state["intent"]
    missing_inputs : list[RequiredInput] = []

    if intent.requires_cv and not state.get("has_cv", False):
        missing_inputs.append(RequiredInput.CV)

    if intent.requires_jd and not state.get('has_jd', False):
        missing_inputs.append(RequiredInput.JOB_DESCRIPTION)

    return missing_inputs

def route_after_analysis(state: ConversationState) -> IntentGateRoute:
    intent = state["intent"]
    missing_inputs = collect_missing_inputs(state)

    if intent.needs_clarification or missing_inputs:
        return IntentGateRoute.CLARIFICATION

    return IntentGateRoute.PLAN_WORKFLOW

def route_after_intent(state: ConversationState) -> ConversationRoute:
    intent = state["intent"]
    
    return INTENT_TO_STATE[intent.primary_intent]

def route_workflow_start(state: ConversationState) -> str:
    workflow = state.get("workflow")

    if workflow is None or workflow.workflow_type == WorkflowType.SINGLE_AGENT:
        return route_after_intent(state).value

    workflow_node_by_step = {
        WorkflowStep.JOB_SEARCH: "workflow_job_search",
        WorkflowStep.JOB_MATCHING: "workflow_job_matching",
        WorkflowStep.CAREER_ADVICE: "workflow_career_advice",
        WorkflowStep.CV_ANALYSIS: "workflow_cv_analysis",
        WorkflowStep.COVER_LETTER: "workflow_cover_letter",
    }

    return workflow_node_by_step.get(
        workflow.current_step,
        "workflow_response",
    )

def route_next_workflow_step(state: ConversationState) -> WorkflowRoute:
    workflow = state.get("workflow")

    if workflow is None:
        return WorkflowRoute.END

    if workflow.current_step == WorkflowStep.JOB_SEARCH:
        return WorkflowRoute.JOB_SEARCH

    if workflow.current_step == WorkflowStep.JOB_MATCHING:
        return WorkflowRoute.JOB_MATCHING

    if workflow.current_step == WorkflowStep.CAREER_ADVICE:
        return WorkflowRoute.CAREER_ADVICE

    if workflow.current_step == WorkflowStep.CV_ANALYSIS:
        return WorkflowRoute.CV_ANALYSIS
    
    if workflow.current_step == WorkflowStep.COVER_LETTER:
        return WorkflowRoute.COVER_LETTER

    return WorkflowRoute.END

def route_after_human_review(state: ConversationState) -> HumanReviewRoute:
    decision = state.get("human_review_decision")

    if decision is None:
        return HumanReviewRoute.REJECTED

    if decision.action != HumanReviewAction.APPROVE:
        return HumanReviewRoute.REJECTED

    workflow = state.get("workflow")

    if workflow is None or workflow.workflow_type == WorkflowType.SINGLE_AGENT:
        return HumanReviewRoute.SINGLE_COVER_LETTER

    return HumanReviewRoute.WORKFLOW_COVER_LETTER
