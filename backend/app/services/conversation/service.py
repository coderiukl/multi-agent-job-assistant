from typing import cast

from langgraph.graph.state import CompiledStateGraph

from app.graphs.conversation.state import ConversationState

from app.schemas.conversation import ConversationResponseData
from app.schemas.conversations_intent import ConversationRequest, IntentAnalysisResult


class ConversationService:
    def __init__(self, *, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def process(self, request: ConversationRequest) -> ConversationResponseData:
        state = await self._invoke_graph(request)

        return ConversationResponseData(
            assistant_message=state["assistant_message"],
            status=state["status"],
            route=state["route"],
            intent=state["intent"],
            cv_id=request.cv_id,
            missing_inputs=state.get("missing_inputs", []),
        )
    
    async def analyze_intent(self, request: ConversationRequest) -> IntentAnalysisResult:
        state = await self._invoke_graph(request)

        return state['intent']
    
    async def _invoke_graph(self, request: ConversationRequest) -> ConversationState:
        initial_state: ConversationState = {
            "message": request.message,
            "cv_id": request.cv_id,
            "job_description": request.job_description,
        }

        result = await self._graph.ainvoke(initial_state)

        return cast(ConversationState, result)