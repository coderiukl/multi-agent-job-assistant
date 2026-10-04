from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents import (
    CareerAdviceAgent, CoverLetterAgent, CVAnalysisAgent, CVParserAgent,
    JobMatchingAgent, JobSearchAgent,
)
from app.core.exceptions import ExternalServiceException, StructuredOutputException
from app.schemas.career_advice import CareerAdviceAssessment, CareerAdviceInput
from app.schemas.cover_letter import CoverLetterDraft, CoverLetterInput
from app.schemas.cv_analysis import CVAnalysisAssessment, CVAnalysisInput
from app.schemas.job_matching import JobMatchingAssessment, JobMatchingInput, JobMatchTarget
from app.schemas.job_search import JobSearchPlan, JobSearchRequest


@pytest.fixture
def cases(cv_profile, results):
    target = JobMatchTarget(description="Python developer")
    return {
        "parser": (CVParserAgent, "parse", "Python SQL CV", cv_profile),
        "analysis": (CVAnalysisAgent, "analyze", CVAnalysisInput(
            cv_profile=cv_profile, user_request="Analyze"
        ), CVAnalysisAssessment.model_validate({
            k: v for k, v in results["cv_analysis"].model_dump().items()
            if k in CVAnalysisAssessment.model_fields
        })),
        "matching": (JobMatchingAgent, "assess", JobMatchingInput(
            cv_profile=cv_profile, job=target
        ), JobMatchingAssessment.model_validate({
            k: v for k, v in results["job_matching"].model_dump().items()
            if k in JobMatchingAssessment.model_fields
        })),
        "advice": (CareerAdviceAgent, "advise", CareerAdviceInput(
            user_request="Advise", cv_profile=cv_profile
        ), CareerAdviceAssessment.model_validate({
            k: v for k, v in results["career_advice"].model_dump().items()
            if k in CareerAdviceAssessment.model_fields
        })),
        "letter": (CoverLetterAgent, "generate", CoverLetterInput(
            user_request="Write", cv_profile=cv_profile, job=target
        ), CoverLetterDraft.model_validate({
            k: v for k, v in results["cover_letter"].model_dump().items()
            if k in CoverLetterDraft.model_fields
        })),
        "search": (JobSearchAgent, "analyze", JobSearchRequest(query="Python"),
                   JobSearchPlan(original_query="Python", semantic_query="Python")),
    }


@pytest.mark.parametrize("name", ["parser", "analysis", "matching", "advice", "letter", "search"])
@pytest.mark.parametrize("mode", ["success", "retry", "invalid", "timeout"])
async def test_agent_structured_output_and_failures(name, mode, cases, settings):
    cls, method, argument, expected = cases[name]
    output = expected.model_dump()
    responses = {
        "success": [output], "retry": [{}, output], "invalid": [{}, {}],
        "timeout": [TimeoutError("Test timeout")],
    }
    structured = SimpleNamespace(ainvoke=AsyncMock(side_effect=responses[mode]))
    llm = Mock()
    llm.with_structured_output.return_value = structured
    agent = cls(llm=llm, settings=settings)
    if mode in {"success", "retry"}:
        result = await getattr(agent, method)(argument)
        assert isinstance(result, type(expected))
        assert structured.ainvoke.await_count == (2 if mode == "retry" else 1)
    else:
        error = ExternalServiceException if mode == "timeout" or name == "search" else StructuredOutputException
        with pytest.raises(error):
            await getattr(agent, method)(argument)
        assert structured.ainvoke.await_count == (2 if mode == "invalid" else 1)
