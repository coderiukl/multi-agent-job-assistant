from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundException, StorageException
from app.schemas.conversations_intent import ConversationRequest
from app.schemas.human_review import ResumeConversationRequest
from app.services.authorized_conversation import AuthorizedConversationService
from app.services.authorized_cv import AuthorizedCVProcessingService


@pytest.fixture
def context():
    user_id, thread_id = uuid4(), uuid4()
    ownership = SimpleNamespace(**{
        name: AsyncMock() for name in [
            "get_thread_owner", "require_thread", "require_cv", "claim_thread",
        ]
    })
    ownership.get_thread_owner.return_value = user_id
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={"cv_id": "cv-a"})))
    service = SimpleNamespace(**{
        name: AsyncMock(return_value="ok") for name in [
            "process", "get_history", "delete_history", "resume", "analyze_intent",
        ]
    })
    authorized = AuthorizedConversationService(
        user_id=user_id, service=service, graph=graph, ownership=ownership,
    )
    return SimpleNamespace(
        user_id=user_id, thread_id=thread_id, ownership=ownership,
        graph=graph, service=service, authorized=authorized,
    )


@pytest.mark.parametrize("method", ["process", "analyze_intent"])
async def test_cannot_send_to_foreign_thread(context, method):
    context.ownership.get_thread_owner.return_value = uuid4()
    with pytest.raises(ResourceNotFoundException):
        await getattr(context.authorized, method)(ConversationRequest(
            thread_id=context.thread_id, message="Hello",
        ))
    getattr(context.service, method).assert_not_awaited()
    context.graph.aget_state.assert_not_awaited()


@pytest.mark.parametrize("method", ["get_history", "delete_history", "resume"])
async def test_existing_thread_requires_owner(context, method):
    context.ownership.require_thread.side_effect = ResourceNotFoundException(
        resource="Conversation", identifier=str(context.thread_id)
    )
    argument = context.thread_id
    if method == "resume":
        argument = ResumeConversationRequest(
            thread_id=context.thread_id, decision={"action": "approve"}
        )
    with pytest.raises(ResourceNotFoundException):
        await getattr(context.authorized, method)(argument)
    getattr(context.service, method).assert_not_awaited()


@pytest.mark.parametrize("source", ["request", "checkpoint"])
async def test_foreign_cv_rejected(context, source):
    context.graph.aget_state.return_value.values = {"cv_id": "cv-other"} if source == "checkpoint" else {"messages": []}
    context.ownership.require_cv.side_effect = ResourceNotFoundException(
        resource="CV", identifier="cv-other"
    )
    with pytest.raises(ResourceNotFoundException):
        await context.authorized.process(ConversationRequest(
            thread_id=context.thread_id, message="Analyze CV",
            cv_id="cv-other" if source == "request" else None,
        ))
    context.service.process.assert_not_awaited()


async def test_legacy_checkpoint_cannot_be_claimed(context):
    context.ownership.get_thread_owner.return_value = None
    with pytest.raises(ResourceNotFoundException):
        await context.authorized.process(ConversationRequest(
            thread_id=context.thread_id, message="Hello"
        ))
    context.ownership.claim_thread.assert_not_awaited()


async def test_new_thread_claimed_after_cv_check(context):
    context.ownership.get_thread_owner.return_value = None
    context.graph.aget_state.return_value.values = {}
    assert await context.authorized.process(ConversationRequest(
        thread_id=context.thread_id, message="Hello", cv_id="cv-a"
    )) == "ok"
    context.ownership.require_cv.assert_awaited_once_with(cv_id="cv-a", user_id=context.user_id)
    context.ownership.claim_thread.assert_awaited_once_with(thread_id=context.thread_id, user_id=context.user_id)


async def test_cv_ownership_failure_rolls_back_files():
    stored = SimpleNamespace(file_id="cv-a")
    result = SimpleNamespace(ingestion=SimpleNamespace(stored_file=stored))
    processing = SimpleNamespace(process=AsyncMock(return_value=result))
    ownership = SimpleNamespace(add_cv=AsyncMock(side_effect=StorageException()))
    repository, storage = SimpleNamespace(delete=AsyncMock()), SimpleNamespace(delete=AsyncMock())
    service = AuthorizedCVProcessingService(
        user_id=uuid4(), processing=processing, ownership=ownership,
        cv_repository=repository, storage=storage,
    )
    with pytest.raises(StorageException):
        await service.process(object())
    repository.delete.assert_awaited_once_with("cv-a")
    storage.delete.assert_awaited_once_with(stored)
