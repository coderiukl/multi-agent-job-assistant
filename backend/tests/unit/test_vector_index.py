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
from app.core.exceptions import AppException, ExternalServiceException
from app.embeddings.types import HybridEmbedding, SparseEmbedding
from app.schemas.job import SeniorityLevel
from app.schemas.job_search import JobSearchFilters
from app.utils.skill_keys import skill_key
from app.vectorstores.fusion import fuse_hits
from app.vectorstores.qdrant_job_index import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    QdrantJobVectorIndex,
)
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


class HybridHashEmbeddings(HashEmbeddings):
    """Adds a bag-of-words sparse vector (token id = word hash), like BGE-M3's
    lexical weights: only texts sharing an exact word get a sparse score."""

    sparse_enabled = True

    @staticmethod
    def _sparse(text: str) -> SparseEmbedding:
        weights: dict[int, float] = {}
        for word in text.lower().split():
            token_id = int(hashlib.md5(word.encode()).hexdigest(), 16) % 250_000
            weights[token_id] = weights.get(token_id, 0.0) + 1.0
        return SparseEmbedding(indices=list(weights), values=list(weights.values()))

    async def aembed_hybrid(self, texts):
        self.calls += 1
        return [HybridEmbedding(dense=self._vector(t), sparse=self._sparse(t))
                for t in texts]


def _collection_config(size: int = DIM, distance=models.Distance.COSINE,
                       sparse: bool = True) -> dict:
    config: dict = {"vectors_config": {DENSE_VECTOR: models.VectorParams(
        size=size, distance=distance)}}
    if sparse:
        config["sparse_vectors_config"] = {SPARSE_VECTOR: models.SparseVectorParams()}
    return config


@pytest.fixture
async def index():
    client = AsyncQdrantClient(location=":memory:")
    settings = Settings(qdrant_collection_name="test_jobs", embedding_batch_size=2)
    yield QdrantJobVectorIndex(client=client, embeddings=HybridHashEmbeddings(),
                               settings=settings)
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
    dense = info.config.params.vectors[DENSE_VECTOR]
    assert dense.size == DIM
    assert dense.distance == models.Distance.COSINE
    assert SPARSE_VECTOR in info.config.params.sparse_vectors


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


@pytest.mark.parametrize(("size", "distance", "sparse"), [
    (8, models.Distance.COSINE, True),
    (DIM, models.Distance.DOT, True),
    (DIM, models.Distance.COSINE, False)])
async def test_vec_07_existing_collection_config_is_verified(size, distance, sparse):
    """TC-VEC-07 (BUG-032 fixed): ensure_collection() refuses an existing
    collection whose vector size/distance does not match the embeddings, or
    that lacks the sparse vector, at startup instead of at query/upsert time."""
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("t", **_collection_config(size, distance, sparse))
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    with pytest.raises(AppException) as error:
        await idx.ensure_collection()
    assert error.value.code == "VECTOR_COLLECTION_MISCONFIGURED"
    await client.close()


async def test_vec_07a_legacy_unnamed_vector_collection_is_refused():
    """TC-VEC-07a: a pre-v3 collection (single unnamed vector) is refused, so
    QDRANT_COLLECTION_NAME must point to a new, re-indexed collection."""
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("t", vectors_config=models.VectorParams(
        size=DIM, distance=models.Distance.COSINE))
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    with pytest.raises(AppException) as error:
        await idx.ensure_collection()
    assert error.value.code == "VECTOR_COLLECTION_MISCONFIGURED"
    await client.close()


async def test_vec_07b_matching_existing_collection_is_accepted():
    """TC-VEC-07b: a correctly configured existing collection is reused."""
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("t", **_collection_config())
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


async def test_vec_10_dense_only_embeddings_still_work():
    """TC-VEC-10: an embedder without a sparse head writes dense vectors only
    and searches with the dense vector (fusion falls back to cosine)."""
    client = AsyncQdrantClient(location=":memory:")
    idx = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    assert idx.sparse_enabled is False
    await idx.index_jobs(JOBS)
    hits = await idx.search_jobs(query="python fastapi backend", limit=3)
    assert hits[0].job_id == JOBS[0].job_id
    points, _ = await client.scroll("t", with_vectors=True, limit=10)
    assert all(set(p.vector) == {DENSE_VECTOR} for p in points)
    assert all(p.payload["sparse_indexed"] is False for p in points)
    await client.close()


async def test_vec_11_points_store_sparse_vector_and_enabling_it_reindexes():
    """TC-VEC-11: hybrid points carry a sparse vector; points indexed without
    one are re-indexed once the sparse head is enabled."""
    client = AsyncQdrantClient(location=":memory:")
    settings = Settings(qdrant_collection_name="t")
    dense_only = QdrantJobVectorIndex(client=client, embeddings=HashEmbeddings(),
                                      settings=settings)
    await dense_only.index_jobs(JOBS[:2])
    hybrid = QdrantJobVectorIndex(client=client, embeddings=HybridHashEmbeddings(),
                                  settings=settings)
    assert len(await hybrid.get_jobs_requiring_index(JOBS[:2])) == 2
    await hybrid.index_jobs(JOBS[:2])
    assert await hybrid.get_jobs_requiring_index(JOBS[:2]) == []
    points, _ = await client.scroll("t", with_vectors=True, limit=10)
    assert all(SPARSE_VECTOR in p.vector for p in points)
    await client.close()


@pytest.mark.parametrize("mode", ["dense", "sparse", "linear", "rrf"])
async def test_vec_12_every_fusion_mode_searches_with_filters(mode):
    """TC-VEC-12: each fusion mode returns filtered hits scored in [0, 1]
    with the lexical match ranked first."""
    client = AsyncQdrantClient(location=":memory:")
    idx = QdrantJobVectorIndex(
        client=client, embeddings=HybridHashEmbeddings(),
        settings=Settings(qdrant_collection_name="t", vector_fusion_mode=mode))
    await idx.index_jobs(JOBS)
    hits = await idx.search_jobs(query="fastapi", limit=10,
                                 filters=JobSearchFilters(locations=["Hồ Chí Minh"]))
    assert hits[0].job_id == JOBS[0].job_id
    assert {h.job_id for h in hits} <= {JOBS[0].job_id, JOBS[2].job_id}
    assert all(0 <= h.score <= 1 for h in hits)
    await client.close()


async def test_vec_12a_linear_scores_do_not_depend_on_the_candidate_limit():
    """TC-VEC-12a: when dense and sparse disagree on the top hit, the linear
    blend still uses each job's real score on both vectors (missing scores are
    fetched), so a job's score is the same at limit=1 and limit=10."""
    client = AsyncQdrantClient(location=":memory:")
    idx = QdrantJobVectorIndex(
        client=client, embeddings=HybridHashEmbeddings(),
        settings=Settings(qdrant_collection_name="t", vector_fusion_mode="linear"))
    # Short text: best cosine. "kafka" repeated in a long text: best raw sparse
    # dot product but a diluted cosine.
    short = make_job(30, title="kafka", description="kafka", skills=[])
    filler = " ".join(f"word{i}" for i in range(150))
    repeated = make_job(31, title="Data platform engineer",
                        description=f"kafka kafka kafka kafka kafka {filler}",
                        skills=[])
    await idx.index_jobs([short, repeated])

    first = await idx._client.query_batch_points("t", requests=[
        models.QueryRequest(query=idx._embeddings._vector("kafka"), using=DENSE_VECTOR,
                            limit=1, with_payload=["job_id"]),
        models.QueryRequest(query=models.SparseVector(
            **HybridHashEmbeddings._sparse("kafka").__dict__),
            using=SPARSE_VECTOR, limit=1, with_payload=["job_id"]),
    ])
    tops = {r.points[0].payload["job_id"] for r in first}
    assert tops == {short.job_id, repeated.job_id}  # the two vectors disagree

    full = {h.job_id: h.score for h in await idx.search_jobs(query="kafka", limit=10)}
    top = await idx.search_jobs(query="kafka", limit=1)
    assert top[0].score == pytest.approx(full[top[0].job_id])
    assert top[0].job_id == max(full, key=full.get)
    await client.close()


async def test_vec_13_skill_filter_distinguishes_cpp_csharp_and_c():
    """TC-VEC-13: "C++", "C#" and "C" no longer share one skill key."""
    client = AsyncQdrantClient(location=":memory:")
    idx = QdrantJobVectorIndex(client=client, embeddings=HybridHashEmbeddings(),
                               settings=Settings(qdrant_collection_name="t"))
    jobs = [make_job(20, title="Embedded engineer", skills=["C++"]),
            make_job(21, title="Game developer", skills=["C#"]),
            make_job(22, title="Firmware engineer", skills=["C"])]
    await idx.index_jobs(jobs)
    for skill, expected in (("c++", jobs[0]), ("C#", jobs[1]), ("C", jobs[2])):
        hits = await idx.search_jobs(query="engineer developer", limit=10,
                                     filters=JobSearchFilters(skills=[skill]))
        assert [h.job_id for h in hits] == [expected.job_id]
    await client.close()


# --- fusion (pure) -----------------------------------------------------------

A, B, C = "a" * 64, "b" * 64, "c" * 64


def test_fusion_01_dense_mode_keeps_cosine_order():
    hits = fuse_hits([(A, 0.8), (B, 0.5)], [(C, 9.0)], mode="dense", limit=5)
    assert [(h.job_id, h.score) for h in hits] == [(A, 0.8), (B, 0.5)]


def test_fusion_02_linear_blends_cosine_and_relative_sparse():
    hits = fuse_hits([(A, 0.8), (B, 0.6)], [(B, 10.0), (C, 5.0)],
                     mode="linear", limit=5, dense_weight=0.5)
    scores = {h.job_id: h.score for h in hits}
    assert scores[B] == pytest.approx(0.5 * 0.6 + 0.5 * 1.0)
    assert scores[A] == pytest.approx(0.4)
    assert scores[C] == pytest.approx(0.25)
    assert [h.job_id for h in hits] == [B, A, C]


def test_fusion_03_rrf_is_normalized_to_one_for_top_of_both_lists():
    hits = fuse_hits([(A, 0.9), (B, 0.1)], [(A, 3.0), (C, 1.0)], mode="rrf", limit=5)
    assert hits[0].job_id == A and hits[0].score == pytest.approx(1.0)
    assert all(0 < h.score <= 1 for h in hits)


def test_fusion_04_empty_sparse_falls_back_to_dense_and_limit_applies():
    for mode in ("linear", "rrf"):
        hits = fuse_hits([(A, 0.7), (B, 0.6)], [], mode=mode, limit=1)
        assert [(h.job_id, h.score) for h in hits] == [(A, 0.7)]
    assert fuse_hits([], [], mode="sparse", limit=3) == []
    with pytest.raises(ValueError):
        fuse_hits([], [], mode="bogus", limit=3)  # type: ignore[arg-type]


def test_skill_key_01_symbols_are_preserved_as_words():
    assert len({skill_key("C++"), skill_key("C#"), skill_key("C")}) == 3
    assert skill_key("ASP.NET Core") == "asp dotnet core"
    assert skill_key("Node.js") == skill_key("node js")
    assert skill_key("Visual C++") == "visual cpp"
