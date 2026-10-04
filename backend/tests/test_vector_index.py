from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient

from app.schemas.job import NormalizedJob
from app.vectorstores.qdrant_job_index import QdrantJobVectorIndex


async def test_qdrant_local_index_search_and_content_hash(settings):
    job = NormalizedJob(
        job_id="a" * 64, content_hash="b" * 64, title="Python developer",
        company="Test", description="Python SQL", source="test", source_job_id="1",
        source_url="https://example.com/jobs/1",
    )
    vector = [1.0] + [0.0] * 1023
    embeddings = SimpleNamespace(
        aembed_documents=AsyncMock(return_value=[vector]),
        aembed_query=AsyncMock(return_value=vector),
    )
    client = AsyncQdrantClient(location=":memory:")
    try:
        index = QdrantJobVectorIndex(client=client, embeddings=embeddings, settings=settings)
        assert len(await index.get_jobs_requiring_index([job])) == 1
        summary = await index.index_jobs([job])
        assert summary.indexed == 1
        assert await index.get_jobs_requiring_index([job]) == []
        hits = await index.search_jobs(query="Python", limit=5)
        assert hits[0].job_id == job.job_id
        assert hits[0].score == pytest.approx(1.0)
        changed = job.model_copy(update={"content_hash": "c" * 64})
        assert len(await index.get_jobs_requiring_index([changed])) == 1
    finally:
        await client.close()
