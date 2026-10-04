import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppException, ResourceNotFoundException
from app.repositories.ownership import OwnershipRepository
from app.repositories.user import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url or not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
    env = dict(os.environ, JOB_DATABASE_URL=url)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    return url


@pytest_asyncio.fixture
async def repositories(database_url):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE cv_ownerships, conversation_ownerships, users CASCADE"))
        yield UserRepository(factory), OwnershipRepository(factory)
    finally:
        await engine.dispose()


async def test_users_persist_and_duplicate_email_is_conflict(repositories):
    users, _ = repositories
    created = await users.create(email="alice@example.com", password_hash="test-hash")
    assert (await users.get_by_id(created.user_id)).email == "alice@example.com"
    with pytest.raises(AppException) as exc:
        await users.create(email="alice@example.com", password_hash="another-hash")
    assert exc.value.status_code == 409


async def test_cv_and_thread_ownership_isolated(repositories):
    users, ownership = repositories
    alice = await users.create(email="alice@example.com", password_hash="test-hash")
    bob = await users.create(email="bob@example.com", password_hash="test-hash")
    thread = uuid4()
    await ownership.add_cv(cv_id="cv-a", user_id=alice.user_id)
    await ownership.claim_thread(thread_id=thread, user_id=alice.user_id)
    await ownership.require_cv(cv_id="cv-a", user_id=alice.user_id)
    for method, kwargs in [
        (ownership.require_cv, {"cv_id": "cv-a"}),
        (ownership.require_thread, {"thread_id": thread}),
        (ownership.claim_thread, {"thread_id": thread}),
    ]:
        with pytest.raises(ResourceNotFoundException):
            await method(user_id=bob.user_id, **kwargs)
    assert await ownership.list_threads_for_user(bob.user_id) == []
    assert (await ownership.list_threads_for_user(alice.user_id))[0][0] == thread


async def test_concurrent_claim_has_one_owner(repositories):
    users, ownership = repositories
    alice = await users.create(email="alice@example.com", password_hash="test-hash")
    bob = await users.create(email="bob@example.com", password_hash="test-hash")
    thread = uuid4()
    outcomes = await asyncio.gather(
        ownership.claim_thread(thread_id=thread, user_id=alice.user_id),
        ownership.claim_thread(thread_id=thread, user_id=bob.user_id),
        return_exceptions=True,
    )
    assert sum(item is None for item in outcomes) == 1
    assert sum(isinstance(item, ResourceNotFoundException) for item in outcomes) == 1
    assert await ownership.get_thread_owner(thread) in {alice.user_id, bob.user_id}


async def test_checkpoint_survives_new_connection(database_url, results):
    from langgraph.graph import END, START, StateGraph

    from app.core.config import Settings
    from app.graphs.conversation.state import ConversationState
    from app.memory.conversation import ConversationMemory

    settings = Settings(
        _env_file=None, job_database_url=database_url,
        conversation_memory_backend="postgres",
    )
    config = {"configurable": {"thread_id": str(uuid4())}}
    memory = ConversationMemory(settings)
    await memory.start()
    builder = StateGraph(ConversationState)
    builder.add_node("save", lambda state: {"job_search_result": results["job_search"]})
    builder.add_edge(START, "save")
    builder.add_edge("save", END)
    try:
        graph = builder.compile(checkpointer=memory.checkpointer)
        await graph.ainvoke({"message": "Python"}, config=config)
    finally:
        await memory.close()
    restored = ConversationMemory(settings)
    await restored.start()
    try:
        graph = builder.compile(checkpointer=restored.checkpointer)
        snapshot = await graph.aget_state(config)
        assert snapshot.values["job_search_result"].query == "Python"
    finally:
        await restored.close()
