from app.graphs.conversation.state import ConversationState
from app.schemas.conversation import ConversationRoute, RequiredInput
from app.schemas.conversations_intent import ConversationIntent

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

def collect_missing_inputs(state: ConversationState) -> list[RequiredInput]:
    intent = state["intent"]
    missing_inputs : list[RequiredInput] = []

    if intent.requires_cv and not state.get("has_cv", False):
        missing_inputs.append(RequiredInput.CV)

    if intent.requires_jd and not state.get('has_jd', False):
        missing_inputs.append(RequiredInput.JOB_DESCRIPTION)

    return missing_inputs

def route_after_intent(state: ConversationState) -> ConversationRoute:
    intent = state["intent"]
    missing_inputs = collect_missing_inputs(state)

    if intent.needs_clarification or missing_inputs:
        return ConversationRoute.CLARIFICATION

    return INTENT_TO_STATE[intent.primary_intent]