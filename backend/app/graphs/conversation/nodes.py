import asyncio
import hashlib
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from app.core.exceptions import AppException, ResourceNotFoundException
from app.graphs.conversation.planning import (
    collect_missing_initial_inputs,
    plan_workflow,
)
from app.graphs.conversation.routing import route_after_intent
from app.graphs.conversation.state import ConversationState
from app.graphs.conversation.workflow import advance_workflow
from app.memory.history import (
    build_contextual_user_message,
    format_conversation_history,
)
from app.repositories.cv import CVRepository
from app.schemas.career_advice import CareerAdviceInput, CareerAdviceResult
from app.schemas.conversation import (
    ConversationRoute,
    ConversationStatus,
    RequiredInput,
)
from app.schemas.conversation_search_context import (
    ConversationSearchContext,
    apply_search_context_patch,
)
from app.schemas.conversations_intent import IntentAnalysisInput
from app.schemas.cover_letter import CoverLetterInput, CoverLetterResult
from app.schemas.cv_analysis import CVAnalysisInput, CVAnalysisResult, CVQualityLevel
from app.schemas.human_review import (
    HumanReviewAction,
    HumanReviewDecision,
    HumanReviewRequest,
)
from app.schemas.job_matching import (
    JobMatchingInput,
    JobMatchingResult,
    JobMatchTarget,
    MatchRecommendation,
)
from app.schemas.job_search import JobSearchFilters, JobSearchRequest, JobSearchResult
from app.schemas.workflow import (
    MatchingExecutionSummary,
    WorkflowExecutionStatus,
    WorkflowJobMatch,
    WorkflowJobMatchOutcome,
    WorkflowJobMatchStatus,
    WorkflowStep,
)
from app.services.career_advice import CareerAdviceService
from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer
from app.services.cover_letter import CoverLetterService
from app.services.cv_analysis import CVAnalysisService
from app.services.job_matching import JobMatchingService
from app.services.job_search import HybridJobSearchService
from app.services.job_search_context import build_job_search_context
from app.utils.serialization import to_json_compatible

logger = logging.getLogger(__name__)


MATCH_RECOMMENDATION_LABELS: dict[MatchRecommendation, str] = {
    MatchRecommendation.STRONG_MATCH: "rất phù hợp",
    MatchRecommendation.GOOD_MATCH: "phù hợp",
    MatchRecommendation.PARTIAL_MATCH: "phù hợp một phần",
    MatchRecommendation.LOW_MATCH: "mức độ phù hợp thấp",
}

CV_QUALITY_LABELS: dict[CVQualityLevel, str] = {
    CVQualityLevel.EXCELLENT: "rất tốt",
    CVQualityLevel.GOOD: "tốt",
    CVQualityLevel.NEEDS_IMPROVEMENT: "cần cải thiện",
    CVQualityLevel.WEAK: "còn yếu",
}

WORKFLOW_MATCH_LIMIT = 5


class ConversationNodes:
    def __init__(
        self,
        *,
        analyzer: ConversationIntentAnalyzer,
        cv_repository: CVRepository,
        cv_analysis_service: CVAnalysisService,
        career_advice_service: CareerAdviceService,
        cover_letter_service: CoverLetterService,
        job_search_service: HybridJobSearchService,
        job_matching_service: JobMatchingService,
        workflow_matching_timeout_seconds: float = 180.0,
    ) -> None:
        self._analyzer = analyzer
        self._cv_repository = cv_repository
        self._cv_analysis_service = cv_analysis_service
        self._career_advice_service = career_advice_service
        self._cover_letter_service = cover_letter_service
        self._job_search_service = job_search_service
        self._job_matching_service = job_matching_service
        self._workflow_matching_timeout_seconds = workflow_matching_timeout_seconds

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
            extra={
                "cv_id": cv_id,
                "has_cv": has_cv,
                "has_jd": has_jd,
            },
        )

        return {
            "cv_profile": cv_profile,
            "has_cv": has_cv,
            "has_jd": has_jd,
        }

    async def analyze_intent(self, state: ConversationState) -> dict[str, Any]:
        analyzer_input = IntentAnalysisInput(
            message=state["message"],
            conversation_history=state.get(
                "conversation_history", "No previous conversation."
            ),
            has_cv=state.get("has_cv", False),
            has_jd=state.get("has_jd", False),
            search_context=state.get("search_context", ConversationSearchContext()),
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

    async def execute_cv_analysis(self, state: ConversationState) -> dict[str, Any]:
        cv_profile = state.get("cv_profile")

        if cv_profile is None:
            missing_inputs = [RequiredInput.CV]

            return {
                "route": ConversationRoute.CLARIFICATION,
                "status": ConversationStatus.NEEDS_CLARIFICATION,
                "missing_inputs": missing_inputs,
                "assistant_message": self._build_clarification_message(
                    missing_inputs=missing_inputs, generated_question=None
                ),
            }

        analysis_input = CVAnalysisInput(
            cv_profile=cv_profile,
            user_request=self._get_contextual_message(state),
        )

        result = await self._cv_analysis_service.analyze(analysis_input)

        assistant_message = self._build_cv_analysis_message(result)

        logger.info(
            "Conversation CV analysis completed",
            extra={
                "cv_id": state.get("cv_id"),
                "overall_score": result.overall_score,
                "quality_level": result.quality_level.value,
                "confidence": result.confidence,
            },
        )

        return {
            "route": ConversationRoute.CV_ANALYSIS,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": assistant_message,
            "cv_analysis_result": result,
        }

    async def execute_career_advice(self, state: ConversationState) -> dict[str, Any]:
        advice_input = CareerAdviceInput(
            user_request=self._get_contextual_message(state),
            cv_profile=state.get("cv_profile"),
        )

        result = await self._career_advice_service.advise(advice_input)
        assistant_message = self._build_career_advice_message(result)

        logger.info(
            "Conversation career advice completed",
            extra={
                "cv_id": state.get("cv_id"),
                "is_personalized": result.is_personalized,
                "recommended_role_count": len(result.recommended_roles),
                "confidence": result.confidence,
            },
        )

        return {
            "route": ConversationRoute.CAREER_ADVICE,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": assistant_message,
            "career_advice_result": result,
        }

    async def execute_job_search(self, state: ConversationState) -> dict[str, Any]:
        request = self._build_job_search_request(state)
        search_context = build_job_search_context(state.get("cv_profile"))

        result = await self._job_search_service.search(request, context=search_context)

        assistant_message = self._build_job_search_message(
            result, used_cv=search_context is not None
        )

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

    async def execute_cover_letter(self, state: ConversationState) -> dict[str, Any]:
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
                "assistant_message": (
                    self._build_clarification_message(
                        missing_inputs=missing_inputs,
                        generated_question=None,
                    )
                ),
            }

        selected_job = state.get("cover_letter_job")
        job = (
            JobMatchTarget.model_validate(selected_job)
            if selected_job is not None
            else JobMatchTarget(description=job_description)
        )
        letter_input = CoverLetterInput(
            user_request=self._cover_letter_request(state),
            cv_profile=cv_profile,
            job=job,
        )

        result = await self._cover_letter_service.generate(letter_input)

        logger.info(
            "Conversation cover letter completed",
            extra={
                "cv_id": state.get("cv_id"),
                "language": result.language.value,
                "word_count": result.word_count,
                "confidence": result.confidence,
            },
        )

        return {
            "route": ConversationRoute.COVER_LETTER,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": self._build_cover_letter_message(result),
            "cover_letter_result": result,
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
                "assistant_message": self._build_clarification_message(
                    missing_inputs=missing_inputs, generated_question=None
                ),
            }

        matching_input = JobMatchingInput(
            cv_profile=cv_profile, job=JobMatchTarget(description=job_description)
        )

        result = await self._job_matching_service.match(matching_input)

        assistant_message = self._build_job_matching_message(result)

        logger.info(
            "Conversation job matching completed",
            extra={
                "cv_id": state.get("cv_id"),
                "job_id": result.job_id,
                "overall_score": result.overall_score,
                "recommendation": result.recommendation.value,
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
        intent = state["intent"]
        missing_inputs = state.get("missing_inputs", [])

        assistant_message = self._build_clarification_message(
            missing_inputs=missing_inputs,
            generated_question=intent.clarification_question,
        )

        return {
            "route": ConversationRoute.CLARIFICATION,
            "status": ConversationStatus.NEEDS_CLARIFICATION,
            "missing_inputs": missing_inputs,
            "assistant_message": assistant_message,
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

    async def respond_general_question(
        self, state: ConversationState
    ) -> dict[str, Any]:
        advice_input = CareerAdviceInput(
            user_request=self._get_contextual_message(state),
            cv_profile=state.get("cv_profile"),
        )

        result = await self._career_advice_service.advise(advice_input)

        assistant_message = self._build_career_advice_message(result)

        return {
            "route": ConversationRoute.GENERAL_QUESTION,
            "status": ConversationStatus.COMPLETED,
            "missing_inputs": [],
            "assistant_message": assistant_message,
            "career_advice_result": result,
        }

    async def create_workflow(self, state: ConversationState) -> dict[str, Any]:
        workflow = plan_workflow(state)
        search_context = apply_search_context_patch(
            state.get("search_context"),
            state["intent"].search_context_patch,
        )
        missing_inputs = collect_missing_initial_inputs(
            workflow,
            has_cv=state.get("has_cv", False),
            has_jd=state.get("has_jd", False),
        )
        contextual_message = build_contextual_user_message(
            current_message=state["message"],
            search_context=search_context,
        )

        logger.info(
            "Conversation workflow planned",
            extra={
                "workflow_type": workflow.workflow_type.value,
                "steps": [step.value for step in workflow.steps],
                "current_step": (
                    workflow.current_step.value if workflow.current_step else None
                ),
            },
        )

        return {
            "workflow": workflow,
            "route": route_after_intent(state),
            "missing_inputs": missing_inputs,
            "search_context": search_context,
            "contextual_message": contextual_message,
        }

    async def execute_workflow_job_matching(
        self, state: ConversationState
    ) -> dict[str, Any]:
        workflow = state.get("workflow")
        cv_profile = state.get("cv_profile")
        search_result = state.get("job_search_result")
        job_description = state.get("job_description")

        if workflow is None:
            raise ValueError("Workflow plan is required for workflow job matching. ")

        if cv_profile is None:
            raise ValueError("CV profile is required for workflow CV analysis.")

        if search_result is None:
            if not job_description:
                raise ValueError(
                    "A job search result or job description is required "
                    "for workflow matching."
                )

            matching_input = JobMatchingInput(
                cv_profile=cv_profile, job=JobMatchTarget(description=job_description)
            )

            result = await self._job_matching_service.match(matching_input)

            updated_workflow = advance_workflow(workflow, WorkflowStep.JOB_MATCHING)

            return {
                "job_matching_result": result,
                "workflow": updated_workflow,
            }

        candidates = search_result.items[:WORKFLOW_MATCH_LIMIT]

        if not candidates:
            updated_workflow = advance_workflow(
                workflow,
                WorkflowStep.JOB_MATCHING,
            )

            return {
                "workflow": updated_workflow,
                "workflow_job_matches": [],
                "workflow_job_match_outcomes": [],
                "matching_execution": MatchingExecutionSummary(
                    status=WorkflowExecutionStatus.FAILED,
                    total=0,
                    succeeded=0,
                    failed=0,
                    skipped=0,
                ),
            }

        tasks = {
            asyncio.create_task(
                self._match_workflow_job(cv_profile=cv_profile, job=hit.job)
            ): hit.job
            for hit in candidates
        }
        done, pending = await asyncio.wait(
            tasks,
            timeout=self._workflow_matching_timeout_seconds,
        )
        matches: list[WorkflowJobMatch] = []
        outcomes: list[WorkflowJobMatchOutcome] = []

        for task in done:
            job = tasks[task]
            try:
                result = task.result()
                matches.append(result)
                outcomes.append(
                    WorkflowJobMatchOutcome(
                        job=job,
                        status=WorkflowJobMatchStatus.SUCCESS,
                        match=result.match,
                    )
                )
            except Exception as exc:
                outcomes.append(
                    WorkflowJobMatchOutcome(
                        job=job,
                        status=WorkflowJobMatchStatus.FAILED,
                        error_code=getattr(exc, "code", type(exc).__name__)[:100],
                    )
                )
                logger.warning(
                    "A workflow job could not be matched",
                    extra={"error_type": type(exc).__name__},
                )

        for task in pending:
            task.cancel()
            outcomes.append(
                WorkflowJobMatchOutcome(
                    job=tasks[task],
                    status=WorkflowJobMatchStatus.SKIPPED,
                    error_code="WORKFLOW_MATCHING_TIMEOUT",
                )
            )

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        ranked_matches = sorted(
            matches, key=lambda item: item.match.overall_score, reverse=True
        )
        succeeded = len(ranked_matches)
        failed = sum(item.status == WorkflowJobMatchStatus.FAILED for item in outcomes)
        skipped = sum(
            item.status == WorkflowJobMatchStatus.SKIPPED for item in outcomes
        )
        if succeeded == len(candidates):
            execution_status = WorkflowExecutionStatus.SUCCESS
        elif succeeded:
            execution_status = WorkflowExecutionStatus.PARTIAL_SUCCESS
        else:
            execution_status = WorkflowExecutionStatus.FAILED
        matching_execution = MatchingExecutionSummary(
            status=execution_status,
            total=len(candidates),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
        )

        updated_workflow = advance_workflow(
            workflow,
            WorkflowStep.JOB_MATCHING,
        )

        logger.info(
            "Workflow job matching completed",
            extra={
                "candidate_count": len(candidates),
                "matched_count": len(ranked_matches),
                "failed_count": failed,
                "skipped_count": skipped,
                "best_score": (
                    ranked_matches[0].match.overall_score if ranked_matches else None
                ),
                "next_step": updated_workflow.current_step.value,
            },
        )

        return {
            "workflow_job_matches": ranked_matches,
            "workflow_job_match_outcomes": outcomes,
            "matching_execution": matching_execution,
            "workflow": updated_workflow,
        }

    async def execute_workflow_job_search(
        self, state: ConversationState
    ) -> dict[str, Any]:
        workflow = state.get("workflow")

        if workflow is None:
            raise ValueError("Workflow plan is required for workflow job search.")

        request = self._build_job_search_request(state)

        search_context = build_job_search_context(state.get("cv_profile"))

        result = await self._job_search_service.search(request, context=search_context)

        updated_workflow = advance_workflow(
            workflow,
            WorkflowStep.JOB_SEARCH,
        )

        logger.info(
            "Workflow job search completed",
            extra={
                "query": request.query,
                "returned_items": len(result.items),
                "next_step": updated_workflow.current_step.value,
            },
        )

        return {
            "job_search_result": result,
            "workflow": updated_workflow,
        }

    async def execute_workflow_career_advice(
        self, state: ConversationState
    ) -> dict[str, Any]:
        workflow = state.get("workflow")

        if workflow is None:
            raise ValueError("Workflow plan is required for workflow career advice.")

        matching_results = [
            item.match for item in state.get("workflow_job_matches", [])[:3]
        ]

        direct_result = state.get("job_matching_result")

        if direct_result is not None and not matching_results:
            matching_results = [direct_result]

        advice_input = CareerAdviceInput(
            user_request=self._get_contextual_message(state),
            cv_profile=state.get("cv_profile"),
            matching_results=matching_results,
            matching_execution=state.get("matching_execution"),
        )

        result = await self._career_advice_service.advise(advice_input)

        updated_workflow = advance_workflow(
            workflow,
            WorkflowStep.CAREER_ADVICE,
        )

        logger.info(
            "Workflow career advice completed",
            extra={
                "is_personalized": result.is_personalized,
                "recommended_role_count": len(result.recommended_roles),
                "next_step": updated_workflow.current_step.value,
            },
        )

        return {
            "career_advice_result": result,
            "workflow": updated_workflow,
        }

    async def execute_workflow_cv_analysis(
        self, state: ConversationState
    ) -> dict[str, Any]:
        workflow = state.get("workflow")
        cv_profile = state.get("cv_profile")

        if workflow is None:
            raise ValueError("Workflow plan is required for workflow CV analysis")

        if cv_profile is None:
            raise ValueError("CV profile is required for workflow job matching.")

        analysis_input = CVAnalysisInput(
            cv_profile=cv_profile,
            user_request=self._get_contextual_message(state),
        )

        result = await self._cv_analysis_service.analyze(analysis_input)

        updated_workflow = advance_workflow(
            workflow,
            WorkflowStep.CV_ANALYSIS,
        )

        logger.info(
            "Workflow CV analysis completed",
            extra={
                "cv_id": state.get("cv_id"),
                "overall_score": result.overall_score,
                "quality_level": result.quality_level.value,
                "confidence": result.confidence,
                "next_step": updated_workflow.current_step.value,
            },
        )

        return {
            "cv_analysis_result": result,
            "workflow": updated_workflow,
        }

    async def execute_workflow_cover_letter(
        self, state: ConversationState
    ) -> dict[str, Any]:
        workflow = state.get("workflow")
        cv_profile = state.get("cv_profile")
        job_description = state.get("job_description")
        workflow_matches = state.get("workflow_job_matches", [])
        search_result = state.get("job_search_result")

        if workflow is None:
            raise ValueError("Workflow plan is required for workflow cover letter.")

        if cv_profile is None:
            raise ValueError("CV profile is required for workflow cover letter.")

        selected_job = state.get("cover_letter_job")
        if selected_job is not None:
            job = JobMatchTarget.model_validate(selected_job)
        elif workflow_matches:
            job = JobMatchTarget.from_normalized_job(workflow_matches[0].job)

        elif search_result is not None and search_result.items:
            job = JobMatchTarget.from_normalized_job(search_result.items[0].job)

        elif job_description:
            job = JobMatchTarget(
                description=job_description,
            )
        else:
            raise ValueError(
                "A matched job, job search result, or job description is "
                "required for workflow cover letter generation."
            )

        letter_input = CoverLetterInput(
            user_request=self._cover_letter_request(state),
            cv_profile=cv_profile,
            job=job,
        )

        result = await self._cover_letter_service.generate(letter_input)

        updated_workflow = advance_workflow(
            workflow,
            WorkflowStep.COVER_LETTER,
        )

        logger.info(
            "Workflow cover letter completed",
            extra={
                "cv_id": state.get("cv_id"),
                "language": result.language.value,
                "word_count": result.word_count,
                "confidence": result.confidence,
                "next_step": updated_workflow.current_step.value,
            },
        )

        return {
            "cover_letter_result": result,
            "workflow": updated_workflow,
        }

    async def build_workflow_response(self, state: ConversationState) -> dict[str, Any]:
        cv_analysis = state.get("cv_analysis_result")
        search_result = state.get("job_search_result")
        matches = state.get("workflow_job_matches", [])
        matching_execution_value = state.get("matching_execution")
        matching_execution = (
            MatchingExecutionSummary.model_validate(matching_execution_value)
            if matching_execution_value is not None
            else None
        )
        career_advice = state.get("career_advice_result")
        cover_letter = state.get("cover_letter_result")

        response_sections: list[str] = []

        if cv_analysis is not None:
            response_sections.append(self._build_cv_analysis_message(cv_analysis))

        if matches:
            match_lines = [
                "Tôi đã tìm và đánh giá các công việc phù hợp nhất với CV của bạn:"
            ]

            for index, item in enumerate(matches, start=1):
                job = item.job
                match = item.match
                company = job.company or "Không rõ công ty"

                match_lines.append(
                    f"{index}. {job.title} - {company}: {match.overall_score:.1f}/100"
                )

            response_sections.append("\n".join(match_lines))

        elif search_result is not None:
            response_sections.append(
                self._build_job_search_message(
                    search_result,
                    used_cv=state.get("cv_profile") is not None,
                )
            )

        if career_advice is not None:
            response_sections.append(self._build_career_advice_message(career_advice))

        if cover_letter is not None:
            response_sections.append(self._build_cover_letter_message(cover_letter))

        if response_sections:
            assistant_message = "\n\n".join(response_sections)
        else:
            assistant_message = "Workflow đã hoàn thành nhưng chưa có kết quả phù hợp."

        logger.info(
            "Workflow response built",
            extra={
                "has_cv_analysis": cv_analysis is not None,
                "has_job_search": search_result is not None,
                "matched_jobs": len(matches),
                "has_career_advice": career_advice is not None,
                "has_cover_letter": cover_letter is not None,
            },
        )

        response_status = ConversationStatus.COMPLETED
        if matching_execution is not None:
            if matching_execution.status == WorkflowExecutionStatus.PARTIAL_SUCCESS:
                response_status = ConversationStatus.PARTIAL_SUCCESS
            elif matching_execution.status == WorkflowExecutionStatus.FAILED:
                response_status = ConversationStatus.FAILED

        return {
            "route": route_after_intent(state),
            "status": response_status,
            "missing_inputs": [],
            "assistant_message": assistant_message,
        }

    async def review_before_cover_letter(
        self, state: ConversationState
    ) -> dict[str, object]:
        candidates = self._cover_letter_candidates(state)
        if not candidates:
            raise ValueError("A cover-letter target is required for review.")
        review_id = self._review_id("cover_letter_input", state, candidates)
        cv_profile = state.get("cv_profile")
        cv_version = self._content_version(
            cv_profile.model_dump(mode="json") if cv_profile is not None else None
        )
        review_request = HumanReviewRequest(
            review_id=review_id,
            review_type="cover_letter_confirmation",
            message=(
                "Hãy xác nhận CV, chọn công việc mục tiêu và chỉnh thông tin "
                "nếu cần trước khi tôi tạo bản nháp Cover Letter."
            ),
            data={
                "cv_id": state.get("cv_id"),
                "cv_name": state.get("cv_name"),
                "cv_version": cv_version,
                "jobs": candidates,
                "selected_job_id": candidates[0]["job_id"],
                "input_message": self._get_contextual_message(state),
            },
        )
        decision_payload = interrupt(review_request.model_dump(mode="json"))
        decision = HumanReviewDecision.model_validate(decision_payload)

        self._require_review_id(review_id, decision.review_id)
        if decision.action == HumanReviewAction.REJECT:
            return {
                "human_review_request": review_request,
                "human_review_decision": decision,
            }

        selected_id = decision.selected_job_id or candidates[0]["job_id"]
        candidate = next(
            (item for item in candidates if item["job_id"] == selected_id),
            None,
        )
        if candidate is None:
            raise AppException(
                status_code=409,
                code="INVALID_REVIEW_SELECTION",
                message="The selected job is not part of this review.",
            )
        overrides = decision.input_overrides
        selected_job = JobMatchTarget(
            job_id=(selected_id if len(selected_id) == 64 else None),
            title=overrides.get("job_title") or candidate.get("title"),
            company=overrides.get("company") or candidate.get("company"),
            description=(
                overrides.get("job_description") or candidate["description"]
            ),
            skills=candidate.get("skills", []),
        )

        return {
            "human_review_request": review_request,
            "human_review_decision": decision,
            "cover_letter_job": selected_job,
            "cover_letter_instructions": overrides.get("instructions"),
        }

    async def review_cover_letter_draft(
        self, state: ConversationState
    ) -> dict[str, Any]:
        raw_result = state.get("cover_letter_result")
        if raw_result is None:
            raise ValueError("Cover letter draft is required for review.")
        result = CoverLetterResult.model_validate(raw_result)
        review_id = self._review_id(
            "cover_letter_draft",
            state,
            result.model_dump(mode="json"),
        )
        review_request = HumanReviewRequest(
            review_id=review_id,
            review_type="cover_letter_draft",
            message="Vui lòng xem lại bản nháp Cover Letter trước khi xác nhận.",
            data={
                "draft": result.full_text,
                "word_count": result.word_count,
                "job": state.get("cover_letter_job"),
                "cv_id": state.get("cv_id"),
            },
        )
        payload = interrupt(review_request.model_dump(mode="json"))
        decision = HumanReviewDecision.model_validate(payload)
        self._require_review_id(review_id, decision.review_id)

        if decision.action == HumanReviewAction.APPROVE and decision.edited_draft:
            edited = decision.edited_draft.strip()
            result = result.model_copy(
                update={
                    "full_text": edited,
                    "word_count": len(edited.split()),
                }
            )

        return {
            "cover_letter_result": result,
            "cover_letter_draft_review": review_request,
            "cover_letter_draft_decision": decision,
        }

    async def respond_cover_letter_approved(
        self, state: ConversationState
    ) -> dict[str, Any]:
        raw_result = state.get("cover_letter_result")
        if raw_result is None:
            raise ValueError("Approved cover letter is required.")
        result = CoverLetterResult.model_validate(raw_result)
        return {
            "route": ConversationRoute.COVER_LETTER,
            "status": ConversationStatus.COMPLETED,
            "assistant_message": self._build_cover_letter_message(result),
        }

    async def respond_human_review_rejected(
        self, state: ConversationState
    ) -> dict[str, object]:
        decision = (
            state.get("cover_letter_draft_decision")
            or state.get("human_review_decision")
        )

        feedback = decision.feedback if decision else None

        message = "Đã dừng tạo Cover Letter theo yêu cầu của bạn."

        if feedback:
            message = f"{message} Phản hồi của bạn: {feedback}"

        return {
            "assistant_message": message,
            "status": ConversationStatus.COMPLETED,
        }

    @staticmethod
    def _require_review_id(expected: str, received: str) -> None:
        if expected != received:
            raise AppException(
                status_code=409,
                code="STALE_HUMAN_REVIEW",
                message="This review is no longer current.",
            )

    def _cover_letter_candidates(
        self, state: ConversationState
    ) -> list[dict[str, Any]]:
        matches = state.get("workflow_job_matches", [])
        if matches:
            return [
                {
                    **item.job.model_dump(mode="json"),
                    "match_score": item.match.overall_score,
                    "jd_version": self._content_version(
                        item.job.model_dump(mode="json")
                    ),
                }
                for item in matches[:5]
            ]
        search_result = state.get("job_search_result")
        if search_result is not None and search_result.items:
            return [
                {
                    **hit.job.model_dump(mode="json"),
                    "match_score": None,
                    "jd_version": self._content_version(
                        hit.job.model_dump(mode="json")
                    ),
                }
                for hit in search_result.items[:5]
            ]
        description = state.get("job_description")
        if description:
            return [
                {
                    "job_id": "direct_jd",
                    "title": None,
                    "company": None,
                    "description": description,
                    "skills": [],
                    "match_score": None,
                    "jd_version": self._content_version(description),
                }
            ]
        return []

    @staticmethod
    def _content_version(value: Any) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _review_id(self, stage: str, state: ConversationState, value: Any) -> str:
        digest = self._content_version(
            {
                "stage": stage,
                "cv_id": state.get("cv_id"),
                "value": value,
            }
        )
        return f"review_{digest}"

    def _cover_letter_request(self, state: ConversationState) -> str:
        request = self._get_contextual_message(state)
        instructions = state.get("cover_letter_instructions")
        if instructions:
            return f"{request}\n\nUser-approved instructions: {instructions}"
        return request

    @staticmethod
    def _build_clarification_message(
        *, missing_inputs: list[RequiredInput], generated_question: str | None
    ) -> str:
        missing_cv = RequiredInput.CV in missing_inputs
        missing_jd = RequiredInput.JOB_DESCRIPTION in missing_inputs

        if missing_cv and missing_jd:
            return (
                "Vui lòng tải lên CV và cung cấp mô tả công việc "
                "để tôi thực hiện yêu cầu này."
            )

        if missing_cv:
            return "Vui lòng tải lên CV để tôi có thể thực hiện yêu cầu này."

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

    @staticmethod
    def _build_cv_analysis_message(result: CVAnalysisResult) -> str:
        quality_label = CV_QUALITY_LABELS[result.quality_level]

        return (
            f"Điểm chất lượng nội dung CV của bạn là "
            f"{result.overall_score:.2f}/100 "
            f"(mức {quality_label}). {result.summary}"
        )

    @staticmethod
    def _build_career_advice_message(result: CareerAdviceResult) -> str:
        prefix = (
            "Dựa trên thông tin trong CV của bạn, "
            if result.is_personalized
            else "Dựa trên mục tiêu bạn cung cấp, "
        )

        if result.recommended_roles:
            primary_role = result.recommended_roles[0].role_title

            return f"{prefix}hướng ưu tiên là {primary_role}. {result.summary}"

        return f"{prefix}{result.summary}"

    @staticmethod
    def _build_cover_letter_message(result: CoverLetterResult) -> str:
        return (
            "Tôi đã tạo thư ứng tuyển dựa trên CV và "
            f"mô tả công việc của bạn "
            f"({result.word_count} từ)."
        )

    async def _match_workflow_job(self, *, cv_profile, job) -> WorkflowJobMatch:
        matching_input = JobMatchingInput(
            cv_profile=cv_profile,
            job=JobMatchTarget.from_normalized_job(job),
        )

        result = await self._job_matching_service.match(matching_input)

        return WorkflowJobMatch(job=job, match=result)

    async def prepare_turn(self, state: ConversationState) -> dict[str, Any]:
        message = state["message"]
        messages = state.get("messages", [])

        conversation_history = format_conversation_history(
            messages,
            current_message=message,
        )

        contextual_message = build_contextual_user_message(
            current_message=message,
            search_context=state.get("search_context"),
        )

        logger.info(
            "Conversation turn prepared",
            extra={
                "history_message_count": len(messages),
                "has_previous_context": (
                    conversation_history != "No previous conversation."
                ),
            },
        )

        return {
            "conversation_history": conversation_history,
            "contextual_message": contextual_message,
            "workflow": None,
            "missing_inputs": [],
            "cv_profile": None,
            "has_cv": False,
            "has_jd": False,
            "human_review_request": None,
            "human_review_decision": None,
            "cover_letter_job": None,
            "cover_letter_instructions": None,
            "cover_letter_draft_review": None,
            "cover_letter_draft_decision": None,
            "cv_analysis_result": None,
            "career_advice_result": None,
            "cover_letter_result": None,
            "job_search_result": None,
            "job_matching_result": None,
            "workflow_job_matches": [],
            "workflow_job_match_outcomes": [],
            "matching_execution": None,
        }

    async def record_assistant_message(
        self, state: ConversationState
    ) -> dict[str, Any]:
        assistant_message = state.get("assistant_message")

        if not assistant_message:
            return {}

        return {
            "messages": [
                AIMessage(
                    content=assistant_message,
                    additional_kwargs={
                        "result": self._build_message_result(state),
                    },
                ),
            ]
        }

    @staticmethod
    def _build_message_result(state: ConversationState) -> dict[str, Any]:
        result: dict[str, Any] = {
            "assistant_message": state.get("assistant_message"),
            "turn_id": state.get("turn_id"),
            "route": to_json_compatible(state.get("route")),
            "status": to_json_compatible(state.get("status")),
            "cv_id": state.get("cv_id"),
            "missing_inputs": to_json_compatible(state.get("missing_inputs", [])),
            "search_context": to_json_compatible(state.get("search_context", {})),
        }

        model_fields = (
            "intent",
            "workflow",
            "cv_analysis_result",
            "career_advice_result",
            "cover_letter_result",
            "job_search_result",
            "job_matching_result",
        )

        for field_name in model_fields:
            value = state.get(field_name)
            result[field_name] = to_json_compatible(value)

        result["workflow_job_matches"] = to_json_compatible(
            state.get("workflow_job_matches", [])
        )
        result["workflow_job_match_outcomes"] = to_json_compatible(
            state.get("workflow_job_match_outcomes", [])
        )
        result["matching_execution"] = to_json_compatible(
            state.get("matching_execution")
        )

        return result

    @staticmethod
    def _get_contextual_message(state: ConversationState) -> str:
        return state.get("contextual_message") or state["message"]

    @classmethod
    def _build_job_search_request(cls, state: ConversationState) -> JobSearchRequest:
        context = ConversationSearchContext.model_validate(
            state.get("search_context") or {}
        )
        filters = JobSearchFilters(
            locations=[context.location] if context.location else [],
            seniority_levels=[context.seniority] if context.seniority else [],
            work_modes=[context.work_mode] if context.work_mode else [],
        )

        return JobSearchRequest(
            query=cls._get_contextual_message(state),
            filters=filters,
            page=1,
            page_size=10,
        )
