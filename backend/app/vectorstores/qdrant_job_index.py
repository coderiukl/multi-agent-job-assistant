import logging
from uuid import NAMESPACE_URL, uuid5

from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import Settings
from app.core.exceptions import AppException, ExternalServiceException
from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary

LOGGER = logging.getLogger(__name__)

class QdrantJobVectorIndex:
    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        embeddings: Embeddings,
        settings: Settings
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
                    size=self._batch_size,
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
                message=(
                    "The job vector collection could not "
                    "be initialized."
                ),
            ) from exc

    async def index_jobs(self, jobs: list[NormalizedJob]) -> JobIndexingSummary:
        if not jobs:
            return JobIndexingSummary(received=0, indexed=0, batches=0)

        await self.ensure_collection()

        indexed = 0
        batches = 0

        try:
            for start in range(0, len(jobs), self._batch_size):
                batch = jobs[start: start + self._batch_size]
                texts = [self._build_embedding_text(job) for job in batch]
                vectors = await self._embeddings.aembed_documents(texts)   
                self._validate_vectors(job=batch, vectors=vectors)

                points = [
                    models.PointStruct(
                        id=self._point_id(job.job_id),
                        vector=vector,
                        payload=self._build_payload(job),
                    )
                    for job, vector in zip(batch, vectors, strict=True)
                ]

            await self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True
            )

            indexed += len(jobs)
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
                    "indexed": indexed,
                    "error_type": type(exc).__name__,
                },
            )

            raise ExternalServiceException(
                service="qdrant",
                message="Jobs could not be indexed.",
            ) from exc

        return JobIndexingSummary(
            received=len(jobs),
            indexed=indexed,
            batches=batches
        )

    def _build_embedding_text(self, job: NormalizedJob) -> str:
        employment_type = (
            job.employment_type.value
            if job.employment_type is not None
            else "unknown"
        )

        parts = [
            f"Job title: {job.title}",
            f"Company: {job.company}",
            f"Location: {job.location or 'unknown'}",
            f"Employment type: {employment_type}",
            f"Work mode: {job.work_mode.value}",
            f"Seniority: {job.seniority_level.value}",
            f"Skills: {', '.join(job.skills)}",
            f"Description: {job.description}",
        ]

        text = "\n".join(parts)
        return text[:self._max_text_chars]

    @staticmethod
    def _point_id(job_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"job:{job_id}"))

    @staticmethod
    def _build_payload(job: NormalizedJob) -> dict[str, object]:
        return {
            "job_id": job.job_id,
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
            "seniority_level": job.seniority_level.value,
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
            "salary_currency": job.salary_currency,
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

    def _validate_vectors(self, *, jobs: list[NormalizedJob], vectors: list[list[float]]) -> None:
        if len(jobs) != len(vectors):
            raise ValueError("Embedding result count does not match job count.")

        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ValueError(
                    "Embedding dimension does not match "
                    "the Qdrant collection."
                )