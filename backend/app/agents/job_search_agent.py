import logging
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ExternalServiceException
from app.prompts.job_search import JOB_SEARCH_QUERY_PROMPT
from app.schemas.job_search import (
    JobSearchFilters,
    JobSearchPlan,
    JobSearchRequest,
    JobSearchSort,
    JobSearchStrategy,
)


LOGGER = logging.getLogger(__name__)


class JobSearchAgent:
    def __init__(self, *, llm: BaseChatModel, settings: Settings) -> None:
        self._structured_llm = llm.with_structured_output(
            JobSearchPlan,
            method=settings.llm_structured_output_method,
        )

    async def analyze(self, request: JobSearchRequest) -> JobSearchPlan:
        prompt_value = JOB_SEARCH_QUERY_PROMPT.invoke(
            {
                "query": request.query,
                "filters": request.filters.model_dump_json(),
                "sort": request.sort.value,
            }
        )

        for attempt in range(2):
            try:
                result: Any = await self._structured_llm.ainvoke(
                    prompt_value
                )

                plan = (
                    result
                    if isinstance(result, JobSearchPlan)
                    else JobSearchPlan.model_validate(result)
                )

                return self._apply_request_constraints(
                    request=request,
                    plan=plan,
                )

            except (
                OutputParserException,
                ValidationError,
                TypeError,
                ValueError,
            ) as exc:
                if attempt == 0:
                    LOGGER.warning(
                        "Invalid structured job search plan; retrying",
                        extra={
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue

                LOGGER.exception(
                    "Job search query analyzer returned invalid output",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message="The job search query could not be analyzed.",
                ) from exc

            except Exception as exc:
                LOGGER.exception(
                    "Job search query analyzer request failed",
                    extra={
                        "error_type": type(exc).__name__,
                    },
                )

                raise ExternalServiceException(
                    service="llm",
                    message="The job search query analyzer is unavailable.",
                ) from exc

        raise ExternalServiceException(
            service="llm",
            message="The job search query could not be analyzed.",
        )

    @staticmethod
    def _apply_request_constraints(*, request: JobSearchRequest, plan: JobSearchPlan) -> JobSearchPlan:
        explicit = request.filters
        inferred = plan.filters

        filters = JobSearchFilters(
            locations=explicit.locations or inferred.locations,
            employment_types=(
                explicit.employment_types
                or inferred.employment_types
            ),
            work_modes=explicit.work_modes or inferred.work_modes,
            seniority_levels=(
                explicit.seniority_levels
                or inferred.seniority_levels
            ),
            skills=explicit.skills or inferred.skills,
            salary_min=(
                explicit.salary_min
                if explicit.salary_min is not None
                else inferred.salary_min
            ),
            salary_currency=(
                explicit.salary_currency
                or inferred.salary_currency
            ),
            posted_after=(
                explicit.posted_after
                or inferred.posted_after
            ),
            include_expired=explicit.include_expired,
        )

        sort = plan.sort

        if request.sort != JobSearchSort.RELEVANCE:
            sort = request.sort

        return JobSearchPlan(
            original_query=request.query,
            semantic_query=plan.semantic_query,
            keywords=plan.keywords,
            filters=filters,
            strategy=JobSearchStrategy.HYBRID,
            sort=sort,
            confidence=plan.confidence,
        )