import logging
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import Settings
from app.core.exceptions import AppException, ExternalServiceException
from app.embeddings.types import HybridEmbedding, SparseEmbedding, supports_sparse
from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary
from app.schemas.job_search import JobSearchFilters, JobVectorSearchHit
from app.utils.job_deduplication import (
    build_job_deduplication_key,
    build_job_location_keys,
)
from app.utils.skill_keys import skill_key
from app.vectorstores.fusion import fuse_hits

LOGGER = logging.getLogger(__name__)
# v3: named dense vector + BGE-M3 sparse vector per point.
INDEX_PAYLOAD_VERSION = "v3"
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"


class QdrantJobVectorIndex:
    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        embeddings: Embeddings,
        settings: Settings,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._collection_name = settings.qdrant_collection_name
        self._dimensions = settings.embedding_dimensions
        self._batch_size = settings.embedding_batch_size
        self._max_text_chars = settings.job_embedding_max_chars
        self._embedding_model = settings.embedding_model
        self._embedding_model_version = settings.embedding_model_version
        self._embedding_text_version = settings.job_embedding_text_version
        self._sparse_enabled = supports_sparse(embeddings)
        self._fusion_mode = settings.vector_fusion_mode
        self._fusion_dense_weight = settings.vector_fusion_dense_weight
        self._collection_ready = False

    @property
    def sparse_enabled(self) -> bool:
        return self._sparse_enabled

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return

        try:
            exists = await self._client.collection_exists(self._collection_name)

            if not exists:
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config={
                        DENSE_VECTOR: models.VectorParams(
                            size=self._dimensions,
                            distance=models.Distance.COSINE,
                        ),
                    },
                    # BGE-M3 weights are learned, so no IDF modifier. The
                    # sparse vector is always declared so it can be enabled
                    # later without recreating the collection.
                    sparse_vectors_config={
                        SPARSE_VECTOR: models.SparseVectorParams(),
                    },
                )
            else:
                await self._validate_existing_collection()

            await self._ensure_payload_indexes()
            self._collection_ready = True

        except AppException:
            raise

        except Exception as exc:
            LOGGER.exception(
                "Could not initialize Qdrant collection",
                extra={
                    "collection": self._collection_name,
                    "error_type": type(exc).__name__,
                },
            )

            raise ExternalServiceException(
                service="qdrant",
                message=("The job vector collection could not be initialized."),
            ) from exc

    async def _validate_existing_collection(self) -> None:
        """Refuse a collection whose vectors do not match the embedding model.

        Otherwise the mismatch only surfaces later as failing upserts/queries
        (BUG-032), e.g. after changing EMBEDDING_MODEL without a new collection.
        """
        info = await self._client.get_collection(self._collection_name)
        vectors = info.config.params.vectors
        # This index writes the named vectors "dense" (+ "sparse"); a legacy
        # collection with one unnamed vector (index payload <= v2) is refused.
        vectors = vectors.get(DENSE_VECTOR) if isinstance(vectors, dict) else None
        sparse_vectors = info.config.params.sparse_vectors or {}

        size = getattr(vectors, "size", None)
        distance = getattr(vectors, "distance", None)
        if (
            size != self._dimensions
            or distance != models.Distance.COSINE
            or SPARSE_VECTOR not in sparse_vectors
        ):
            LOGGER.error(
                "Qdrant collection configuration does not match the embeddings",
                extra={
                    "collection": self._collection_name,
                    "expected_size": self._dimensions,
                    "actual_size": size,
                    "actual_distance": str(distance),
                    "has_sparse_vector": SPARSE_VECTOR in sparse_vectors,
                },
            )
            raise AppException(
                status_code=500,
                code="VECTOR_COLLECTION_MISCONFIGURED",
                message=(
                    "The job vector collection does not match the configured "
                    "embedding model. Use a new QDRANT_COLLECTION_NAME and "
                    "re-index the jobs."
                ),
                details={
                    "collection": self._collection_name,
                    "expected_size": self._dimensions,
                    "actual_size": size,
                    "has_sparse_vector": SPARSE_VECTOR in sparse_vectors,
                },
            )

    async def delete_jobs(self, job_ids: list[str]) -> int:
        """Remove the vectors of jobs deleted from PostgreSQL."""
        unique_ids = list(dict.fromkeys(job_id for job_id in job_ids if job_id))
        if not unique_ids:
            return 0

        await self.ensure_collection()
        point_ids = [self._point_id_for_job_id(job_id) for job_id in unique_ids]
        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(points=point_ids),
                wait=True,
            )
        except Exception as exc:
            LOGGER.exception(
                "Could not delete Qdrant job points",
                extra={"collection": self._collection_name,
                       "error_type": type(exc).__name__},
            )
            raise ExternalServiceException(
                service="qdrant",
                message="Job vectors could not be deleted.",
            ) from exc
        return len(point_ids)

    async def delete_expired_jobs(self, *, before: datetime | None = None) -> int:
        """Remove vectors of jobs that expired before ``before`` (default: now)."""
        await self.ensure_collection()
        cutoff = before or datetime.now(UTC)
        expired = models.Filter(
            must=[
                models.FieldCondition(
                    key="expires_at",
                    range=models.DatetimeRange(lt=cutoff),
                )
            ]
        )
        try:
            counted = await self._client.count(
                collection_name=self._collection_name,
                count_filter=expired,
                exact=True,
            )
            if counted.count:
                await self._client.delete(
                    collection_name=self._collection_name,
                    points_selector=models.FilterSelector(filter=expired),
                    wait=True,
                )
        except Exception as exc:
            LOGGER.exception(
                "Could not prune expired Qdrant job points",
                extra={"collection": self._collection_name,
                       "error_type": type(exc).__name__},
            )
            raise ExternalServiceException(
                service="qdrant",
                message="Expired job vectors could not be pruned.",
            ) from exc
        return counted.count

    async def get_jobs_requiring_index(
        self,
        jobs: list[NormalizedJob],
    ) -> list[NormalizedJob]:
        unique_jobs = self._unique_jobs_by_id(jobs)

        if not unique_jobs:
            return []

        await self.ensure_collection()

        point_ids = [self._point_id(job) for job in unique_jobs]

        try:
            records = await self._client.retrieve(
                collection_name=self._collection_name,
                ids=point_ids,
                with_payload=True,
                with_vectors=False,
            )

        except Exception as exc:
            LOGGER.exception(
                "Could not read existing Qdrant points",
                extra={
                    "collection": self._collection_name,
                    "received_jobs": len(jobs),
                    "unique_jobs": len(unique_jobs),
                    "error_type": type(exc).__name__,
                },
            )

            raise ExternalServiceException(
                service="qdrant",
                message=("Existing job vectors could not be read."),
            ) from exc

        existing_payloads_by_point_id: dict[str, dict[str, object]] = {}

        for record in records:
            existing_payloads_by_point_id[str(record.id)] = record.payload or {}

        requiring_index: list[NormalizedJob] = []

        for job in unique_jobs:
            point_id = self._point_id(job)
            payload = existing_payloads_by_point_id.get(point_id)

            if payload is None or not self._index_metadata_matches(
                job=job,
                payload=payload,
            ):
                requiring_index.append(job)

        LOGGER.info(
            "Resolved jobs requiring vector indexing",
            extra={
                "collection": self._collection_name,
                "received_jobs": len(jobs),
                "unique_jobs": len(unique_jobs),
                "requiring_index": len(requiring_index),
                "duplicates_removed": (len(jobs) - len(unique_jobs)),
            },
        )

        return requiring_index

    async def index_jobs(self, jobs: list[NormalizedJob]) -> JobIndexingSummary:
        received_count = len(jobs)
        unique_jobs = self._unique_jobs_by_id(jobs)

        if not unique_jobs:
            return JobIndexingSummary(
                received=received_count,
                indexed=0,
                batches=0,
            )

        await self.ensure_collection()

        indexed = 0
        batches = 0

        try:
            for start in range(0, len(unique_jobs), self._batch_size):
                batch = unique_jobs[start : start + self._batch_size]

                texts = [self._build_embedding_text(job) for job in batch]

                embeddings = await self._embed_documents(texts)

                self._validate_embeddings(
                    jobs=batch,
                    embeddings=embeddings,
                )

                points = [
                    models.PointStruct(
                        id=self._point_id(job),
                        vector=self._point_vectors(embedding),
                        payload=self._build_payload(job),
                    )
                    for job, embedding in zip(batch, embeddings, strict=True)
                ]

                await self._client.upsert(
                    collection_name=(self._collection_name),
                    points=points,
                    wait=True,
                )

                indexed += len(batch)
                batches += 1

                LOGGER.info(
                    "Indexed job embedding batch",
                    extra={
                        "collection": self._collection_name,
                        "batch_size": len(points),
                        "indexed": indexed,
                    },
                )

        except AppException:
            raise

        except Exception as exc:
            LOGGER.exception(
                "Job embedding indexing failed",
                extra={
                    "collection": self._collection_name,
                    "received_jobs": received_count,
                    "unique_jobs": len(unique_jobs),
                    "indexed": indexed,
                    "error_type": type(exc).__name__,
                },
            )

            raise ExternalServiceException(
                service="qdrant",
                message="Jobs could not be indexed.",
            ) from exc

        return JobIndexingSummary(
            received=received_count,
            indexed=indexed,
            batches=batches,
        )

    async def search_jobs(
        self,
        *,
        query: str,
        limit: int,
        filters: JobSearchFilters | None = None,
    ) -> list[JobVectorSearchHit]:
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Semantic query must not be empty.")

        if not 1 <= limit <= 500:
            raise ValueError("Semantic search limit must be between 1 and 500.")

        await self.ensure_collection()

        try:
            query_embedding = await self._embed_query(normalized_query)
            query_filter = self._build_search_filter(filters)
            dense_query = query_embedding.dense
            sparse_query = models.SparseVector(
                indices=query_embedding.sparse.indices,
                values=query_embedding.sparse.values,
            )
            requests = [
                self._query_request(dense_query, DENSE_VECTOR, query_filter, limit)
            ]
            use_sparse = (
                self._fusion_mode != "dense"
                and bool(query_embedding.sparse.indices)
            )
            if use_sparse:
                requests.append(
                    self._query_request(
                        sparse_query, SPARSE_VECTOR, query_filter, limit
                    )
                )

            responses = await self._client.query_batch_points(
                collection_name=self._collection_name,
                requests=requests,
            )
            dense_hits = self._scored_job_ids(responses[0].points)
            sparse_hits = (
                self._scored_job_ids(responses[1].points)
                if len(responses) > 1
                else []
            )

            if use_sparse and self._fusion_mode == "linear":
                dense_hits, sparse_hits = await self._complete_linear_scores(
                    dense_hits,
                    sparse_hits,
                    dense_query=dense_query,
                    sparse_query=sparse_query,
                    query_filter=query_filter,
                )

        except AppException:
            raise

        except Exception as exc:
            LOGGER.exception(
                "Qdrant semantic job search failed",
                extra={
                    "collection": self._collection_name,
                    "limit": limit,
                    "error_type": type(exc).__name__,
                },
            )

            raise ExternalServiceException(
                service="qdrant",
                message=("Semantic job search is unavailable."),
            ) from exc

        return fuse_hits(
            dense_hits,
            sparse_hits,
            mode=self._fusion_mode,
            limit=limit,
            dense_weight=self._fusion_dense_weight,
        )

    @staticmethod
    def _query_request(
        query: list[float] | models.SparseVector,
        using: str,
        query_filter: models.Filter | None,
        limit: int,
    ) -> models.QueryRequest:
        return models.QueryRequest(
            query=query,
            using=using,
            filter=query_filter,
            limit=limit,
            with_payload=["job_id"],
            with_vector=False,
        )

    async def _complete_linear_scores(
        self,
        dense_hits: list[tuple[str, float]],
        sparse_hits: list[tuple[str, float]],
        *,
        dense_query: list[float],
        sparse_query: models.SparseVector,
        query_filter: models.Filter | None,
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        """Score each candidate on the side whose top-K it missed.

        Both lists are top-K only, so a job ranked by one vector alone would
        get 0 for the other one in the linear blend just because it was not
        retrieved. One extra batched query restricted to those point ids
        fetches the real scores (a job without any shared sparse token stays
        at 0, which is then its true sparse score).
        """
        dense_ids = {job_id for job_id, _ in dense_hits}
        sparse_ids = {job_id for job_id, _ in sparse_hits}
        missing = (
            (DENSE_VECTOR, dense_query, sorted(sparse_ids - dense_ids)),
            (SPARSE_VECTOR, sparse_query, sorted(dense_ids - sparse_ids)),
        )
        lookups = [
            (using, query, job_ids) for using, query, job_ids in missing if job_ids
        ]
        if not lookups:
            return dense_hits, sparse_hits

        requests = []
        for using, query, job_ids in lookups:
            restriction: list[models.Condition] = [
                models.HasIdCondition(
                    has_id=[self._point_id_for_job_id(job_id) for job_id in job_ids]
                )
            ]
            if query_filter is not None:
                restriction.append(query_filter)
            requests.append(
                self._query_request(
                    query, using, models.Filter(must=restriction), len(job_ids)
                )
            )

        responses = await self._client.query_batch_points(
            collection_name=self._collection_name,
            requests=requests,
        )

        completed = {DENSE_VECTOR: list(dense_hits), SPARSE_VECTOR: list(sparse_hits)}
        for (using, _, _), response in zip(lookups, responses, strict=True):
            completed[using].extend(self._scored_job_ids(response.points))

        return completed[DENSE_VECTOR], completed[SPARSE_VECTOR]

    @staticmethod
    def _scored_job_ids(points: list[models.ScoredPoint]) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []

        for point in points:
            payload = point.payload or {}
            job_id = payload.get("job_id")

            if not isinstance(job_id, str):
                LOGGER.warning(
                    "Qdrant job point has no valid job_id",
                    extra={"point_id": str(point.id)},
                )
                continue

            scored.append((job_id, float(point.score)))

        return scored

    async def _embed_documents(self, texts: list[str]) -> list[HybridEmbedding]:
        if self._sparse_enabled:
            return await self._embeddings.aembed_hybrid(texts)  # type: ignore[attr-defined]

        vectors = await self._embeddings.aembed_documents(texts)
        empty = SparseEmbedding(indices=[], values=[])
        return [HybridEmbedding(dense=vector, sparse=empty) for vector in vectors]

    async def _embed_query(self, text: str) -> HybridEmbedding:
        if self._sparse_enabled and self._fusion_mode != "dense":
            embeddings = await self._embeddings.aembed_hybrid([text])  # type: ignore[attr-defined]
            embedding = embeddings[0]
        else:
            embedding = HybridEmbedding(
                dense=await self._embeddings.aembed_query(text),
                sparse=SparseEmbedding(indices=[], values=[]),
            )

        if len(embedding.dense) != self._dimensions:
            raise ValueError(
                "Query embedding dimension does not match the Qdrant collection."
            )

        return embedding

    @staticmethod
    def _point_vectors(embedding: HybridEmbedding) -> dict[str, object]:
        vectors: dict[str, object] = {DENSE_VECTOR: embedding.dense}

        if embedding.sparse.indices:
            vectors[SPARSE_VECTOR] = models.SparseVector(
                indices=embedding.sparse.indices,
                values=embedding.sparse.values,
            )

        return vectors

    def _build_embedding_text(self, job: NormalizedJob) -> str:
        employment_type = (
            job.employment_type.value if job.employment_type is not None else "unknown"
        )

        parts = [
            f"Job title: {job.title}",
            f"Company: {job.company}",
            (f"Location: {job.location or 'unknown'}"),
            (f"Employment type: {employment_type}"),
            (f"Work mode: {job.work_mode.value}"),
            (f"Seniority: {job.seniority_level.value}"),
            (f"Skills: {', '.join(job.skills)}"),
            (f"Categories: {', '.join(self._job_categories(job))}"),
            (f"Description: {job.description}"),
        ]

        text = "\n".join(parts)

        return text[: self._max_text_chars]

    @staticmethod
    def _job_categories(job: NormalizedJob) -> list[str]:
        categories = job.source_metadata.get("job_categories") or []
        return [str(category) for category in categories if str(category).strip()]

    @staticmethod
    def _point_id(job: NormalizedJob) -> str:
        return QdrantJobVectorIndex._point_id_for_job_id(job.job_id)

    @staticmethod
    def _point_id_for_job_id(job_id: str) -> str:
        # Qdrant only accepts unsigned integers or UUIDs as point IDs. Use a
        # deterministic UUID derived solely from PostgreSQL's stable job_id.
        return str(
            uuid5(
                NAMESPACE_URL,
                f"source-record-job:{job_id}",
            )
        )

    def _build_payload(self, job: NormalizedJob) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "source_record_id": job.job_id,
            "source_job_id": job.source_job_id,
            "canonical_key": (build_job_deduplication_key(job)),
            "content_hash": job.content_hash,
            "embedding_model": self._embedding_model,
            "embedding_model_version": self._embedding_model_version,
            "embedding_text_version": self._embedding_text_version,
            "index_payload_version": INDEX_PAYLOAD_VERSION,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "location_keys": build_job_location_keys(job.location),
            "employment_type": (
                job.employment_type.value if job.employment_type is not None else None
            ),
            "work_mode": job.work_mode.value,
            "seniority_level": (job.seniority_level.value),
            "skills": job.skills,
            "skill_keys": list(dict.fromkeys(skill_key(skill) for skill in job.skills)),
            "sparse_indexed": self._sparse_enabled,
            "salary_min": (
                float(job.salary_min) if job.salary_min is not None else None
            ),
            "salary_max": (
                float(job.salary_max) if job.salary_max is not None else None
            ),
            "salary_currency": (job.salary_currency),
            "salary_period": job.salary_period.value,
            "salary_floor": self._salary_floor(job),
            "salary_ceiling": self._salary_ceiling(job),
            "posted_at": (
                job.posted_at.isoformat() if job.posted_at is not None else None
            ),
            "expires_at": (
                job.expires_at.isoformat() if job.expires_at is not None else None
            ),
            "source": job.source,
            "source_url": str(job.source_url),
        }

    def _index_metadata_matches(
        self,
        *,
        job: NormalizedJob,
        payload: dict[str, object],
    ) -> bool:
        return (
            payload.get("job_id") == job.job_id
            and payload.get("content_hash") == job.content_hash
            and payload.get("embedding_model") == self._embedding_model
            and payload.get("embedding_model_version") == self._embedding_model_version
            and payload.get("embedding_text_version") == self._embedding_text_version
            and payload.get("index_payload_version") == INDEX_PAYLOAD_VERSION
            # Turning the sparse head on re-indexes points that only have the
            # dense vector; turning it off keeps the existing sparse vectors.
            and (bool(payload.get("sparse_indexed")) or not self._sparse_enabled)
        )
        

    @staticmethod
    def _salary_floor(job: NormalizedJob) -> float | None:
        value = job.salary_min if job.salary_min is not None else job.salary_max
        return float(value) if value is not None else None

    @staticmethod
    def _salary_ceiling(job: NormalizedJob) -> float | None:
        value = job.salary_max if job.salary_max is not None else job.salary_min
        return float(value) if value is not None else None

    async def _ensure_payload_indexes(self) -> None:
        index_definitions = {
            "location_keys": models.PayloadSchemaType.KEYWORD,
            "employment_type": models.PayloadSchemaType.KEYWORD,
            "work_mode": models.PayloadSchemaType.KEYWORD,
            "seniority_level": models.PayloadSchemaType.KEYWORD,
            "skill_keys": models.PayloadSchemaType.KEYWORD,
            "salary_currency": models.PayloadSchemaType.KEYWORD,
            "salary_period": models.PayloadSchemaType.KEYWORD,
            "salary_floor": models.PayloadSchemaType.FLOAT,
            "salary_ceiling": models.PayloadSchemaType.FLOAT,
            "posted_at": models.PayloadSchemaType.DATETIME,
            "expires_at": models.PayloadSchemaType.DATETIME,
        }

        for field_name, field_schema in index_definitions.items():
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )

    @staticmethod
    def _build_search_filter(
        filters: JobSearchFilters | None,
    ) -> models.Filter | None:
        if filters is None:
            return None

        must: list[models.Condition] = []

        if filters.locations:
            location_keys = list(
                dict.fromkeys(
                    key
                    for location in filters.locations
                    for key in build_job_location_keys(location)
                )
            )
            must.append(
                models.FieldCondition(
                    key="location_keys",
                    match=models.MatchAny(any=location_keys),
                )
            )

        if filters.employment_types:
            must.append(
                models.FieldCondition(
                    key="employment_type",
                    match=models.MatchAny(
                        any=[value.value for value in filters.employment_types]
                    ),
                )
            )

        if filters.work_modes:
            must.append(
                models.FieldCondition(
                    key="work_mode",
                    match=models.MatchAny(
                        any=[value.value for value in filters.work_modes]
                    ),
                )
            )

        if filters.seniority_levels:
            seniority_values = [value.value for value in filters.seniority_levels]
            seniority_values.append("unknown")
            must.append(
                models.FieldCondition(
                    key="seniority_level",
                    match=models.MatchAny(any=list(dict.fromkeys(seniority_values))),
                )
            )

        if filters.skills:
            must.append(
                models.FieldCondition(
                    key="skill_keys",
                    match=models.MatchAny(
                        any=[
                            skill_key(skill)
                            for skill in filters.skills
                        ]
                    ),
                )
            )

        if filters.salary_min is not None:
            must.append(
                models.FieldCondition(
                    key="salary_ceiling",
                    range=models.Range(gte=filters.salary_min),
                )
            )

        if filters.salary_max is not None:
            must.append(
                models.FieldCondition(
                    key="salary_floor",
                    range=models.Range(lte=filters.salary_max),
                )
            )

        if filters.salary_currency is not None:
            must.append(
                models.FieldCondition(
                    key="salary_currency",
                    match=models.MatchValue(value=filters.salary_currency),
                )
            )

        if filters.salary_period is not None:
            must.append(
                models.FieldCondition(
                    key="salary_period",
                    match=models.MatchValue(value=filters.salary_period.value),
                )
            )

        if filters.posted_after is not None:
            must.append(
                models.FieldCondition(
                    key="posted_at",
                    range=models.DatetimeRange(gte=filters.posted_after),
                )
            )

        if not filters.include_expired:
            must.append(
                models.Filter(
                    should=[
                        models.IsEmptyCondition(
                            is_empty=models.PayloadField(key="expires_at"),
                        ),
                        models.FieldCondition(
                            key="expires_at",
                            range=models.DatetimeRange(gte=datetime.now(UTC)),
                        ),
                    ]
                )
            )

        return models.Filter(must=must) if must else None

    @staticmethod
    def _unique_jobs_by_id(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
        jobs_by_id: dict[str, NormalizedJob] = {}

        for job in jobs:
            jobs_by_id[job.job_id] = job

        return list(jobs_by_id.values())

    def _validate_embeddings(
        self,
        *,
        jobs: list[NormalizedJob],
        embeddings: list[HybridEmbedding],
    ) -> None:
        if len(jobs) != len(embeddings):
            raise ValueError("Embedding result count does not match job count.")

        for embedding in embeddings:
            if len(embedding.dense) != self._dimensions:
                raise ValueError(
                    "Embedding dimension does not match the Qdrant collection."
                )
            if len(embedding.sparse.indices) != len(embedding.sparse.values):
                raise ValueError(
                    "Sparse embedding indices and values differ in length."
                )
