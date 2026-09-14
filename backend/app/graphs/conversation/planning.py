from app.graphs.conversation.state import ConversationState
from app.schemas.conversations_intent import ConversationIntent, IntentAnalysisResult
from app.schemas.workflow import WorkflowPlan, WorkflowStep, WorkflowType

INTENT_STEP_ORDER = (
    (ConversationIntent.CV_ANALYSIS, WorkflowStep.CV_ANALYSIS),
    (ConversationIntent.JOB_SEARCH, WorkflowStep.JOB_SEARCH),
    (ConversationIntent.JOB_MATCHING, WorkflowStep.JOB_MATCHING),
    (ConversationIntent.CAREER_ADVICE, WorkflowStep.CAREER_ADVICE),
    (ConversationIntent.COVER_LETTER, WorkflowStep.COVER_LETTER),
)

def _collect_requested_intents(intent: IntentAnalysisResult) -> set[ConversationIntent]:
    return {
        intent.primary_intent,
        *intent.secondary_intents,
    }

def _build_workflow_steps(intents: set[ConversationIntent]) -> list[WorkflowStep]:
    return [
        workflow_step
        for conversation_intent, workflow_step in INTENT_STEP_ORDER
        if conversation_intent in intents
    ]

def create_workflow_plan(intent: IntentAnalysisResult) -> WorkflowPlan:
    intents = _collect_requested_intents(intent)
    steps = _build_workflow_steps(intents)

    if steps == [WorkflowStep.JOB_SEARCH]:
        return WorkflowPlan(
            workflow_type=WorkflowType.JOB_DISCOVERY,
            steps=steps,
            current_step=steps[0],
        )

    if steps == [WorkflowStep.JOB_SEARCH, WorkflowStep.JOB_MATCHING]:
        return WorkflowPlan(
            workflow_type=WorkflowType.JOB_RECOMMENDATION,
            steps=steps,
            current_step=steps[0],
        )

    if len(steps) <= 1:
        return WorkflowPlan(
            workflow_type=WorkflowType.SINGLE_AGENT,
            steps=[],
            current_step=None,
        )

    return WorkflowPlan(
        workflow_type=WorkflowType.FULL_CAREER,
        steps=steps,
        current_step=steps[0],
    )

def plan_workflow(state: ConversationState) -> WorkflowPlan:
    intent = state["intent"]
    return create_workflow_plan(intent)
