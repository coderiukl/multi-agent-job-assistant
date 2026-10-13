from typing import Any

from app.schemas.conversation_search_context import (
    ConversationSearchContext,
)
from app.schemas.conversations_intent import IntentAnalysisInput
from app.schemas.job_matching import JobMatchingInput
from app.schemas.job_search import JobSearchRequest
from app.schemas.job_search_context import JobSearchContext
from evals.runtime import (
    get_intent_analyzer,
    get_job_matching_service,
    get_job_search_agent,
    get_job_search_service,
)

async def intent_analysis_target(inputs: dict[str, Any]) -> dict[str, Any]:
    analyzer = get_intent_analyzer()

    input_data = IntentAnalysisInput(
        message=inputs["message"],
        conversation_history=inputs.get("conversation_history", "No previous conversation"),
        has_cv=bool(inputs.get("has_cv", False)),
        has_jd=bool(inputs.get("has_jd", False)),
        search_context=ConversationSearchContext.model_validate(inputs.get("search_context", {})),
    )

    result = await analyzer.analyze(input_data)

    return result.model_dump(mode="json")

async def job_search_plan_target(inputs: dict[str, Any]) -> dict[str, Any]:
    agent = get_job_search_agent()

    request = JobSearchRequest.model_validate(
        {
            "query": inputs["query"],
            "filters": inputs.get("filters", {}),
            "sort": inputs.get("sort", "relevance"),
            "page": 1,
            "page_size": 10,
        }
    )

    context_value = inputs.get("candidate_context")
    context = JobSearchContext.model_validate(context_value) if context_value else None
    plan = await agent.analyze(request, context=context)
    
    return plan.model_dump(mode="json")

async def job_search_retrieval_target(inputs: dict[str, Any]) -> dict[str, Any]:
    service = get_job_search_service()

    request = JobSearchRequest.model_validate(
        {
            "query": inputs["query"],
            "filters": inputs.get("filters", {}),
            "sort": inputs.get("sort", "relevance"),
            "page": inputs.get("page", 1),
            "page_size": 10,
        }
    )

    context_value = inputs.get("candidate_context")
    context = JobSearchContext.model_validate(context_value) if context_value else None
    result = await service.search(request, context=context)

    return result.model_dump(mode="json")

async def job_matching_target(inputs: dict[str, Any]) -> dict[str, Any]:
    service = get_job_matching_service()

    matching_input = JobMatchingInput.model_validate(
        {
           "cv_profile": inputs["cv_profile"],
           "job": inputs["job"],
        }
    )

    result = await service.match(matching_input)

    return result.model_dump(mode="json")
