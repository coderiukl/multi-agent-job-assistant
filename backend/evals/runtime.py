import os
import subprocess
from functools import lru_cache

from app.api.dependencies import (
    get_chat_model,
    get_job_matching_service,
    get_job_search_agent,
    get_job_search_service,
)
from app.core.config import get_settings
from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer

def config_langsmith() -> None:
    settings = get_settings()

    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)

    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGSMITH_PROJECT", f"{settings.langsmith_project}-eval")

@lru_cache
def get_intent_analyzer() -> ConversationIntentAnalyzer:
    return ConversationIntentAnalyzer(llm=get_chat_model())

def get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            check=True,
            text=True
        )

        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"

def eval_metadata() -> dict[str, str]:
    settings = get_settings()

    return {
        "git_sha": get_git_sha(),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "structured_output_method": settings.llm_structured_output_method
    }

__all__ = [
    "config_langsmith",
    "eval_metadata",
    "get_intent_analyzer",
    "get_job_matching_service",
    "get_job_search_agent",
    "get_job_search_service",
]
