from uuid import UUID

from fastapi import APIRouter, status

from app.api.resource_dependencies import (
    AuthorizedConversationServiceDependency,
)
from app.schemas.conversation import (
    ConversationHistoryData,
    ConversationResponseData,
)
from app.schemas.conversations_intent import (
    ConversationRequest,
    IntentAnalysisResult,
)
from app.schemas.error import ErrorResponse
from app.schemas.human_review import ResumeConversationRequest
from app.schemas.response import ApiResponse

router = APIRouter()


@router.get(
    "/threads/{thread_id}/messages",
    response_model=ApiResponse[ConversationHistoryData],
    status_code=status.HTTP_200_OK,
)
async def get_conversation_history(
    thread_id: UUID,
    conversation_service: AuthorizedConversationServiceDependency,
) -> ApiResponse[ConversationHistoryData]:
    result = await conversation_service.get_history(thread_id)

    return ApiResponse(
        message="Conversation history retrieved successfully.",
        data=result,
    )


@router.delete(
    "/threads/{thread_id}",
    response_model=ApiResponse[dict[str, bool]],
    status_code=status.HTTP_200_OK,
)
async def delete_conversation_history(
    thread_id: UUID,
    conversation_service: AuthorizedConversationServiceDependency,
) -> ApiResponse[dict[str, bool]]:
    await conversation_service.delete_history(thread_id)

    return ApiResponse(
        message="Conversation history deleted successfully.",
        data={"deleted": True},
    )


@router.post(
    "/messages",
    response_model=ApiResponse[ConversationResponseData],
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "The CV or conversation is not available to this user."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "The request data is invalid.",
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "The conversation is waiting for human review."
            ),
        },
        502: {
            "model": ErrorResponse,
            "description": "Conversation processing failed.",
        },
    },
)
async def process_conversation(
    request: ConversationRequest,
    conversation_service: AuthorizedConversationServiceDependency,
) -> ApiResponse[ConversationResponseData]:
    result = await conversation_service.process(request)

    return ApiResponse(
        message="Conversation processed successfully.",
        data=result,
    )


@router.post(
    "/intent-analysis",
    response_model=ApiResponse[IntentAnalysisResult],
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "The CV or conversation is not available to this user."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "The request data is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "Intent analysis failed.",
        },
    },
)
async def analyze_conversation_intent(
    request: ConversationRequest,
    conversation_service: AuthorizedConversationServiceDependency,
) -> ApiResponse[IntentAnalysisResult]:
    result = await conversation_service.analyze_intent(request)

    return ApiResponse(
        message="Conversation intent analyzed successfully.",
        data=result,
    )


@router.post(
    "/resume",
    response_model=ApiResponse[ConversationResponseData],
    responses={
        404: {
            "model": ErrorResponse,
            "description": "The conversation does not exist.",
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "The conversation is not waiting for human review."
            ),
        },
    },
)
async def resume_conversation(
    request: ResumeConversationRequest,
    conversation_service: AuthorizedConversationServiceDependency,
) -> ApiResponse[ConversationResponseData]:
    result = await conversation_service.resume(request)

    return ApiResponse(data=result)