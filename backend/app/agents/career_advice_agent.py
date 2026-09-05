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
from app.prompts.career_advice import CAREER_ADVICE_AGENT_PROMPT
from app.schemas.career_advice import CareerAdviceAssessment, CareerAdviceInput


logger = logging.getLogger(__name__)


class CareerAdviceAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings) -> None:
        self._structured_llm = llm.with_structured_output(
            CareerAdviceAssessment,
            method=settings.llm_structured_output_method,
        )

    async def advise(self, advice_input: CareerAdviceInput) -> CareerAdviceAssessment:
        cv_profile = (
            advice_input.cv_profile.model_dump_json(exclude_none=True)
            if advice_input.cv_profile is not None
            else "null"
        )

        prompt_value = CAREER_ADVICE_AGENT_PROMPT.invoke(
            {
                "user_request": advice_input.user_request,
                "cv_profile": cv_profile,
            }
        )

        for attempt in range(2):
            try:
                result: Any = await self._structured_llm.ainvoke(prompt_value)

                assessment = (
                    result
                    if isinstance(result, CareerAdviceAssessment)
                    else CareerAdviceAssessment.model_validate(result)
                )

                logger.info(
                    "Career advice assessment completed",
                    extra={
                        "confidence": assessment.confidence,
                        "recommended_role_count": len(assessment.recommended_roles),
                        "skill_gap_count": len(assessment.skill_gaps),
                        "roadmap_step_count": len(assessment.roadmap),
                    },
                )

                return assessment

            except (
                OutputParserException,
                ValidationError,
                TypeError,
                ValueError,
            ) as exc:
                if attempt == 0:
                    logger.warning(
                        "Invalid career advice output; retrying",
                        extra={
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                logger.exception(
                    "Career advice agent returned invalid output",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise StructuredOutputException(
                    message=(
                        "The career advice result could not be "
                        "converted to structured data."
                    ),
                    details={
                        "reason": type(exc).__name__,
                    },
                ) from exc

            except AppException:
                raise

            except Exception as exc:
                logger.exception(
                    "Career advice LLM request failed",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message=(
                        "The career advice service is "
                        "unavailable."
                    ),
                ) from exc

        raise StructuredOutputException(
            message=(
                "The career advice result could not be "
                "converted to structured data."
            )
        )