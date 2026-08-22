from app.core.exceptions import ResourceNotFoundException
from app.repositories.cv import CVRepository
from app.schemas.conversations_intent import IntentAnalysisInput, ConversationRequest, IntentAnalysisResult
from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer

class ConservationService:
    def __init__(self, *, analyzer: ConversationIntentAnalyzer, cv_repository: CVRepository) -> None:
        self._analyzer = analyzer
        self._cv_repository = cv_repository

    async def analyze_intent(self, request: ConversationRequest) -> IntentAnalysisResult:
        has_cv = await self._resolve_cv(request.cv_id)
        has_jd = request.job_description is not None

        analyzer_input = IntentAnalysisInput(
            message=request.message,
            has_cv=has_cv,
            has_jd=has_jd,
        )

        return await self._analyzer.analyze(analyzer_input)

    async def _resolve_cv(self, cv_id: str | None) -> bool:
        if cv_id is None:
            return False

        profile = await self._cv_repository.get(cv_id)

        if profile is None:
            raise ResourceNotFoundException(
                resource="CV",
                identifier=cv_id
            )

        return True