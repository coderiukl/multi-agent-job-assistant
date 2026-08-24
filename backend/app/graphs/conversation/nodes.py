import logging
from typing import Any

from app.core.exceptions import ResourceNotFoundException

from app.graphs.conversation.state import ConversationState
from app.graphs.conversation.routing import collect_missing_inputs

from app.repositories.cv import CVRepository

from app.schemas.conversations_intent import IntentAnalysisInput
from app.schemas.conversation import ConversationRoute, ConversationStatus, RequiredInput

from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer

logger = logging.getLogger(__name__)

BUSINESS_ROUTE_MESSAGES: dict[ConversationRoute, str] = {
    ConversationRoute.CV_ANALYSIS: (
        "Yêu cầu phân tích CV đã được tiếp nhận."
    ),
    ConversationRoute.JOB_SEARCH: (
        "Yêu cầu tìm kiếm việc làm đã được tiếp nhận."
    ),
    ConversationRoute.JOB_MATCHING: (
        "Yêu cầu đánh giá mức độ phù hợp giữa CV và công việc "
        "đã được tiếp nhận."
    ),
    ConversationRoute.CAREER_ADVICE: (
        "Yêu cầu tư vấn nghề nghiệp đã được tiếp nhận."
    ),
    ConversationRoute.COVER_LETTER: (
        "Yêu cầu tạo thư ứng tuyển đã được tiếp nhận."
    ),
}

class ConversationNodes:
    def __init__(self, *, analyzer: ConversationIntentAnalyzer, cv_repository: CVRepository) -> None:
        self._analyzer = analyzer
        self._cv_repository = cv_repository

    async def resolve_context(self, state: ConversationState) -> dict[str, Any]:
        cv_id = state.get("cv_id")
        job_description = state.get("job_description")

        cv_profile = None

        if cv_id is not None:
            cv_profile = await self._cv_repository.get(cv_id)

            if cv_profile is None:
                raise ResourceNotFoundException(
                    resource="CV",
                    identifier=cv_id,
                )

        has_cv = cv_profile is not None
        has_jd = bool(job_description)

        logger.info(
            "Conversation context resolved",
            extra = {
                "cv_id": cv_id,
                "has_cv": has_cv,
                "has_jd": has_jd,
            }
        )

        return {
            "cv_profile": cv_profile,
            "has_cv": has_cv,
            "has_jd": has_jd,
        }

    async def analyze_intent(self, state: ConversationState) -> dict[str, Any]:
        analyzer_input = IntentAnalysisInput(
            message=state["message"],
            has_cv=state.get("has_cv", False),
            has_jd=state.get("has_jd", False)
        )

        intent = await self._analyzer.analyze(analyzer_input)

        logger.info(
            "Conversation intent analyzed",
            extra={
                "primary_intent": intent.primary_intent.value,
                "confidence": intent.confidence,
                "needs_clarification": intent.needs_clarification,
            },
        )

        return {"intent": intent}

    async def respond_clarification(self, state: ConversationState) -> dict[str, Any]:
        intent = state['intent']
        missing_inputs = collect_missing_inputs(state)

        assistant_message = self._build_clarification_message(
            missing_inputs=missing_inputs,
            generated_question=intent.clarification_question,
        )

        return {
            "route": ConversationRoute.CLARIFICATION,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": (
                "Xin chào! Tôi có thể hỗ trợ bạn phân tích CV, "
                "tìm kiếm công việc, đánh giá mức độ phù hợp với JD "
                "và tư vấn định hướng nghề nghiệp."
            ),
        }

    async def respond_small_talk(
        self,
        state: ConversationState,
    ) -> dict[str, Any]:
        return {
            "route": ConversationRoute.SMALL_TALK,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": (
                "Xin chào! Tôi có thể hỗ trợ bạn phân tích CV, "
                "tìm kiếm công việc, đánh giá mức độ phù hợp với JD "
                "và tư vấn định hướng nghề nghiệp."
            ),
        }

    async def respond_out_out_scope(self, state: ConversationState) -> dict[str, Any]:
        return {
            "route": ConversationRoute.OUT_OF_SCOPE,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": (
                "Yêu cầu này nằm ngoài phạm vi hỗ trợ của hệ thống. "
                "Tôi có thể giúp bạn về CV, việc làm, JD và "
                "định hướng nghề nghiệp."
            ),
        }

    async def respond_general_question(self, state: ConversationState) -> dict[str, Any] :
        return {
            "route": ConversationRoute.GENERAL_QUESTION,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": (
                "Tôi là trợ lý hỗ trợ tìm việc. Bạn có thể gửi CV, "
                "mô tả công việc hoặc đặt câu hỏi về quá trình "
                "ứng tuyển và phát triển nghề nghiệp."
            ),
        }

    async def dispatch_business_task(self, state: ConversationState) -> dict[str, Any]:
        intent = state["intent"]

        route = ConversationRoute(intent.primary_intent.value)

        logger.info(
            "Conversation task routed",
            extra={
                "route": route.value,
            },
        )

        return {
            "route": route,
            "status": ConversationStatus.ROUTED,
            "missing_inputs": [],
            "assistant_message": BUSINESS_ROUTE_MESSAGES[route],
        }

    @staticmethod
    def _build_clarification_message(*, missing_inputs: list[RequiredInput], generated_question: str | None) -> str:
        missing_cv = RequiredInput.CV in missing_inputs
        missing_jd = RequiredInput.JOB_DESCRIPTION in missing_inputs

        if missing_cv and missing_jd:
            return (
                "Vui lòng tải lên CV và cung cấp mô tả công việc "
                "để tôi thực hiện yêu cầu này."
            )

        if missing_cv:
            return (
                "Vui lòng tải lên CV để tôi có thể thực hiện "
                "yêu cầu này."
            )

        if missing_jd:
            return (
                "Vui lòng cung cấp mô tả công việc (JD) để tôi "
                "có thể thực hiện yêu cầu này."
            )

        if generated_question:
            return generated_question

        return "Bạn có thể cung cấp thêm thông tin về yêu cầu không?"
