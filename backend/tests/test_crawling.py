from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.normalizers.job import JobNormalizer
from app.repositories.job import LocalJsonlJobRepository
from app.schemas.job import CrawlPage, JobCandidate, RawJob
from app.services.job_crawling import JobCrawlingService


@pytest.fixture
def candidate():
    return JobCandidate(
        title="Python developer", company="Test", description="Python SQL",
        source="test", source_job_id="1", source_url="https://example.com/jobs/1",
    )


async def test_jsonl_upsert_detects_unchanged_and_changed_content(tmp_path, candidate):
    repository = LocalJsonlJobRepository(tmp_path)
    normalizer = JobNormalizer()
    original = normalizer.normalize(candidate)
    assert (await repository.upsert_many([original])).inserted == 1
    assert (await repository.upsert_many([original])).unchanged == 1
    changed = normalizer.normalize(candidate.model_copy(update={"description": "Python FastAPI"}))
    assert changed.job_id == original.job_id
    assert changed.content_hash != original.content_hash
    assert (await repository.upsert_many([changed])).updated == 1


async def test_bad_source_record_does_not_drop_valid_records(tmp_path, candidate):
    records = [RawJob(source="test", source_job_id=str(i), source_url="https://example.com/jobs/1", payload={}) for i in range(2)]
    source = SimpleNamespace(
        source_name="test", fetch_page=AsyncMock(return_value=CrawlPage(items=records)),
        map_to_candidate=Mock(side_effect=[candidate, ValueError("Invalid source record")]),
    )
    service = JobCrawlingService(
        source=source, normalizer=JobNormalizer(), repository=LocalJsonlJobRepository(tmp_path),
    )
    result = await service.crawl(batch_id="test-batch")
    assert result.fetched_count == 2
    assert result.normalized_count == 1
    assert result.failed_count == 1
    assert result.inserted_count == 1
