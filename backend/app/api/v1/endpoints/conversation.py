from fastapi import APIRouter, status

from app.api.dependencies import ConversationServiceDependency
from app.schemas.conversation import ConversationResponseData
from app.schemas.conversations_intent import ConversationRequest, IntentAnalysisResult
from app.schemas.response import ApiResponse
from app.schemas.error import ErrorResponse

router = APIRouter()

@router.post(
    "/messages",
    response_model=ApiResponse[ConversationResponseData],
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "The referenced CV does not exist.",
        },
        422: {
            "model": ErrorResponse,
            "description": "The request data is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "Conversation processing failed.",
        },
    }
)
async def process_conversation(request: ConversationRequest, conversation_service: ConversationServiceDependency) -> ApiResponse[ConversationResponseData]:
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
            "description": "The referenced CV does not exist.",
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
    conversation_service: ConversationServiceDependency,
) -> ApiResponse[IntentAnalysisResult]:
    result = await conversation_service.analyze_intent(request)

    return ApiResponse(
        message="Conversation intent analyzed successfully.",
        data=result,
    )
