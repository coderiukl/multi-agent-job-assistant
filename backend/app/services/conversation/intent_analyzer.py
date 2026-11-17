import logging
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AppException,
    ExternalServiceException,
    StructuredOutputException,
)
from app.prompts.intent_analysis import INTENT_ANALYSIS_PROMPT
from app.schemas.conversation_search_context import format_search_context
from app.schemas.conversations_intent import IntentAnalysisInput, IntentAnalysisResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


class ConversationIntentAnalyzer:
    """LLM intent router.

    Every chat turn goes through this component, so it follows the same
    contract as the business agents: the configured structured-output method,
    one retry for malformed output (502 INVALID_STRUCTURED_OUTPUT after that)
    and provider failures mapped to 502 EXTERNAL_SERVICE_ERROR (BUG-014).
    """

    def __init__(self, llm: BaseChatModel, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._structured_llm = llm.with_structured_output(
            IntentAnalysisResult,
            method=settings.llm_structured_output_method,
        )

    async def analyze(self, input_data: IntentAnalysisInput) -> IntentAnalysisResult:
        prompt_value = INTENT_ANALYSIS_PROMPT.invoke(
            {
                "message": input_data.message,
                "conversation_history": input_data.conversation_history,
                "has_cv": input_data.has_cv,
                "has_jd": input_data.has_jd,
                "search_context": format_search_context(
                    input_data.search_context
                ),
            }
        )

        for attempt in range(MAX_ATTEMPTS):
            try:
                result: Any = await self._structured_llm.ainvoke(prompt_value)
                return (
                    result
                    if isinstance(result, IntentAnalysisResult)
                    else IntentAnalysisResult.model_validate(result)
                )
            except (
                OutputParserException,
                ValidationError,
                TypeError,
                ValueError,
            ) as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    logger.warning(
                        "Invalid structured intent output; retrying",
                        extra={"error_type": type(exc).__name__},
                    )
                    continue

                logger.error(
                    "Intent analyzer returned invalid output",
                    extra={"error_type": type(exc).__name__},
                )
                raise StructuredOutputException(
                    message="The request intent could not be analyzed.",
                    details={"reason": type(exc).__name__},
                ) from exc
            except AppException:
                raise
            except Exception as exc:
                logger.error(
                    "Intent analysis LLM request failed",
                    extra={"error_type": type(exc).__name__},
                )
                raise ExternalServiceException(
                    service="llm",
                    message="The intent analysis service is unavailable.",
                ) from exc

        raise StructuredOutputException(  # pragma: no cover - loop always returns
            message="The request intent could not be analyzed."
        )
