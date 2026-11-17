from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.schemas.conversation_search_context import (
    ConversationSearchContext,
    format_search_context,
)

MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 6_000
# Downstream agent inputs (user_request / query) accept at most 2,000 chars.
MAX_CONTEXTUAL_MESSAGE_CHARS = 2_000
_TRUNCATION_MARK = "…"


def get_previous_message(
    messages: Sequence[BaseMessage],
    *,
    current_message: str,
) -> list[BaseMessage]:
    previous_messages = list(messages)

    if (
        previous_messages
        and isinstance(previous_messages[-1], HumanMessage)
        and _message_text(previous_messages[-1]) == current_message
    ):
        previous_messages.pop()

    return previous_messages


def format_conversation_history(
    messages: Sequence[BaseMessage],
    *,
    current_message: str,
) -> str:
    previous_messages = get_previous_message(
        messages=messages, current_message=current_message
    )

    recent_messages = previous_messages[-MAX_HISTORY_MESSAGES:]
    formatted_messages: list[str] = []

    for message in recent_messages:
        content = _message_text(message)

        if not content:
            continue

        if isinstance(message, HumanMessage):
            role = "User"
        elif isinstance(message, AIMessage):
            role = "Assistant"
        else:
            continue

        formatted_messages.append(f"{role}: {content}")

    if not formatted_messages:
        return "No previous conversation."

    history = "\n".join(formatted_messages)

    return history[-MAX_HISTORY_CHARS:]


def build_contextual_user_message(
    *,
    current_message: str,
    search_context: ConversationSearchContext | dict | None = None,
) -> str:
    context = ConversationSearchContext.model_validate(search_context or {})

    if context.is_empty:
        return current_message

    prefix = (
        "Saved job search constraints:\n"
        f"{format_search_context(context)}\n\n"
        "Current user request:\n"
    )
    # Truncate the user's message, never the saved constraints (BUG-025):
    # slicing the whole string from the end silently dropped them.
    prefix = prefix[: MAX_CONTEXTUAL_MESSAGE_CHARS // 2]
    budget = MAX_CONTEXTUAL_MESSAGE_CHARS - len(prefix)
    if len(current_message) > budget:
        current_message = (
            current_message[: budget - len(_TRUNCATION_MARK)].rstrip()
            + _TRUNCATION_MARK
        )

    return prefix + current_message


def _message_text(message: BaseMessage) -> str:
    content = message.content

    if isinstance(content, str):
        return content.strip()

    return str(content).strip()
