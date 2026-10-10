import asyncio
import json
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
from app.core.llm_concurrency import LLMConcurrencyLimiter
from app.prompts.job_matching import JOB_MATCHING_AGENT_PROMPT
from app.schemas.job_matching import (
    JobMatchingAssessment,
    JobMatchingInput,
    MatchStatus,
)

logger = logging.getLogger(__name__)


class JobMatchingAgent:
    def __init__(
        self,
        *,
        llm: BaseChatModel,
        settings: Settings,
        limiter: LLMConcurrencyLimiter | None = None,
    ) -> None:
        self._structured_llm = llm.with_structured_output(
            JobMatchingAssessment, method=settings.llm_structured_output_method
        )
        self._limiter = limiter or LLMConcurrencyLimiter(
            settings.job_matching_max_concurrency
        )
        self._timeout_seconds = settings.job_matching_request_timeout_seconds

    async def assess(self, matching_input: JobMatchingInput) -> JobMatchingAssessment:
        prompt_value = JOB_MATCHING_AGENT_PROMPT.invoke(
            {
                "cv_profile": matching_input.cv_profile.model_dump_json(
                    exclude_none=True
                ),
                "job_context": matching_input.job.model_dump_json(exclude_none=True),
                "requirements": self._serialize_requirements(matching_input),
                "cv_evidence_catalog": self._serialize_cv_evidence(matching_input),
            }
        )

        job_id = matching_input.job.job_id

        for attempt in range(2):
            try:
                async with self._limiter.slot():
                    result: Any = await asyncio.wait_for(
                        self._structured_llm.ainvoke(prompt_value),
                        timeout=self._timeout_seconds,
                    )
                assessment = (
                    result
                    if isinstance(result, JobMatchingAssessment)
                    else JobMatchingAssessment.model_validate(result)
                )
                self._validate_references(assessment, matching_input)

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
                ValueError,
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
                    message=("The job matching service is unavailable."),
                ) from exc

        raise StructuredOutputException(
            message=(
                "The job matching result could not be converted to structured data."
            )
        )

    @staticmethod
    def _serialize_requirements(matching_input: JobMatchingInput) -> str:
        return json.dumps(
            [item.model_dump(mode="json") for item in matching_input.requirements],
            ensure_ascii=False,
        )

    @staticmethod
    def _serialize_cv_evidence(matching_input: JobMatchingInput) -> str:
        return json.dumps(
            [
                item.model_dump(mode="json")
                for item in matching_input.cv_evidence_catalog
            ],
            ensure_ascii=False,
        )

    @staticmethod
    def _validate_references(
        assessment: JobMatchingAssessment,
        matching_input: JobMatchingInput,
    ) -> None:
        requirements = {
            item.requirement_id: item for item in matching_input.requirements
        }
        evidence_catalog = {
            item.cv_evidence_id: item for item in matching_input.cv_evidence_catalog
        }
        assessed_ids: set[str] = set()

        for item in assessment.evidence:
            if item.status == MatchStatus.NOT_APPLICABLE:
                continue
            requirement = requirements.get(item.requirement_id or "")
            if requirement is None or requirement.dimension != item.dimension:
                raise ValueError("Unknown or inconsistent requirement_id.")
            if item.requirement_id in assessed_ids:
                raise ValueError("Each requirement_id must be assessed once.")
            assessed_ids.add(item.requirement_id)
            if any(
                evidence_id not in evidence_catalog
                for evidence_id in item.cv_evidence_ids
            ):
                raise ValueError("Unknown cv_evidence_id.")

        if assessed_ids != set(requirements):
            raise ValueError("Every normalized requirement must be assessed once.")

        applicable_dimensions = {item.dimension for item in requirements.values()}
        score_by_dimension = {
            "technical_skills": assessment.breakdown.technical_skills,
            "experience": assessment.breakdown.experience,
            "education": assessment.breakdown.education,
            "projects": assessment.breakdown.projects,
            "language_and_certifications": (
                assessment.breakdown.language_and_certifications
            ),
        }
        for dimension, score in score_by_dimension.items():
            if dimension not in {item.value for item in applicable_dimensions}:
                if score != 0:
                    raise ValueError(
                        "Non-applicable dimensions must have a zero score."
                    )
