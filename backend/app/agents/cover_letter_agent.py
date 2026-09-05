import logging
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import (
    AppException,
    ExternalServiceException,
    StructuredOutputException,
)
from app.prompts.cover_letter import COVER_LETTER_AGENT_PROMPT
from app.schemas.cover_letter import CoverLetterDraft, CoverLetterInput

logger = logging.getLogger(__name__)


class CoverLetterAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings) -> None:
        self._structured_llm = llm.with_structured_output(
            CoverLetterDraft,
            method=settings.llm_structured_output_method,
        )

    async def generate(self, letter_input: CoverLetterInput) -> CoverLetterDraft:
        prompt_value = COVER_LETTER_AGENT_PROMPT.invoke(
            {
                "user_request": letter_input.user_request,
                "cv_profile": letter_input.cv_profile.model_dump_json(exclude_none=True),
                "job_context": letter_input.job.model_dump_json(exclude_none=True),
            }
        )

        for attempt in range(2):
            try:
                result: Any = await self._structured_llm.ainvoke(prompt_value)

                draft = (
                    result
                    if isinstance(result, CoverLetterDraft)
                    else CoverLetterDraft.model_validate(result)
                )

                logger.info(
                    "Cover letter draft generated",
                    extra={
                        "language": draft.language.value,
                        "tone": draft.tone.value,
                        "body_paragraph_count": len(draft.body_paragraphs),
                        "confidence": draft.confidence,
                    },
                )

                return draft

            except (
                OutputParserException,
                ValidationError,
                TypeError,
                ValueError,
            ) as exc:
                if attempt == 0:
                    logger.warning(
                        (
                            "Invalid cover letter output; "
                            "retrying"
                        ),
                        extra={
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                logger.exception(
                    (
                        "Cover letter agent returned "
                        "invalid output"
                    ),
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise StructuredOutputException(
                    message=(
                        "The cover letter result could not "
                        "be converted to structured data."
                    ),
                    details={
                        "reason": type(exc).__name__,
                    },
                ) from exc

            except AppException:
                raise

            except Exception as exc:
                logger.exception(
                    "Cover letter LLM request failed",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message=(
                        "The cover letter service is "
                        "unavailable."
                    ),
                ) from exc

        raise StructuredOutputException(
            message=(
                "The cover letter result could not be "
                "converted to structured data."
            )
        )