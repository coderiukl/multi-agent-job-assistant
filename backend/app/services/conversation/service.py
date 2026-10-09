from datetime import datetime
from typing import Any, cast
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.core.exceptions import AppException, ResourceNotFoundException
from app.graphs.conversation.routing import route_after_intent
from app.graphs.conversation.state import ConversationState
from app.schemas.conversation import (
    ConversationHistoryData,
    ConversationMessageData,
    ConversationResponseData,
    ConversationRoute,
    ConversationStatus,
    ConversationThreadSummaryData,
)
from app.schemas.conversation_search_context import ConversationSearchContext
from app.schemas.conversations_intent import ConversationRequest, IntentAnalysisResult
from app.schemas.human_review import HumanReviewRequest, ResumeConversationRequest
from app.utils.serialization import to_json_compatible


class ConversationService:
    def __init__(self, *, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def process(self, request: ConversationRequest) -> ConversationResponseData:
        pending_review = await self._get_pending_review(request.thread_id)

        if pending_review is not None:
            raise AppException(
                status_code=409,
                code="HUMAN_REVIEW_PENDING",
                message=(
                    "Cuộc trò chuyện đang chờ bạn xử lý yêu cầu duyệt "
                    "trước khi gửi tin nhắn mới."
                ),
                details={
                    "pending_human_review": pending_review.model_dump(mode="json"),
                },
            )

        state = await self._invoke_graph(request)

        interrupts = state.get("__interrupt__", [])

        if interrupts:
            interrupt_value = interrupts[0].value

            human_review = HumanReviewRequest.model_validate(interrupt_value)

            return ConversationResponseData(
                thread_id=request.thread_id,
                turn_id=request.turn_id,
                assistant_message=human_review.message,
                status=ConversationStatus.WAITING_FOR_HUMAN,
                route=state["route"],
                intent=state["intent"],
                cv_id=state.get("cv_id"),
                missing_inputs=state.get("missing_inputs", []),
                human_review=human_review,
                workflow=state.get("workflow"),
                cv_analysis_result=state.get("cv_analysis_result"),
                career_advice_result=state.get("career_advice_result"),
                cover_letter_result=state.get("cover_letter_result"),
                job_search_result=state.get("job_search_result"),
                job_matching_result=state.get("job_matching_result"),
                workflow_job_matches=state.get("workflow_job_matches", []),
                search_context=state.get(
                    "search_context", ConversationSearchContext()
                ),
            )

        return self._build_response(
            thread_id=request.thread_id,
            state=state,
        )

    async def get_history(self, thread_id: UUID) -> ConversationHistoryData:
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": str(thread_id),
            }
        }

        snapshot = await self._graph.aget_state(config)

        pending_review = self._extract_pending_review(snapshot)

        stored_messages = snapshot.values.get("messages", [])

        messages: list[ConversationMessageData] = []

        for message in stored_messages:
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                continue

            content = self._get_message_content(message.content)

            if not content:
                continue

            messages.append(
                ConversationMessageData(
                    message_id=(str(message.id) if message.id is not None else None),
                    role=role,
                    content=content,
                    metadata=dict(message.additional_kwargs),
                )
            )

        return ConversationHistoryData(
            thread_id=thread_id,
            messages=messages,
            cv_id=snapshot.values.get("cv_id"),
            cv_name=snapshot.values.get("cv_name"),
            job_description=snapshot.values.get("job_description"),
            latest_result=self._build_history_result(snapshot.values),
            pending_human_review=pending_review,
            search_context=ConversationSearchContext.model_validate(
                snapshot.values.get("search_context") or {}
            ),
        )

    async def get_thread_summary(
        self,
        thread_id: UUID,
        *,
        created_at: datetime,
    ) -> ConversationThreadSummaryData | None:
        snapshot = await self._graph.aget_state(
            {"configurable": {"thread_id": str(thread_id)}}
        )

        if not snapshot.values:
            return None

        user_messages: list[str] = []
        for message in snapshot.values.get("messages", []):
            if not isinstance(message, HumanMessage):
                continue

            content = self._get_message_content(message.content)
            if content:
                user_messages.append(content)

        first_message = user_messages[0] if user_messages else ""
        latest_message = user_messages[-1] if user_messages else first_message
        title = self._truncate_summary(first_message, 80)
        preview = self._truncate_summary(latest_message, 140)
        result_fields = {
            ConversationRoute.JOB_SEARCH: "job_search_result",
            ConversationRoute.JOB_MATCHING: "job_matching_result",
            ConversationRoute.CV_ANALYSIS: "cv_analysis_result",
            ConversationRoute.CAREER_ADVICE: "career_advice_result",
            ConversationRoute.COVER_LETTER: "cover_letter_result",
        }
        result_types = [
            route
            for route, field in result_fields.items()
            if snapshot.values.get(field) is not None
        ]
        updated_at = created_at
        if snapshot.created_at:
            try:
                updated_at = datetime.fromisoformat(snapshot.created_at)
            except ValueError:
                pass

        return ConversationThreadSummaryData(
            thread_id=thread_id,
            title=title or "Cuộc trò chuyện",
            preview=preview,
            created_at=created_at,
            updated_at=updated_at,
            has_cv=bool(snapshot.values.get("cv_id")),
            has_job_description=bool(snapshot.values.get("job_description")),
            result_types=result_types,
            has_pending_human_review=(
                self._extract_pending_review(snapshot) is not None
            ),
        )

    @staticmethod
    def _truncate_summary(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

    async def delete_history(self, thread_id: UUID) -> None:
        checkpointer = self._graph.checkpointer

        if checkpointer is None:
            return

        await checkpointer.adelete_thread(str(thread_id))

    async def analyze_intent(
        self,
        request: ConversationRequest,
    ) -> IntentAnalysisResult:
        state = await self._invoke_graph(request, stop_after_intent=True)

        return state["intent"]

    async def _invoke_graph(
        self,
        request: ConversationRequest,
        stop_after_intent: bool = False,
    ) -> ConversationState:
        message_context = {
            key: value
            for key, value in {
                "cv_id": request.cv_id,
                "cv_name": request.cv_name,
                "job_description": request.job_description,
            }.items()
            if value is not None
        }

        initial_state: ConversationState = {
            "message": request.message,
            "turn_id": str(request.turn_id),
            "messages": [
                HumanMessage(
                    content=request.message,
                    additional_kwargs={"context": message_context},
                )
            ],
        }

        if "cv_id" in request.model_fields_set:
            initial_state["cv_id"] = request.cv_id

        if "cv_name" in request.model_fields_set:
            initial_state["cv_name"] = request.cv_name

        if "job_description" in request.model_fields_set:
            initial_state["job_description"] = request.job_description

        config: dict[str, Any] = {
            "configurable": {
                "thread_id": str(request.thread_id),
            }
        }

        if stop_after_intent:
            result = await self._graph.ainvoke(
                initial_state, config=config, interrupt_after=["analyze_intent"]
            )
        else:
            result = await self._graph.ainvoke(initial_state, config=config)

        return cast(ConversationState, result)

    async def resume(
        self,
        request: ResumeConversationRequest,
    ) -> ConversationResponseData:
        config = {
            "configurable": {
                "thread_id": str(request.thread_id),
            }
        }

        snapshot = await self._graph.aget_state(config)

        if not snapshot.values:
            raise ResourceNotFoundException(
                resource="Conversation",
                identifier=str(request.thread_id),
            )

        pending_review = self._extract_pending_review(snapshot)

        if pending_review is None:
            raise AppException(
                status_code=409,
                code="HUMAN_REVIEW_NOT_PENDING",
                message="Cuộc trò chuyện này không còn yêu cầu nào đang chờ duyệt.",
            )

        result = await self._graph.ainvoke(
            Command(
                resume=request.decision.model_dump(mode="json"),
                update={"turn_id": str(request.turn_id)},
            ),
            config=config,
        )

        state = cast(ConversationState, result)
        return self._build_response(
            thread_id=request.thread_id,
            state=state,
        )

    async def _get_pending_review(self, thread_id: UUID) -> HumanReviewRequest | None:
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": str(thread_id),
            }
        }

        snapshot = await self._graph.aget_state(config)

        return self._extract_pending_review(snapshot)

    @staticmethod
    def _extract_pending_review(snapshot: Any) -> HumanReviewRequest | None:
        """Return a review only while the checkpoint is truly interrupted."""

        for task in snapshot.tasks:
            if task.name != "human_review":
                continue

            for task_interrupt in task.interrupts:
                try:
                    return HumanReviewRequest.model_validate(task_interrupt.value)
                except (TypeError, ValueError):
                    continue

        return None

    @staticmethod
    def _get_message_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()

        return str(content).strip()

    @staticmethod
    def _build_history_result(state: dict[str, Any]) -> dict[str, Any] | None:
        assistant_message = state.get("assistant_message")

        if not assistant_message:
            return None

        result: dict[str, Any] = {
            "assistant_message": assistant_message,
            "turn_id": state.get("turn_id"),
            "route": to_json_compatible(state.get("route")),
            "status": to_json_compatible(state.get("status")),
            "cv_id": state.get("cv_id"),
            "missing_inputs": to_json_compatible(state.get("missing_inputs", [])),
            "search_context": to_json_compatible(state.get("search_context", {})),
        }

        for field_name in (
            "intent",
            "workflow",
            "cv_analysis_result",
            "career_advice_result",
            "cover_letter_result",
            "job_search_result",
            "job_matching_result",
        ):
            value = state.get(field_name)
            result[field_name] = to_json_compatible(value)

        result["workflow_job_matches"] = to_json_compatible(
            state.get("workflow_job_matches", [])
        )

        return result

    def _build_response(
        self,
        *,
        thread_id: UUID,
        state: ConversationState,
    ) -> ConversationResponseData:
        human_review = state.get("human_review_request")

        if human_review is not None and state.get("human_review_decision") is None:
            return ConversationResponseData(
                thread_id=thread_id,
                turn_id=self._state_turn_id(state),
                assistant_message=human_review.message,
                status=ConversationStatus.WAITING_FOR_HUMAN,
                route=state.get("route") or route_after_intent(state),
                intent=state.get("intent"),
                cv_id=state.get("cv_id"),
                missing_inputs=state.get("missing_inputs", []),
                human_review=human_review,
                workflow=state.get("workflow"),
                cv_analysis_result=state.get("cv_analysis_result"),
                career_advice_result=state.get("career_advice_result"),
                cover_letter_result=state.get("cover_letter_result"),
                job_search_result=state.get("job_search_result"),
                job_matching_result=state.get("job_matching_result"),
                workflow_job_matches=state.get("workflow_job_matches", []),
                search_context=state.get("search_context", ConversationSearchContext()),
            )

        return ConversationResponseData(
            thread_id=thread_id,
            turn_id=self._state_turn_id(state),
            assistant_message=state["assistant_message"],
            status=state["status"],
            route=state["route"],
            intent=state["intent"],
            cv_id=state.get("cv_id"),
            missing_inputs=state.get("missing_inputs", []),
            human_review=None,
            workflow=state.get("workflow"),
            cv_analysis_result=state.get("cv_analysis_result"),
            career_advice_result=state.get("career_advice_result"),
            cover_letter_result=state.get("cover_letter_result"),
            job_search_result=state.get("job_search_result"),
            job_matching_result=state.get("job_matching_result"),
            workflow_job_matches=state.get("workflow_job_matches", []),
            search_context=state.get("search_context", ConversationSearchContext()),
        )

    @staticmethod
    def _state_turn_id(state: ConversationState) -> UUID | None:
        value = state.get("turn_id")
        return UUID(value) if value else None
