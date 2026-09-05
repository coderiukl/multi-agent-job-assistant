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
from app.prompts.cv_analysis import CV_ANALYSIS_AGENT_PROMPT
from app.schemas.cv_analysis import CVAnalysisAssessment, CVAnalysisInput

logger = logging.getLogger(__name__)


class CVAnalysisAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings) -> None:
        self._structured_llm = llm.with_structured_output(
            CVAnalysisAssessment,
            method=settings.llm_structured_output_method,
        )

    async def analyze(self, analysis_input: CVAnalysisInput) -> CVAnalysisAssessment:
        prompt_value = CV_ANALYSIS_AGENT_PROMPT.invoke(
            {
                "cv_profile":  analysis_input.cv_profile.model_dump_json(exclude_none=True),
                "user_request": analysis_input.user_request,
            }
        )

        for attempt in range(2):
            try:
                result: Any = await self._structured_llm.ainvoke(prompt_value)

                assessment = (
                    result
                    if isinstance(result, CVAnalysisAssessment)
                    else CVAnalysisAssessment.model_validate(result)
                )

                logger.info(
                    "CV analysis assessment completed",
                    extra={
                        "confidence": assessment.confidence,
                        "strength_count": len(assessment.strengths),
                        "weakness_count": len(assessment.weaknesses),
                        "improvement_count": len(
                            assessment.improvements
                        ),
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
                        "Invalid structured CV analysis output; retrying",
                        extra={
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                logger.exception(
                    "CV analysis agent returned invalid output",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise StructuredOutputException(
                    message=(
                        "The CV analysis result could not be "
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
                    "CV analysis LLM request failed",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message="The CV analysis service is unavailable.",
                ) from exc

        raise StructuredOutputException(
            message=(
                "The CV analysis result could not be converted "
                "to structured data."
            )
        )