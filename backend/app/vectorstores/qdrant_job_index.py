import logging
from uuid import NAMESPACE_URL, uuid5

from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import Settings
from app.core.exceptions import AppException, ExternalServiceException
from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary
from app.schemas.job_search import JobVectorSearchHit
from app.utils.job_deduplication import (
    build_job_deduplication_key,
    deduplicate_jobs,
)

LOGGER = logging.getLogger(__name__)


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

    async def ensure_collection(self) -> None:
        try:
            exists = await self._client.collection_exists(self._collection_name)

            if exists:
                return

            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=self._dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

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

    async def get_jobs_requiring_index(self, jobs: list[NormalizedJob]) -> list[NormalizedJob]:
        unique_jobs = deduplicate_jobs(jobs)

        if not unique_jobs:
            return []

        await self.ensure_collection()

        point_ids = [
            self._point_id(job)
            for job in unique_jobs
        ]

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
                message=(
                    "Existing job vectors could "
                    "not be read."
                ),
            ) from exc

        existing_hashes_by_point_id: dict[str, str] = {}

        for record in records:
            payload = record.payload or {}
            content_hash = payload.get("content_hash")

            if isinstance(content_hash, str):
                existing_hashes_by_point_id[str(record.id)] = content_hash

        requiring_index: list[NormalizedJob] = []
            
        for job in unique_jobs:
            point_id = self._point_id(job)

            if (existing_hashes_by_point_id.get(point_id) != job.content_hash):
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
        unique_jobs = deduplicate_jobs(jobs)

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

                texts = [
                    self._build_embedding_text(job)
                    for job in batch
                ]

                vectors = await self._embeddings.aembed_documents(texts)

                self._validate_vectors(
                    jobs=batch,
                    vectors=vectors,
                )

                points = [
                    models.PointStruct(
                        id=self._point_id(job),
                        vector=vector,
                        payload=self._build_payload(job),
                    )
                    for job, vector in zip(batch, vectors, strict=True)
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

    async def search_jobs(self, *, query: str, limit: int) -> list[JobVectorSearchHit]:
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Semantic query must not be empty.")
            
        if not 1 <= limit <= 500:
            raise ValueError("Semantic search limit must be between 1 and 500.")

        await self.ensure_collection()

        try:
            query_vector = await self._embeddings.aembed_query(normalized_query)

            if len(query_vector) != self._dimensions:
                raise ValueError("Query embedding dimension does not match the Qdrant collection.")

            response = (
                await self._client.query_points(
                    collection_name=self._collection_name,
                    query=query_vector,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
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
                message=(
                    "Semantic job search is unavailable."
                ),
            ) from exc

        hits: list[JobVectorSearchHit] = []

        for point in response.points:
            payload = point.payload or {}
            job_id = payload.get("job_id")

            if not isinstance(job_id, str):
                LOGGER.warning(
                    "Qdrant job point has no valid job_id",
                    extra={
                        "point_id": str(point.id)
                    },
                )
                continue

            hits.append(
                JobVectorSearchHit(
                    job_id=job_id,
                    score=float(point.score),
                )
            )

        return hits

    def _build_embedding_text(self, job: NormalizedJob) -> str:
        employment_type = (
            job.employment_type.value
            if job.employment_type is not None
            else "unknown"
        )

        parts = [
            f"Job title: {job.title}",
            f"Company: {job.company}",
            (
                "Location: "
                f"{job.location or 'unknown'}"
            ),
            (
                "Employment type: "
                f"{employment_type}"
            ),
            (
                "Work mode: "
                f"{job.work_mode.value}"
            ),
            (
                "Seniority: "
                f"{job.seniority_level.value}"
            ),
            (
                "Skills: "
                f"{', '.join(job.skills)}"
            ),
            (
                "Description: "
                f"{job.description}"
            ),
        ]

        text = "\n".join(parts)

        return text[: self._max_text_chars]

    @staticmethod
    def _point_id(job: NormalizedJob) -> str:
        canonical_key = (
            build_job_deduplication_key(job)
        )

        return str(
            uuid5(
                NAMESPACE_URL,
                f"canonical-job:{canonical_key}",
            )
        )

    @staticmethod
    def _build_payload(job: NormalizedJob) -> dict[str, object]:
        return {
            "job_id": job.job_id,
            "canonical_key": (
                build_job_deduplication_key(job)
            ),
            "content_hash": job.content_hash,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "employment_type": (
                job.employment_type.value
                if job.employment_type is not None
                else None
            ),
            "work_mode": job.work_mode.value,
            "seniority_level": (
                job.seniority_level.value
            ),
            "skills": job.skills,
            "salary_min": (
                float(job.salary_min)
                if job.salary_min is not None
                else None
            ),
            "salary_max": (
                float(job.salary_max)
                if job.salary_max is not None
                else None
            ),
            "salary_currency": (
                job.salary_currency
            ),
            "posted_at": (
                job.posted_at.isoformat()
                if job.posted_at is not None
                else None
            ),
            "expires_at": (
                job.expires_at.isoformat()
                if job.expires_at is not None
                else None
            ),
            "source": job.source,
            "source_url": str(job.source_url),
        }

    def _validate_vectors(
        self,
        *,
        jobs: list[NormalizedJob],
        vectors: list[list[float]],
    ) -> None:
        if len(jobs) != len(vectors):
            raise ValueError(
                "Embedding result count does "
                "not match job count."
            )

        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ValueError(
                    "Embedding dimension does not "
                    "match the Qdrant collection."
                )