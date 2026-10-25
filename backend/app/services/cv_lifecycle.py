from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from app.repositories.conversation_turn import ConversationTurnRepository
    from app.repositories.cv import CVRepository
    from app.repositories.ownership import OwnershipRepository
    from app.services.storage import StorageService


class CVDataLifecycleService:
    """Coordinate deletion of a CV and data derived from it."""

    def __init__(
        self,
        *,
        user_id: UUID,
        ownership: OwnershipRepository,
        turns: ConversationTurnRepository,
        profiles: CVRepository,
        storage: StorageService,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self._user_id = user_id
        self._ownership = ownership
        self._turns = turns
        self._profiles = profiles
        self._storage = storage
        self._checkpointer = checkpointer

    async def delete(self, cv_id: str) -> list[UUID]:
        await self._ownership.require_cv(
            cv_id=cv_id,
            user_id=self._user_id,
        )

        affected_threads = await self._find_linked_threads(cv_id)

        # Delete derived conversation state before removing the ownership row.
        # If this step fails, the ownership record remains so the operation can
        # be retried instead of leaving inaccessible personal data behind.
        for thread_id in affected_threads:
            await self._turns.delete_for_thread(thread_id)
            await self._checkpointer.adelete_thread(str(thread_id))

        cleanup_results = await asyncio.gather(
            self._profiles.delete(cv_id),
            self._storage.delete_by_id(cv_id),
            return_exceptions=True,
        )
        failures = [
            failure
            for failure in cleanup_results
            if isinstance(failure, BaseException)
        ]
        if failures:
            raise failures[0]

        await self._ownership.delete_cv(
            cv_id=cv_id,
            user_id=self._user_id,
        )
        return affected_threads

    async def _find_linked_threads(self, cv_id: str) -> list[UUID]:
        linked: list[UUID] = []
        for thread_id, _created_at in await self._ownership.list_threads_for_user(
            self._user_id
        ):
            checkpoint_tuple = await self._checkpointer.aget_tuple(
                {"configurable": {"thread_id": str(thread_id)}}
            )
            if checkpoint_tuple is None:
                continue

            values = checkpoint_tuple.checkpoint.get("channel_values", {})
            if values.get("cv_id") == cv_id:
                linked.append(thread_id)

        return linked
