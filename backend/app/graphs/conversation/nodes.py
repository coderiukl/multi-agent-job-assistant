import logging
from typing import Any

from app.core.exceptions import ResourceNotFoundException

from app.graphs.conversation.state import ConversationState
from app.graphs.conversation.routing import collect_missing_inputs

from app.repositories.cv import CVRepository

from app.schemas.conversations_intent import IntentAnalysisInput
from app.schemas.conversation import ConversationRoute, ConversationStatus, RequiredInput
from app.schemas.job_search import JobSearchResult, JobSearchRequest
from app.schemas.job_matching import JobMatchingInput, JobMatchingResult, JobMatchTarget, MatchRecommendation

from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer
from app.services.job_search import HybridJobSearchService
from app.services.job_search_context import build_job_search_context
from app.services.job_matching import JobMatchingService


logger = logging.getLogger(__name__)

BUSINESS_ROUTE_MESSAGES: dict[ConversationRoute, str] = {
    ConversationRoute.CV_ANALYSIS: (
        "Yêu cầu phân tích CV đã được tiếp nhận."
    ),
    ConversationRoute.CAREER_ADVICE: (
        "Yêu cầu tư vấn nghề nghiệp đã được tiếp nhận."
    ),
    ConversationRoute.COVER_LETTER: (
        "Yêu cầu tạo thư ứng tuyển đã được tiếp nhận."
    ),
}

MATCH_RECOMMENDATION_LABELS: dict[MatchRecommendation, str] = {
    MatchRecommendation.STRONG_MATCH: "rất phù hợp",
    MatchRecommendation.GOOD_MATCH: "phù hợp",
    MatchRecommendation.PARTIAL_MATCH: "phù hợp một phần",
    MatchRecommendation.LOW_MATCH: "mức độ phù hợp thấp",
}

class ConversationNodes:
    def __init__(
        self,
        *,
        analyzer: ConversationIntentAnalyzer,
        cv_repository: CVRepository,
        job_search_service: HybridJobSearchService,
        job_matching_service: JobMatchingService,
    ) -> None:
        self._analyzer = analyzer
        self._cv_repository = cv_repository
        self._job_search_service = job_search_service
        self._job_matching_service = job_matching_service

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

    async def execute_job_search(self, state: ConversationState) -> dict[str, Any]:
        request = JobSearchRequest(
            query=state["message"],
            page=1,
            page_size=10
        )
        search_context = build_job_search_context(state.get("cv_profile"))

        result = await self._job_search_service.search(request, context=search_context)

        assistant_message = self._build_job_search_message(result, used_cv=search_context is not None)

        logger.info(
            "Conversation job search completed",
            extra={
                "query": request.query,
                "strategy": result.strategy.value,
                "total": result.total,
                "returned_items": len(result.items),
            },
        )

        return {
            "route": ConversationRoute.JOB_SEARCH,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": assistant_message,
            "job_search_result": result,
        }

    async def execute_job_matching(self, state: ConversationState) -> dict[str, Any]:
            cv_profile = state.get("cv_profile")
            job_description = state.get("job_description")
            missing_inputs: list[RequiredInput] = []

            if cv_profile is None:
                missing_inputs.append(RequiredInput.CV)

            if not job_description:
                missing_inputs.append(RequiredInput.JOB_DESCRIPTION)

            if missing_inputs:
                return {
                    "route": ConversationRoute.CLARIFICATION,
                    "status": ConversationStatus.NEEDS_CLARIFICATION,
                    "missing_inputs": missing_inputs,
                    "assistant_message": self._build_clarification_message(missing_inputs, generated_question=None),
                }

            matching_input = JobMatchingInput(cv_profile, job=JobMatchTarget(description=job_description))

            result = await self._job_matching_service.match(matching_input)

            assistant_message = self._build_job_matching_message(result)

            logger.info(
                "Conversation job matching completed",
                extra={
                    "cv_id": state.get("cv_id"),
                    "job_id": result.job_id,
                    "overall_score": result.overall_score,
                    "recommendation": (
                        result.recommendation.value
                    ),
                },
            )

            return {
                "route": ConversationRoute.JOB_MATCHING,
                "status": ConversationStatus.COMPLETED,
                "missing_inputs": [],
                "assistant_message": assistant_message,
                "job_matching_result": result,
            }
    
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
            "missing_inputs": missing_inputs,
            "assistant_message": assistant_message
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

    @staticmethod 
    def _build_job_search_message(result: JobSearchResult, *, used_cv: bool) -> str:
        returned_count = len(result.items)

        if returned_count == 0:
            return (
                "Tôi chưa tìm thấy công việc phù hợp với tiêu chí hiện tại. "
                "Bạn có thể thử mở rộng địa điểm, kỹ năng hoặc cấp độ kinh nghiệm."
            )

        if used_cv:
            return (
                f"Tôi đã chọn ra {returned_count} công việc có mức độ liên quan "
                "cao nhất dựa trên yêu cầu và thông tin nghề nghiệp trong CV của bạn."
            )

        return (
            f"Tôi đã chọn ra {returned_count} công việc có mức độ liên quan "
            "cao nhất với yêu cầu tìm kiếm của bạn."
        )

    @staticmethod 
    def _build_job_matching_message(result: JobMatchingResult) -> str:
        recommendation_label = MATCH_RECOMMENDATION_LABELS[result.recommendation]

        return (
            f"Mức độ phù hợp của CV với công việc là "
            f"{result.overall_score:.2f}/100 "
            f"({recommendation_label}). {result.summary}"
        )
