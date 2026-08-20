import logging
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import (
    AppException,
    ExternalServiceException,
    FileValidationException,
    StructuredOutputException,
)
from app.prompts.cv_parser import CV_PARSER_PROMPT
from app.schemas.cv_profile import CVProfile

logger = logging.getLogger(__name__)

class CVParserAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings) -> None:
        self._max_text_chars = settings.max_cv_text_chars
        self._structured_llm = llm.with_structured_output(
            CVProfile,
            method=settings.llm_structured_output_method
        )

    async def parse(self, cv_text: str) -> CVProfile:
        normalized_text = cv_text.strip()

        if not normalized_text:
            raise FileValidationException(
                message="No readable text was found in the CV.",
            )

        if len(normalized_text) > self._max_text_chars:
            raise FileValidationException(
                message="The extracted CV text is too large.",
                details={
                    "character_count": len(normalized_text),
                    "maximum": self._max_text_chars,
                },
            )

        prompt_value = CV_PARSER_PROMPT.invoke({"cv_text": normalized_text})

        for attempt in range(2):
            try:
                result: Any = (await self._structured_llm.ainvoke(prompt_value))

                if isinstance(result, CVProfile):
                    return result

                return CVProfile.model_validate(result)

            except (OutputParserException, ValidationError, TypeError, ValueError) as exc:
                if attempt == 0:
                    logger.warning(
                        "Invalid structured CV output; retrying",
                        extra={
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                raise StructuredOutputException(
                    details={"reason": type(exc).__name__,},
                ) from exc

            except AppException:
                raise

            except Exception as exc:
                logger.exception(
                    "CV parser LLM request failed",
                    extra={"error_type": type(exc).__name__,},
                )

                raise ExternalServiceException(
                    service="llm",
                    message="The CV parsing service is unavailable.",
                ) from exc

        raise StructuredOutputException()