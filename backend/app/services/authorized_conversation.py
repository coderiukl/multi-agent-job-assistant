from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.exceptions import ResourceNotFoundException
from app.repositories.ownership import OwnershipRepository
from app.schemas.conversation import (
    ConversationHistoryData,
    ConversationResponseData,
)
from app.schemas.conversations_intent import (
    ConversationRequest,
    IntentAnalysisResult,
)
from app.schemas.human_review import ResumeConversationRequest

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from app.services.conversation import ConversationService


class AuthorizedConversationService:
    def __init__(
        self,
        *,
        user_id: UUID,
        service: ConversationService,
        graph: CompiledStateGraph,
        ownership: OwnershipRepository,
    ) -> None:
        self._user_id = user_id
        self._service = service
        self._graph = graph
        self._ownership = ownership

    async def process(
        self,
        request: ConversationRequest,
    ) -> ConversationResponseData:
        await self._authorize_turn(request)
        return await self._service.process(request)

    async def analyze_intent(
        self,
        request: ConversationRequest,
    ) -> IntentAnalysisResult:
        await self._authorize_turn(request)
        return await self._service.analyze_intent(request)

    async def get_history(
        self,
        thread_id: UUID,
    ) -> ConversationHistoryData:
        await self._authorize_existing(thread_id)
        return await self._service.get_history(thread_id)

    async def resume(
        self,
        request: ResumeConversationRequest,
    ) -> ConversationResponseData:
        await self._authorize_existing(request.thread_id)
        return await self._service.resume(request)

    async def delete_history(
        self,
        thread_id: UUID,
    ) -> None:
        await self._ownership.require_thread(
            thread_id=thread_id,
            user_id=self._user_id,
        )

        if not await self._get_values(thread_id):
            self._not_found(thread_id)

        await self._service.delete_history(thread_id)

        # Keep ownership so another account cannot reuse this ID.

    async def _authorize_turn(
        self,
        request: ConversationRequest,
    ) -> None:
        owner = await self._ownership.get_thread_owner(
            request.thread_id
        )

        if owner is not None and owner != self._user_id:
            self._not_found(request.thread_id)

        values = await self._get_values(request.thread_id)

        if owner is None and values:
            # Legacy checkpoints must not be claimed automatically.
            self._not_found(request.thread_id)

        await self._require_checkpoint_cv(values)

        if request.cv_id is not None:
            await self._ownership.require_cv(
                cv_id=request.cv_id,
                user_id=self._user_id,
            )

        if owner is None:
            await self._ownership.claim_thread(
                thread_id=request.thread_id,
                user_id=self._user_id,
            )

    async def _authorize_existing(
        self,
        thread_id: UUID,
    ) -> None:
        await self._ownership.require_thread(
            thread_id=thread_id,
            user_id=self._user_id,
        )

        values = await self._get_values(thread_id)

        if not values:
            self._not_found(thread_id)

        await self._require_checkpoint_cv(values)

    async def _require_checkpoint_cv(
        self,
        values: dict[str, Any],
    ) -> None:
        cv_id = values.get("cv_id")

        if cv_id is not None:
            await self._ownership.require_cv(
                cv_id=cv_id,
                user_id=self._user_id,
            )

    async def _get_values(
        self,
        thread_id: UUID,
    ) -> dict[str, Any]:
        snapshot = await self._graph.aget_state(
            {
                "configurable": {
                    "thread_id": str(thread_id),
                }
            }
        )

        return dict(snapshot.values)

    @staticmethod
    def _not_found(thread_id: UUID) -> None:
        raise ResourceNotFoundException(
            resource="Conversation",
            identifier=str(thread_id),
        )