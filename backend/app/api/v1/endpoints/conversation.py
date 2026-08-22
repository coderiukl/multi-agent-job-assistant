from fastapi import APIRouter, status

from app.api.dependencies import ConversationIntentAnalyzerDependency
from app.schemas.conversations_intent import IntentAnalysisInput, IntentAnalysisResult
from app.schemas.response import ApiResponse

router = APIRouter()


@router.post(
    "/intent-analysis",
    response_model=ApiResponse[IntentAnalysisResult],
    status_code=status.HTTP_200_OK,
)
async def analyze_conversation_intent(
    request: IntentAnalysisInput,
    analyzer: ConversationIntentAnalyzerDependency,
) -> ApiResponse[IntentAnalysisResult]:
    result = await analyzer.analyze(request)

    return ApiResponse(
        message="Conversation intent analyzed successfully.",
        data=result,
    )
