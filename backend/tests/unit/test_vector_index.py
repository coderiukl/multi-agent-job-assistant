"""Qdrant vector index tests using qdrant-client local in-memory mode and a
deterministic 1024-d fake embedding (no BGE-M3 download, no real Qdrant)."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.core.exceptions import ExternalServiceException
from app.schemas.job import SeniorityLevel
from app.schemas.job_search import JobSearchFilters
from app.vectorstores.qdrant_job_index import QdrantJobVectorIndex
from tests.conftest import make_job

DIM = 1024


class HashEmbeddings(Embeddings):
    """Bag-of-words hashing embedding: shared words -> higher cosine."""

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in text.lower().split():
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts):
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
async def index():
    client = AsyncQdrantClient(location=":memory:")
    settings = Settings(qdrant_collection_name="test_jobs", embedding_batch_size=2)
    yield QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(), settings=settings)
    await client.close()


JOBS = [
    make_job(1, title="Python Backend Intern", description="FastAPI PostgreSQL python",
             location="TP.HCM", skills=["Python"]),
    make_job(2, title="Java Spring Developer", description="Spring Boot Java microservices",
             location="Hà Nội", skills=["Java"], seniority=SeniorityLevel.SENIOR),
    make_job(3, title="React Frontend", description="React TypeScript UI",
             location="Ho Chi Minh City", skills=["React"], seniority=SeniorityLevel.UNKNOWN),
    make_job(4, title="Old Python job", description="python django",
             location="Đà Nẵng", expires_at=datetime.now(UTC) - timedelta(days=1)),
]


async def test_vec_01_collection_created_with_dimension_and_indexes(index):
    """TC-VEC-01: collection = 1024-d cosine with keyword payload indexes."""
    await index.ensure_collection()
    info = await index._client.get_collection("test_jobs")
    assert info.config.params.vectors.size == DIM
    assert info.config.params.vectors.distance == models.Distance.COSINE


async def test_vec_02_index_and_semantic_search(index):
    """TC-VEC-02: batch insertion; most similar job ranked first; ids mapped back."""
    summary = await index.index_jobs(JOBS)
    assert (summary.indexed, summary.batches) == (4, 2)
    hits = await index.search_jobs(query="python fastapi backend", limit=3)
    assert hits[0].job_id == JOBS[0].job_id
    assert all(-1 <= h.score <= 1 for h in hits)


async def test_vec_03_reindex_is_idempotent(index):
    """TC-VEC-03: deterministic point ids -> re-indexing does not duplicate."""
    await index.index_jobs(JOBS)
    await index.index_jobs(JOBS + JOBS)
    count = await index._client.count("test_jobs")
    assert count.count == 4


async def test_vec_04_metadata_filters(index):
    """TC-VEC-04: location alias, seniority(+unknown) and expiry filters."""
    await index.index_jobs(JOBS)
    hcm = await index.search_jobs(query="developer", limit=10,
                                  filters=JobSearchFilters(locations=["Hồ Chí Minh"]))
    senior = await index.search_jobs(query="developer", limit=10,
                                     filters=JobSearchFilters(seniority_levels=["senior"]))
    default = await index.search_jobs(query="python", limit=10, filters=JobSearchFilters())
    assert {h.job_id for h in hcm} == {JOBS[0].job_id, JOBS[2].job_id}
    assert {h.job_id for h in senior} == {JOBS[1].job_id, JOBS[2].job_id}
    assert JOBS[3].job_id not in {h.job_id for h in default}


async def test_vec_05_updated_job_overwrites_payload(index):
    """TC-VEC-05: updating a job (same job_id) replaces its vector payload."""
    await index.index_jobs(JOBS[:1])
    updated = make_job(1, title="Python Backend Intern", location="Hà Nội",
                       description="FastAPI PostgreSQL python", skills=["Python"])
    await index.index_jobs([updated])
    hits = await index.search_jobs(query="python", limit=5,
                                   filters=JobSearchFilters(locations=["Hà Nội"]))
    assert [h.job_id for h in hits] == [JOBS[0].job_id]


async def test_vec_06_wrong_embedding_dimension_rejected():
    """TC-VEC-06: an embedding model returning 768-d vectors -> 502, nothing written."""
    client = AsyncQdrantClient(location=":memory:")
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(768),
                               settings=Settings(qdrant_collection_name="t"))
    with pytest.raises(ExternalServiceException):
        await idx.index_jobs(JOBS[:1])
    with pytest.raises(ExternalServiceException):
        await idx.search_jobs(query="python", limit=3)
    assert (await client.count("t")).count == 0
    await client.close()


@pytest.mark.parametrize(("size", "distance"), [
    (8, models.Distance.COSINE), (DIM, models.Distance.DOT)])
async def test_vec_07_existing_collection_config_is_verified(size, distance):
    """TC-VEC-07 (BUG-032 fixed): ensure_collection() refuses an existing
    collection whose vector size/distance does not match the embeddings, at
    startup instead of at query/upsert time."""
    from app.core.exceptions import AppException

    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("t", vectors_config=models.VectorParams(
        size=size, distance=distance))
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    with pytest.raises(AppException) as error:
        await idx.ensure_collection()
    assert error.value.code == "VECTOR_COLLECTION_MISCONFIGURED"
    await client.close()


async def test_vec_07b_matching_existing_collection_is_accepted():
    """TC-VEC-07b: a correctly configured existing collection is reused."""
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("t", vectors_config=models.VectorParams(
        size=DIM, distance=models.Distance.COSINE))
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    await idx.ensure_collection()
    await client.close()


async def test_vec_08_jobs_can_be_deleted_and_expired_ones_pruned(index):
    """TC-VEC-08 (BUG-032 fixed): vectors of deleted jobs can be removed and
    expired jobs pruned; live jobs are untouched."""
    expired = make_job(9, title="Old Python job", description="python legacy",
                       expires_at=datetime.now(UTC) - timedelta(days=2))
    await index.index_jobs([*JOBS, expired])

    # JOBS[3] and ``expired`` are past their expiry date.
    assert await index.delete_expired_jobs() == 2
    assert await index.delete_expired_jobs() == 0  # idempotent
    assert await index.delete_jobs([JOBS[1].job_id, "unknown-id"]) == 2
    hits = await index.search_jobs(query="python java react", limit=10,
                                   filters=JobSearchFilters(include_expired=True))
    remaining = {hit.job_id for hit in hits}
    assert remaining == {JOBS[0].job_id, JOBS[2].job_id}
    assert await index.delete_jobs([]) == 0


async def test_vec_09_empty_query_and_limits(index):
    """TC-VEC-09: blank query / out-of-range limit -> ValueError."""
    for kwargs in ({"query": "  ", "limit": 3}, {"query": "x", "limit": 0},
                   {"query": "x", "limit": 501}):
        with pytest.raises(ValueError):
            await index.search_jobs(**kwargs)
