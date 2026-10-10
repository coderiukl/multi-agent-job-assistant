from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.exceptions import ResourceNotFoundException
from app.repositories.conversation_turn import ConversationTurnRepository
from app.repositories.ownership import OwnershipRepository
from app.schemas.conversation import (
    ConversationHistoryData,
    ConversationResponseData,
    ConversationThreadSummaryData,
)
from app.schemas.conversations_intent import (
    ConversationRequest,
    IntentAnalysisResult,
)
from app.schemas.human_review import ResumeConversationRequest

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from app.services.conversation import ConversationService


logger = logging.getLogger(__name__)


class AuthorizedConversationService:
    def __init__(
        self,
        *,
        user_id: UUID,
        service: ConversationService,
        graph: CompiledStateGraph,
        ownership: OwnershipRepository,
        turns: ConversationTurnRepository,
    ) -> None:
        self._user_id = user_id
        self._service = service
        self._graph = graph
        self._ownership = ownership
        self._turns = turns

    async def process(
        self,
        request: ConversationRequest,
    ) -> ConversationResponseData:
        await self._authorize_turn(request)
        acquisition = await self._turns.begin(
            turn_id=request.turn_id,
            thread_id=request.thread_id,
            user_id=self._user_id,
            operation="message",
            payload_hash=self._payload_hash(request.model_dump(mode="json")),
        )
        if acquisition.is_replay:
            return ConversationResponseData.model_validate(
                acquisition.replay_response
            )

        try:
            result = await self._service.process(request)
            await self._turns.complete(
                turn_id=request.turn_id,
                response_data=result.model_dump(mode="json"),
            )
            return result
        except Exception as exc:
            await self._record_turn_failure(request.turn_id, exc)
            raise

    async def analyze_intent(
        self,
        request: ConversationRequest,
    ) -> IntentAnalysisResult:
        await self._authorize_turn(request)
        acquisition = await self._turns.begin(
            turn_id=request.turn_id,
            thread_id=request.thread_id,
            user_id=self._user_id,
            operation="intent_analysis",
            payload_hash=self._payload_hash(request.model_dump(mode="json")),
        )
        if acquisition.is_replay:
            return IntentAnalysisResult.model_validate(
                acquisition.replay_response
            )

        try:
            result = await self._service.analyze_intent(request)
            await self._turns.complete(
                turn_id=request.turn_id,
                response_data=result.model_dump(mode="json"),
            )
            return result
        except Exception as exc:
            await self._record_turn_failure(request.turn_id, exc)
            raise

    async def get_history(
        self,
        thread_id: UUID,
    ) -> ConversationHistoryData:
        await self._authorize_existing(thread_id)
        return await self._service.get_history(thread_id)

    async def list_threads(self) -> list[ConversationThreadSummaryData]:
        owned_threads = await self._ownership.list_threads_for_user(
            self._user_id
        )
        summaries: list[ConversationThreadSummaryData] = []

        for thread_id, created_at in owned_threads:
            summary = await self._service.get_thread_summary(
                thread_id,
                created_at=created_at,
            )
            if summary is not None:
                summaries.append(summary)

        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    async def resume(
        self,
        request: ResumeConversationRequest,
    ) -> ConversationResponseData:
        await self._authorize_existing(request.thread_id)
        acquisition = await self._turns.begin(
            turn_id=request.turn_id,
            thread_id=request.thread_id,
            user_id=self._user_id,
            operation="resume",
            payload_hash=self._payload_hash(request.model_dump(mode="json")),
        )
        if acquisition.is_replay:
            return ConversationResponseData.model_validate(
                acquisition.replay_response
            )

        try:
            result = await self._service.resume(request)
            await self._turns.complete(
                turn_id=request.turn_id,
                response_data=result.model_dump(mode="json"),
            )
            return result
        except Exception as exc:
            await self._record_turn_failure(request.turn_id, exc)
            raise

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

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def _record_turn_failure(self, turn_id: UUID, exc: Exception) -> None:
        try:
            await self._turns.fail(
                turn_id=turn_id,
                error_code=type(exc).__name__,
            )
        except Exception:
            logger.exception(
                "Conversation turn failure status could not be recorded",
                extra={"turn_id": str(turn_id)},
            )
