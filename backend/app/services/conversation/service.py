from typing import cast, Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.graphs.conversation.state import ConversationState
from app.graphs.conversation.routing import route_after_intent
from app.schemas.conversation import (
    ConversationHistoryData,
    ConversationMessageData,
    ConversationResponseData,
    ConversationStatus,
)
from app.schemas.conversations_intent import ConversationRequest, IntentAnalysisResult
from app.schemas.human_review import ResumeConversationRequest, HumanReviewRequest

class ConversationService:
    def __init__(self, *, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def process(self, request: ConversationRequest) -> ConversationResponseData:
        state = await self._invoke_graph(request)

        interrupts = state.get("__interrupt__", [])

        if interrupts:
            interrupt_value = interrupts[0].value

            human_review = HumanReviewRequest.model_validate(interrupt_value)

            return ConversationResponseData(
                thread_id=request.thread_id,
                assistant_message=human_review.message,
                status=ConversationStatus.WAITING_FOR_HUMAN,
                route=state["route"],
                intent=state["intent"],
                cv_id=state.get("cv_id"),
                missing_inputs=state.get('missing_inputs', []),
                human_review=human_review,
                workflow=state.get("workflow"),
                cv_analysis_result=state.get("cv_analysis_result"),
                career_advice_result=state.get("career_advice_result"),
                cover_letter_result=state.get("cover_letter_result"),
                job_search_result=state.get("job_search_result"),
                job_matching_result=state.get("job_matching_result"),
                workflow_job_matches=state.get("workflow_job_matches", []),
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
                )
            )

        return ConversationHistoryData(
            thread_id=thread_id,
            messages=messages,
        )

    async def delete_history(self, thread_id: UUID) -> None:
        checkpointer = self._graph.checkpointer

        if checkpointer is None:
            return

        await checkpointer.adelete_thread(str(thread_id))
    
    async def analyze_intent(self, request: ConversationRequest) -> IntentAnalysisResult:
        state = await self._invoke_graph(request, stop_after_intent=True)

        return state["intent"]

    async def _invoke_graph(self, request: ConversationRequest, stop_after_intent: bool = False) -> ConversationState:
        initial_state: ConversationState = {
            "message": request.message, 
            "messages": [HumanMessage(content=request.message)], 
        }

        if "cv_id" in request.model_fields_set:
            initial_state["cv_id"] = request.cv_id

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

    async def resume(self, request: ResumeConversationRequest) -> ConversationResponseData:
        config = {
            "configurable": {
                "thread_id": str(request.thread_id),
            }
        }

        result = await self._graph.ainvoke(
            Command(
                resume=request.decision.model_dump(mode="json")
            ),
            config=config,
        )

        state = cast(ConversationState, result)
        return self._build_response(
            thread_id=request.thread_id,
            state=state,
        )

    @staticmethod
    def _get_message_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()

        return str(content).strip()

    def _build_response(self, *, thread_id: UUID, state: ConversationState) -> ConversationResponseData:
        human_review = state.get("human_review_request")

        if human_review is not None and state.get("human_review_decision") is None:
            return ConversationResponseData(
                thread_id=thread_id,
                assistant_message=human_review.message,
                status=ConversationStatus.WAITING_FOR_HUMAN,
                route=state.get("route") or route_after_intent(state),
                intent=state.get("intent"),
                cv_id=state.get("cv_id"),
                missing_inputs=state.get('missing_inputs', []),
                human_review=human_review,
                workflow=state.get("workflow"),
                cv_analysis_result=state.get("cv_analysis_result"),
                career_advice_result=state.get("career_advice_result"),
                cover_letter_result=state.get("cover_letter_result"),
                job_search_result=state.get("job_search_result"),
                job_matching_result=state.get("job_matching_result"),
                workflow_job_matches=state.get("workflow_job_matches", []),
            )
        
        return ConversationResponseData(
            thread_id=thread_id,
            assistant_message=state['assistant_message'],
            status=state['status'],
            route=state['route'],
            intent=state['intent'],
            cv_id=state.get("cv_id"),
            missing_inputs=state.get('missing_inputs', []),
            human_review=None,
            workflow=state.get("workflow"),
            cv_analysis_result=state.get("cv_analysis_result"),
            career_advice_result=state.get("career_advice_result"),
            cover_letter_result=state.get("cover_letter_result"),
            job_search_result=state.get("job_search_result"),
            job_matching_result=state.get("job_matching_result"),
            workflow_job_matches=state.get("workflow_job_matches", []),
        )

