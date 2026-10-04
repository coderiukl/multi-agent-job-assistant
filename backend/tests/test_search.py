from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.job import NormalizedJob
from app.schemas.job_search import JobSearchPlan, JobSearchRequest
from app.services.job_search import HybridJobSearchService


@pytest.fixture
def search():
    job = NormalizedJob(
        job_id="a" * 64, content_hash="b" * 64, title="Python developer",
        company="Test Company", description="Python SQL", source="test",
        source_job_id="1", source_url="https://example.com/jobs/1",
        posted_at=datetime.now(UTC), skills=["Python"],
    )
    repository = SimpleNamespace(
        search_candidates=AsyncMock(return_value=[job]), get_by_ids=AsyncMock(return_value=[]),
    )
    vector = SimpleNamespace(search_jobs=AsyncMock(return_value=[]))
    service = HybridJobSearchService(
        agent=SimpleNamespace(analyze=AsyncMock(return_value=JobSearchPlan(
            original_query="Python", semantic_query="Python", keywords=["Python"],
        ))), repository=repository, vector_index=vector,
    )
    return SimpleNamespace(service=service, repository=repository, vector=vector)


async def test_vector_failure_falls_back_to_postgres(search):
    search.vector.search_jobs.side_effect = RuntimeError("Vector unavailable")
    result = await search.service.search(JobSearchRequest(query="Python"))
    assert result.strategy.value == "postgres"
    assert result.total == 1
    assert result.items[0].job.title == "Python developer"


async def test_database_failure_is_not_hidden(search):
    search.repository.search_candidates.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError, match="Database unavailable"):
        await search.service.search(JobSearchRequest(query="Python"))


async def test_pagination_keeps_total(search):
    result = await search.service.search(JobSearchRequest(query="Python", page=2, page_size=1))
    assert result.total == 1
    assert result.items == []
