from collections.abc import Sequence
from typing import Any

from app.core.config import Settings, get_settings
from app.database import create_job_database_engine, create_job_session_factory
from app.embeddings import EmbeddingFactory
from app.repositories.postgres_job_index_source import PostgresJobIndexSource
from app.schemas.job_index import JobIndexSyncSummary
from app.schemas.job import NormalizedJob
from app.utils.job_deduplication import deduplicate_jobs
from app.vectorstores import QdrantJobVectorIndex, create_qdrant_client
import logging
LOGGER = logging.getLogger(__name__)


async def sync_job_index(
    *,
    scan_batch_size: int,
    source: str | None = None,
    job_ids: Sequence[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    selected_settings = settings or get_settings()

    if selected_settings.job_storage_backend != "postgres":
        raise ValueError(
            "JOB_STORAGE_BACKEND must be postgres to index jobs."
        )

    if not 1 <= scan_batch_size <= 1_000:
        raise ValueError("scan_batch_size must be between 1 and 1000")

    engine = create_job_database_engine(selected_settings)
    session_factory = create_job_session_factory(engine)
    qdrant_client = create_qdrant_client(selected_settings)

    try:
        embeddings = EmbeddingFactory.create(selected_settings)
        index_source = PostgresJobIndexSource(session_factory)
        vector_index = QdrantJobVectorIndex(
            client=qdrant_client,
            embeddings=embeddings,
            settings=selected_settings,
        )

        await vector_index.ensure_collection()

        all_jobs: list[NormalizedJob] = []

        async for jobs in index_source.iter_batches(
            batch_size=scan_batch_size,
            source=source,
            job_ids=job_ids,
        ):
            all_jobs.extend(jobs)

        scanned = len(all_jobs)

        unique_jobs = deduplicate_jobs(all_jobs)

        duplicate_count = scanned - len(unique_jobs)

        indexed = 0
        unchanged = duplicate_count
        indexing_batches = 0


        summary = JobIndexSyncSummary(
            source=source,
            scanned=scanned,
            indexed=indexed,
            unchanged=unchanged,
            batches=indexing_batches
        )

        LOGGER.info(
            "Prepared jobs for vector indexing",
            extra={
                "collection": selected_settings.qdrant_collection_name,
                "scanned": scanned,
                "unique_jobs": len(unique_jobs),
                "duplicates_removed": (
                    duplicate_count
                ),
            },
        )

        for start in range(0, len(unique_jobs), scan_batch_size):
            batch = unique_jobs[start: start + scan_batch_size]

            pending_jobs = await vector_index.get_jobs_requiring_index(batch)

            unchanged += len(batch) - len(pending_jobs)

            result = await vector_index.index_jobs(pending_jobs)

            indexed += result.indexed
            indexing_batches += result.batches

        summary = JobIndexSyncSummary(
            source=source,
            scanned=scanned,
            indexed=indexed,
            unchanged=unchanged,
            batches=indexing_batches
        )

        LOGGER.info(
            "Job vector synchronization completed",
            extra={
                "collection": (
                    selected_settings
                    .qdrant_collection_name
                ),
                "scanned": scanned,
                "unique_jobs": len(unique_jobs),
                "duplicates_removed": (
                    duplicate_count
                ),
                "indexed": indexed,
                "unchanged": unchanged,
                "batches": indexing_batches,
            },
        )

        return summary.model_dump(mode="json")
    
    finally:
        await qdrant_client.close()
        await engine.dispose()
