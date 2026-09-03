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
from app.prompts.job_matching import JOB_MATCHING_AGENT_PROMPT
from app.schemas.job_matching import JobMatchingAssessment, JobMatchingInput 


logger = logging.getLogger(__name__)

class JobMatchingAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings):
        self._structured_llm = llm.with_structured_output(JobMatchingAssessment, method=settings.llm_structured_output_method)

    async def assess(self, matching_input: JobMatchingInput) -> JobMatchingAssessment:
        prompt_value = JOB_MATCHING_AGENT_PROMPT.invoke(
            {
                "cv_profile": matching_input.cv_profile.model_dump_json(exclude_none=True),
                "job_context": matching_input.job.model_dump_json(exclude_none=True),
            }
        )

        job_id = matching_input.job.job_id

        for attempt in range(2):
            try:
                result: Any = await self._structured_llm.ainvoke(prompt_value)
                assessment = result if isinstance(result, JobMatchingAssessment) else JobMatchingAssessment.model_validate(result)

                logger.info(
                    "Job matching assessment completed",
                    extra={
                        "job_id": job_id,
                        "confidence": assessment.confidence,
                    },
                )

                return assessment

            except (
                OutputParserException,
                ValidationError,
                TypeError,
                ValueError
            ) as exc:
                if attempt == 0:
                    logger.warning(
                        "Invalid structured job matching output; retrying",
                        extra={
                            "job_id": job_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                logger.exception(
                    "Job matching agent returned invalid output",
                    extra={
                        "job_id": job_id,
                        "error_type": type(exc).__name__,
                    },
                )

                raise StructuredOutputException(
                    message=(
                        "The job matching result could not be "
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
                    "Job matching LLM request failed",
                    extra={
                        "job_id": job_id,
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message=(
                        "The job matching service is unavailable."
                    ),
                ) from exc

        raise StructuredOutputException(
            message=(
                "The job matching result could not be converted "
                "to structured data."
            )
        )
