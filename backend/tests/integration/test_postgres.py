"""PostgreSQL integration tests (Phase 4) – run only against a disposable
database given by TEST_DATABASE_URL (migrated with ``alembic upgrade head``).

Safety: the fixture refuses to run unless the database name contains "test"
or "qa", and every test starts from TRUNCATEd tables of that database only.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppException, ResourceNotFoundException, StorageException
from app.repositories.conversation_turn import ConversationTurnRepository
from app.repositories.cv_task import CVTaskRepository
from app.repositories.ownership import OwnershipRepository
from app.repositories.postgres_job import PostgresNormalizedJobRepository
from app.repositories.postgres_job_search import PostgresJobSearchRepository
from app.repositories.user import UserRepository
from app.schemas.job import SeniorityLevel
from app.schemas.job_search import JobSearchFilters, JobSearchPlan
from app.services.storage.models import StoredFile
from tests.conftest import make_job

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def event_loop_policy():
    # psycopg's async driver (LangGraph AsyncPostgresSaver) cannot run on the
    # Windows Proactor loop; production runs on Linux where this is a no-op.
    import sys

    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TABLES = ("conversation_turns", "conversation_ownerships", "cv_processing_tasks",
          "cv_ownerships", "users", "jobs")


@pytest.fixture
async def sessions():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    database_name = DATABASE_URL.rsplit("/", 1)[-1]
    assert "test" in database_name or "qa" in database_name, "refusing non-test database"
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def new_user(sessions, email=None):
    return await UserRepository(sessions).create(
        email=email or f"{uuid4().hex[:8]}@example.com", password_hash="x")


def plan(keywords=(), **filters) -> JobSearchPlan:
    return JobSearchPlan(original_query="q", semantic_query="q", keywords=list(keywords),
                         filters=JobSearchFilters(**filters))


# --------------------------------------------------------------------------
# Users / ownership
# --------------------------------------------------------------------------
async def test_db_01_user_unique_email(sessions):
    """TC-DB-01: duplicate e-mail -> 409 EMAIL_ALREADY_REGISTERED from the constraint."""
    await new_user(sessions, "dup@example.com")
    with pytest.raises(AppException) as error:
        await new_user(sessions, "dup@example.com")
    assert error.value.code == "EMAIL_ALREADY_REGISTERED"


async def test_db_02_email_must_be_normalised(sessions):
    """TC-DB-02: the DB CHECK constraint rejects non-normalised e-mails."""
    with pytest.raises(StorageException):
        await new_user(sessions, "Upper@Example.com")


async def test_db_03_concurrent_thread_claim_has_one_owner(sessions):
    """TC-DB-03: two users racing to claim the same thread -> exactly one wins."""
    alice, bob = await new_user(sessions), await new_user(sessions)
    ownership = OwnershipRepository(sessions)
    thread_id = uuid4()
    results = await asyncio.gather(
        ownership.claim_thread(thread_id=thread_id, user_id=alice.user_id),
        ownership.claim_thread(thread_id=thread_id, user_id=bob.user_id),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ResourceNotFoundException) for r in results) == 1
    assert await ownership.get_thread_owner(thread_id) in {alice.user_id, bob.user_id}


async def test_db_04_user_with_data_cannot_be_deleted(sessions):
    """TC-DB-04: FK ON DELETE RESTRICT protects users that own threads."""
    alice = await new_user(sessions)
    await OwnershipRepository(sessions).claim_thread(thread_id=uuid4(), user_id=alice.user_id)
    with pytest.raises(IntegrityError):
        async with sessions() as session, session.begin():
            await session.execute(text("DELETE FROM users WHERE user_id = :u"),
                                  {"u": alice.user_id})


# --------------------------------------------------------------------------
# Conversation turns (idempotency + single active turn per thread)
# --------------------------------------------------------------------------
async def _thread(sessions):
    user = await new_user(sessions)
    thread_id = uuid4()
    await OwnershipRepository(sessions).claim_thread(thread_id=thread_id, user_id=user.user_id)
    return user, thread_id


async def test_db_05_turn_replay_and_reuse(sessions):
    """TC-DB-05: completed turn replays; same turn_id with another payload -> 409."""
    user, thread_id = await _thread(sessions)
    turns = ConversationTurnRepository(sessions)
    turn_id = uuid4()
    args = dict(turn_id=turn_id, thread_id=thread_id, user_id=user.user_id, operation="message")
    assert not (await turns.begin(**args, payload_hash="a" * 64)).is_replay
    await turns.complete(turn_id=turn_id, response_data={"ok": True})
    replay = await turns.begin(**args, payload_hash="a" * 64)
    assert replay.replay_response == {"ok": True}
    with pytest.raises(AppException) as error:
        await turns.begin(**args, payload_hash="b" * 64)
    assert error.value.code == "TURN_ID_REUSED"


async def test_db_06_only_one_active_turn_per_thread(sessions):
    """TC-DB-06: 5 concurrent turns on one thread -> exactly 1 acquires the lease."""
    user, thread_id = await _thread(sessions)
    turns = ConversationTurnRepository(sessions)
    results = await asyncio.gather(*[
        turns.begin(turn_id=uuid4(), thread_id=thread_id, user_id=user.user_id,
                    operation="message", payload_hash="c" * 64) for _ in range(5)
    ], return_exceptions=True)
    busy = [r for r in results if isinstance(r, AppException)]
    assert len(busy) == 4 and {e.code for e in busy} == {"CONVERSATION_TURN_IN_PROGRESS"}


async def test_db_07_expired_turn_lease_is_released(sessions):
    """TC-DB-07: a crashed turn (expired lease) no longer blocks the thread."""
    user, thread_id = await _thread(sessions)
    turns = ConversationTurnRepository(sessions)
    first = uuid4()
    await turns.begin(turn_id=first, thread_id=thread_id, user_id=user.user_id,
                      operation="message", payload_hash="d" * 64)
    async with sessions() as session, session.begin():
        await session.execute(text("UPDATE conversation_turns SET lease_expires_at = now() - "
                                   "interval '1 hour' WHERE turn_id = :t"), {"t": first})
    acquired = await turns.begin(turn_id=uuid4(), thread_id=thread_id, user_id=user.user_id,
                                 operation="message", payload_hash="d" * 64)
    assert not acquired.is_replay


async def test_db_08_deleting_thread_ownership_cascades_turns(sessions):
    """TC-DB-08: FK ON DELETE CASCADE from ownership to turns."""
    user, thread_id = await _thread(sessions)
    await ConversationTurnRepository(sessions).begin(
        turn_id=uuid4(), thread_id=thread_id, user_id=user.user_id, operation="message",
        payload_hash="e" * 64)
    async with sessions() as session, session.begin():
        await session.execute(text("DELETE FROM conversation_ownerships WHERE thread_id=:t"),
                              {"t": thread_id})
        remaining = await session.scalar(text("SELECT count(*) FROM conversation_turns"))
    assert remaining == 0


# --------------------------------------------------------------------------
# Jobs: upsert + filtered retrieval
# --------------------------------------------------------------------------
async def test_db_09_job_upsert_insert_unchanged_update(sessions):
    """TC-DB-09: insert -> unchanged -> updated, intra-batch duplicates collapsed."""
    repo = PostgresNormalizedJobRepository(sessions)
    job = make_job(1)
    first = await repo.upsert_many([job, job])
    second = await repo.upsert_many([job])
    changed = make_job(1, description="New description")
    third = await repo.upsert_many([changed])
    assert (first.inserted, second.unchanged, third.updated) == (1, 1, 1)
    async with sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM jobs")) == 1


async def test_db_10_salary_constraints_enforced_by_db(sessions):
    """TC-DB-10: salary without currency or min > max is rejected by CHECKs."""
    for sql in ("salary_min = 10", "salary_min = 10, salary_max = 5, salary_currency = 'VND'"):
        await PostgresNormalizedJobRepository(sessions).upsert_many([make_job(99)])
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(text(f"UPDATE jobs SET {sql}"))


async def _seed(sessions):
    jobs = [
        make_job(1, title="Python Backend Intern", location="TP.HCM", skills=["Python"],
                 salary_min=Decimal(5_000_000), salary_max=Decimal(8_000_000),
                 salary_currency="VND", salary_period="monthly"),
        make_job(2, title="Java Developer", location="Hà Nội", skills=["Java"],
                 seniority=SeniorityLevel.SENIOR),
        make_job(3, title="Frontend Developer", location="Ho Chi Minh City",
                 skills=["JavaScript"], seniority=SeniorityLevel.UNKNOWN),
        make_job(4, title="Expired Python job", location="Đà Nẵng",
                 expires_at=datetime.now(UTC) - timedelta(days=1)),
    ]
    await PostgresNormalizedJobRepository(sessions).upsert_many(jobs)
    return jobs


async def test_db_11_location_alias_filter(sessions):
    """TC-DB-11: 'Hồ Chí Minh' matches 'TP.HCM' and 'Ho Chi Minh City'."""
    jobs = await _seed(sessions)
    found = await PostgresJobSearchRepository(sessions).search_candidates(
        plan=plan(locations=["Hồ Chí Minh"]), limit=50)
    assert {j.job_id for j in found} == {jobs[0].job_id, jobs[2].job_id}


async def test_db_12_expired_jobs_excluded_by_default(sessions):
    """TC-DB-12: expired jobs hidden unless include_expired."""
    jobs = await _seed(sessions)
    repo = PostgresJobSearchRepository(sessions)
    default = await repo.search_candidates(plan=plan(), limit=50)
    everything = await repo.search_candidates(plan=plan(include_expired=True), limit=50)
    assert jobs[3].job_id not in {j.job_id for j in default}
    assert len(everything) == 4


async def test_db_13_salary_and_seniority_filters(sessions):
    """TC-DB-13: salary overlap filter; seniority filter also keeps 'unknown'."""
    jobs = await _seed(sessions)
    repo = PostgresJobSearchRepository(sessions)
    salary = await repo.search_candidates(plan=plan(salary_min=7_000_000, salary_currency="VND",
                                                    salary_period="monthly"), limit=50)
    senior = await repo.search_candidates(plan=plan(seniority_levels=["senior"]), limit=50)
    assert [j.job_id for j in salary] == [jobs[0].job_id]
    assert {j.job_id for j in senior} == {jobs[1].job_id, jobs[2].job_id}


async def test_db_14_skill_filter_is_exact(sessions):
    """TC-DB-14 (BUG-020 fixed): skills=['Java'] must not return a
    JavaScript-only job; matching is case-insensitive like Qdrant skill_keys."""
    jobs = await _seed(sessions)
    repo = PostgresJobSearchRepository(sessions)
    found = await repo.search_candidates(plan=plan(skills=["Java"]), limit=50)
    assert {j.job_id for j in found} == {jobs[1].job_id}
    either = await repo.search_candidates(plan=plan(skills=["javascript", "PYTHON"]), limit=50)
    assert {j.job_id for j in either} == {jobs[0].job_id, jobs[2].job_id}


async def test_db_14b_skill_keys_match_python_normalisation(sessions):
    """TC-DB-14b: SQL skill normalisation equals normalize_deduplication_text
    (accents, punctuation, case) – the rule Qdrant uses for skill_keys."""
    from app.utils.job_deduplication import normalize_deduplication_text

    job = make_job(9, title="Polyglot", skills=["Node.js", "C#", "Tiếng Anh", "ASP.NET Core"])
    await PostgresNormalizedJobRepository(sessions).upsert_many([job])
    repo = PostgresJobSearchRepository(sessions)
    for skill in ("node js", "NODE.JS", "c", "tieng anh", "Tiếng  Anh", "asp net core"):
        found = await repo.search_candidates(plan=plan(skills=[skill]), limit=10)
        expected = normalize_deduplication_text(skill) in {
            normalize_deduplication_text(s) for s in job.skills}
        assert bool(found) is expected, skill
    assert await repo.search_candidates(plan=plan(skills=["Node"]), limit=10) == []


async def test_db_14c_relevance_sort_prefers_keyword_matches(sessions):
    """TC-DB-14c (BUG-031): with sort=relevance the candidate window is ordered
    by keyword relevance (title/skills > description), not just by date."""
    older_title = make_job(20, title="Rust Engineer", company="A", skills=["Rust"],
                           description="Systems work", posted_days_ago=20)
    newer_desc = make_job(21, title="Backend Engineer", company="B", skills=["Go"],
                          description="Some Rust tooling", posted_days_ago=1)
    await PostgresNormalizedJobRepository(sessions).upsert_many([older_title, newer_desc])
    repo = PostgresJobSearchRepository(sessions)
    relevance = await repo.search_candidates(plan=plan(keywords=["Rust"]), limit=1)
    assert [j.job_id for j in relevance] == [older_title.job_id]
    newest = await repo.search_candidates(
        plan=JobSearchPlan(original_query="q", semantic_query="q", keywords=["Rust"],
                           sort="newest"), limit=1)
    assert [j.job_id for j in newest] == [newer_desc.job_id]


async def test_db_15_sql_injection_and_wildcards_are_literal(sessions):
    """TC-DB-15: quotes/SQL and LIKE wildcards in keywords are treated literally."""
    await _seed(sessions)
    repo = PostgresJobSearchRepository(sessions)
    for keyword in ("'; DROP TABLE jobs; --", "%", "_", "\\"):
        assert await repo.search_candidates(plan=plan(keywords=[keyword]), limit=50) == []
    async with sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM jobs")) == 4


async def test_db_16_get_by_ids_keeps_semantic_order_and_filters(sessions):
    """TC-DB-16: Qdrant ids are re-loaded from PostgreSQL in Qdrant order, with
    filters re-applied and unknown/stale ids dropped (PG <-> Qdrant mapping)."""
    jobs = await _seed(sessions)
    ids = [jobs[2].job_id, "f" * 64, jobs[0].job_id, jobs[3].job_id]
    found = await PostgresJobSearchRepository(sessions).get_by_ids(job_ids=ids, plan=plan())
    assert [j.job_id for j in found] == [jobs[2].job_id, jobs[0].job_id]


# --------------------------------------------------------------------------
# CV processing queue
# --------------------------------------------------------------------------
async def _backdate_tasks(sessions):
    """available_at uses the DB clock while claim_next() compares it with the
    app clock; back-date rows so tests do not depend on host/VM clock skew."""
    async with sessions() as session, session.begin():
        await session.execute(text("UPDATE cv_processing_tasks SET available_at = "
                                   "now() - interval '1 minute'"))


async def _enqueue(sessions, user):
    file_id = uuid4().hex
    return await CVTaskRepository(sessions).enqueue(
        user_id=user.user_id, retention_expires_at=datetime.now(UTC),
        file=StoredFile(file_id=file_id, path=Path(f"{file_id}.pdf"),
                        original_filename="cv.pdf", content_type="application/pdf",
                        size_bytes=10))


async def test_db_17_concurrent_workers_never_share_a_task(sessions):
    """TC-DB-17: FOR UPDATE SKIP LOCKED – 3 workers, 2 tasks -> 2 claims, 1 None."""
    user = await new_user(sessions)
    tasks = CVTaskRepository(sessions)
    for _ in range(2):
        await _enqueue(sessions, user)
    await _backdate_tasks(sessions)
    claims = await asyncio.gather(*[
        tasks.claim_next(worker_id=f"w{i}", lease_seconds=60, max_attempts=2) for i in range(3)
    ])
    claimed = [c for c in claims if c is not None]
    assert len(claimed) == 2 and len({c.task_id for c in claimed}) == 2


async def test_db_18_failed_task_retry_and_max_attempts(sessions):
    """TC-DB-18: retryable failure re-queues; attempts are capped."""
    user = await new_user(sessions)
    tasks = CVTaskRepository(sessions)
    await _enqueue(sessions, user)
    await _backdate_tasks(sessions)
    first = await tasks.claim_next(worker_id="w", lease_seconds=60, max_attempts=2)
    await tasks.mark_failed(task_id=first.task_id, worker_id="w", error_code="X",
                            error_message="boom", retry=True, retry_delay_seconds=0)
    await _backdate_tasks(sessions)
    second = await tasks.claim_next(worker_id="w", lease_seconds=60, max_attempts=2)
    assert second.attempt_count == 2
    await tasks.mark_failed(task_id=second.task_id, worker_id="w", error_code="X",
                            error_message="boom", retry=True, retry_delay_seconds=0)
    await _backdate_tasks(sessions)
    assert await tasks.claim_next(worker_id="w", lease_seconds=60, max_attempts=2) is None


@pytest.mark.parametrize("skew_seconds", [-2, 2])
async def test_db_20_queue_uses_one_clock(sessions, monkeypatch, skew_seconds):
    """TC-DB-20 (BUG-021 fixed): a freshly enqueued task (available_at = DB
    now()) is claimable even when the worker's clock is 2 s behind/ahead of
    the DB, and its lease is computed on the DB clock."""
    import app.repositories.cv_task as module

    user = await new_user(sessions)
    task = await _enqueue(sessions, user)

    class SkewedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=skew_seconds)

    monkeypatch.setattr(module, "datetime", SkewedDatetime)
    claimed = await CVTaskRepository(sessions).claim_next(
        worker_id="w", lease_seconds=60, max_attempts=2)
    assert claimed is not None and claimed.task_id == task.task_id
    async with sessions() as session:
        lease_left = await session.scalar(text(
            "SELECT extract(epoch FROM lease_expires_at - now()) "
            "FROM cv_processing_tasks WHERE task_id = :t"), {"t": task.task_id})
    assert 55 <= float(lease_left) <= 60


async def test_db_07b_turn_lease_is_short_and_renewable(sessions):
    """TC-DB-07b (BUG-029 fixed): a turn lease lasts minutes, not an hour, and
    the heartbeat renewal extends it only while the turn is processing."""
    from app.repositories.conversation_turn import TURN_LEASE_SECONDS

    user = await new_user(sessions)
    thread_id, turn_id = uuid4(), uuid4()
    await OwnershipRepository(sessions).claim_thread(thread_id=thread_id, user_id=user.user_id)
    turns = ConversationTurnRepository(sessions)
    await turns.begin(turn_id=turn_id, thread_id=thread_id, user_id=user.user_id,
                      operation="message", payload_hash="h")

    async def lease_left():
        async with sessions() as session:
            return float(await session.scalar(text(
                "SELECT extract(epoch FROM lease_expires_at - now()) "
                "FROM conversation_turns WHERE turn_id = :t"), {"t": turn_id}))

    assert TURN_LEASE_SECONDS <= 300
    assert TURN_LEASE_SECONDS - 5 <= await lease_left() <= TURN_LEASE_SECONDS
    async with sessions() as session, session.begin():
        await session.execute(text("UPDATE conversation_turns SET lease_expires_at = "
                                   "now() + interval '5 seconds' WHERE turn_id = :t"),
                              {"t": turn_id})
    assert await turns.renew_lease(turn_id=turn_id) is True
    assert await lease_left() > 60
    await turns.complete(turn_id=turn_id, response_data={"ok": True})
    assert await turns.renew_lease(turn_id=turn_id) is False


# --------------------------------------------------------------------------
# LangGraph PostgreSQL checkpointer
# --------------------------------------------------------------------------
async def test_db_19_checkpoint_survives_restart_and_resumes_hitl(sessions):
    """TC-DB-19: state + pending human review persist in PostgreSQL; a fresh
    graph instance (simulated restart) reads history and resumes the review."""
    from app.core.config import Settings
    from app.graphs.conversation import build_conversation_graph
    from app.memory.conversation import ConversationMemory
    from app.schemas.conversations_intent import ConversationIntent as I
    from app.services.conversation import ConversationService
    from tests.conftest import GraphHarness, intent

    memory = ConversationMemory(Settings(conversation_memory_backend="postgres",
                                         job_database_url=DATABASE_URL))
    await memory.start()
    try:
        harness = GraphHarness()
        harness.analyzer.on("cover letter", intent(I.COVER_LETTER))
        graph = build_conversation_graph(_nodes(harness), checkpointer=memory.checkpointer)
        harness.service = ConversationService(graph=graph)
        harness.graph = graph
        cv_id = harness.add_cv()
        first = await harness.send("Viết cover letter", cv_id=cv_id, job_description="Python dev")
        assert first.human_review is not None

        restarted = ConversationService(graph=build_conversation_graph(
            _nodes(harness), checkpointer=memory.checkpointer))
        history = await restarted.get_history(harness.thread_id)
        assert history.pending_human_review.review_id == first.human_review.review_id
        harness.service = restarted
        second = await harness.resume(first.human_review.review_id)
        assert second.human_review.review_type == "cover_letter_draft"
        await restarted.delete_history(harness.thread_id)
        assert (await restarted.get_history(harness.thread_id)).messages == []
    finally:
        await memory.close()


def _nodes(harness):
    from app.graphs.conversation import ConversationNodes

    return ConversationNodes(
        analyzer=harness.analyzer, cv_repository=harness.cv_repository,
        cv_analysis_service=harness.cv_analysis, career_advice_service=harness.career_advice,
        cover_letter_service=harness.cover_letter, job_search_service=harness.job_search,
        job_matching_service=harness.job_matching)
