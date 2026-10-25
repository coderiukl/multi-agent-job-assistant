from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.database import create_job_database_engine, create_job_session_factory
from app.memory import ConversationMemory
from app.repositories.conversation_turn import ConversationTurnRepository
from app.repositories.cv import LocalJsonCVRepository
from app.repositories.ownership import OwnershipRepository
from app.services.cv_lifecycle import CVDataLifecycleService
from app.services.storage import LocalStorageService


async def purge_expired_cvs(
    *,
    limit: int,
    execute: bool,
) -> dict[str, Any]:
    settings = get_settings()
    engine = create_job_database_engine(settings)
    session_factory = create_job_session_factory(engine)
    ownership = OwnershipRepository(session_factory)
    candidates = await ownership.list_expired_cvs(
        before=datetime.now(UTC),
        limit=limit,
    )

    result: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "candidate_count": len(candidates),
        "deleted_count": 0,
        "candidates": [
            {
                "cv_id": cv_id,
                "user_id": str(user_id),
                "retention_expires_at": expires_at.isoformat(),
            }
            for cv_id, user_id, expires_at in candidates
        ],
    }

    if not execute or not candidates:
        await engine.dispose()
        return result

    memory = ConversationMemory(settings)
    await memory.start()
    try:
        profiles = LocalJsonCVRepository(settings)
        storage = LocalStorageService(settings)
        turns = ConversationTurnRepository(session_factory)

        for cv_id, user_id, _expires_at in candidates:
            lifecycle = CVDataLifecycleService(
                user_id=user_id,
                ownership=ownership,
                turns=turns,
                profiles=profiles,
                storage=storage,
                checkpointer=memory.checkpointer,
            )
            await lifecycle.delete(cv_id)
            result["deleted_count"] += 1
    finally:
        await memory.close()
        await engine.dispose()

    return result
