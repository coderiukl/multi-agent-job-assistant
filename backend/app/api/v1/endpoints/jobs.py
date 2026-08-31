from fastapi import APIRouter, status

from app.api.dependencies import JobSearchServiceDependency

from app.schemas.error import ErrorResponse
from app.schemas.job_search import JobSearchRequest, JobSearchResult
from app.schemas.response import ApiResponse

router = APIRouter()

@router.post(
    "/search",
    response_model=ApiResponse[JobSearchResult],
    status_code=status.HTTP_200_OK,
    summary="Search jobs",
    responses={
        422: {
            "model": ErrorResponse,
            "description": (
                "The job search request is invalid."
            ),
        },
        500: {
            "model": ErrorResponse,
            "description": (
                "Job data could not be loaded."
            ),
        },
        502: {
            "model": ErrorResponse,
            "description": (
                "LLM, embedding, or Qdrant "
                "service is unavailable."
            ),
        },
    }
)
async def search_jobs(
    request: JobSearchRequest,
    search_service: JobSearchServiceDependency
) -> ApiResponse[JobSearchResult]:
    result = await search_service.search(request)
    return ApiResponse(
        message="Jobs searched successfully.",
        data=result,
    )