from app.graphs.conversation.state import ConversationState
from app.schemas.conversation import RequiredInput
from app.schemas.conversations_intent import ConversationIntent, IntentAnalysisResult
from app.schemas.workflow import WorkflowPlan, WorkflowStep, WorkflowType

INTENT_STEP_ORDER = (
    (ConversationIntent.CV_ANALYSIS, WorkflowStep.CV_ANALYSIS),
    (ConversationIntent.JOB_SEARCH, WorkflowStep.JOB_SEARCH),
    (ConversationIntent.JOB_MATCHING, WorkflowStep.JOB_MATCHING),
    (ConversationIntent.CAREER_ADVICE, WorkflowStep.CAREER_ADVICE),
    (ConversationIntent.COVER_LETTER, WorkflowStep.COVER_LETTER),
)

STEP_REQUIREMENTS: dict[WorkflowStep, frozenset[str]] = {
    WorkflowStep.CV_ANALYSIS: frozenset({"cv"}),
    WorkflowStep.JOB_SEARCH: frozenset(),
    WorkflowStep.JOB_MATCHING: frozenset({"cv", "job_target"}),
    WorkflowStep.CAREER_ADVICE: frozenset(),
    WorkflowStep.COVER_LETTER: frozenset({"cv", "job_target"}),
}

STEP_OUTPUTS: dict[WorkflowStep, frozenset[str]] = {
    WorkflowStep.JOB_SEARCH: frozenset({"job_target"}),
}

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
            steps=steps,
            current_step=steps[0] if steps else None,
        )

    return WorkflowPlan(
        workflow_type=WorkflowType.FULL_CAREER,
        steps=steps,
        current_step=steps[0],
    )

def plan_workflow(state: ConversationState) -> WorkflowPlan:
    intent = state["intent"]
    return create_workflow_plan(intent)


def collect_missing_initial_inputs(
    workflow: WorkflowPlan,
    *,
    has_cv: bool,
    has_jd: bool,
) -> list[RequiredInput]:
    """Resolve only data that must exist before the first executable step."""

    available = set()
    if has_cv:
        available.add("cv")
    if has_jd:
        available.add("job_target")

    missing: list[RequiredInput] = []

    for step in workflow.steps:
        requirements = STEP_REQUIREMENTS.get(step, frozenset())

        if "cv" in requirements and "cv" not in available:
            if RequiredInput.CV not in missing:
                missing.append(RequiredInput.CV)

        if "job_target" in requirements and "job_target" not in available:
            if RequiredInput.JOB_DESCRIPTION not in missing:
                missing.append(RequiredInput.JOB_DESCRIPTION)

        available.update(STEP_OUTPUTS.get(step, frozenset()))

    return missing
