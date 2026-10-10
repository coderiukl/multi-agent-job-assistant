import logging
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings, get_settings
from app.database import create_job_database_engine, create_job_session_factory
from app.embeddings import EmbeddingFactory
from app.repositories.postgres_job_index_source import PostgresJobIndexSource
from app.schemas.job_index import JobIndexSyncSummary
from app.vectorstores import QdrantJobVectorIndex, create_qdrant_client

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
        raise ValueError("JOB_STORAGE_BACKEND must be postgres to index jobs.")

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

        scanned = 0
        indexed = 0
        unchanged = 0
        indexing_batches = 0

        async for jobs in index_source.iter_batches(
            batch_size=scan_batch_size,
            source=source,
            job_ids=job_ids,
        ):
            scanned += len(jobs)
            pending_jobs = await vector_index.get_jobs_requiring_index(jobs)
            unchanged += len(jobs) - len(pending_jobs)

            result = await vector_index.index_jobs(pending_jobs)

            indexed += result.indexed
            indexing_batches += result.batches

            LOGGER.info(
                "Processed job vector synchronization batch",
                extra={
                    "collection": selected_settings.qdrant_collection_name,
                    "batch_received": len(jobs),
                    "batch_indexed": result.indexed,
                    "scanned": scanned,
                    "indexed": indexed,
                    "unchanged": unchanged,
                },
            )

        summary = JobIndexSyncSummary(
            source=source,
            scanned=scanned,
            indexed=indexed,
            unchanged=unchanged,
            batches=indexing_batches,
        )

        LOGGER.info(
            "Job vector synchronization completed",
            extra={
                "collection": (selected_settings.qdrant_collection_name),
                "scanned": scanned,
                "indexed": indexed,
                "unchanged": unchanged,
                "batches": indexing_batches,
            },
        )

        return summary.model_dump(mode="json")

    finally:
        await qdrant_client.close()
        await engine.dispose()
