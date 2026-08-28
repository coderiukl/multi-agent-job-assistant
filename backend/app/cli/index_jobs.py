from typing import Any

from app.core.config import Settings, get_settings
from app.database import create_job_database_engine, create_job_session_factory
from app.embeddings import EmbeddingFactory
from app.repositories.postgres_job_index_source import PostgresJobIndexSource
from app.schemas.job_index import JobIndexSyncSummary
from app.vectorstores import QdrantJobVectorIndex, create_qdrant_client

async def sync_job_index(*, scan_batch_size: int, settings:Settings | None = None) -> dict[str, Any]:
    selected_settings = settings or get_settings()

    if selected_settings.job_storage_backend != "postgres":
        raise ValueError(
            "JOB_STORAGE_BACKEND must be postgres to index jobs."
        )

    if not 1 < scan_batch_size <= 1_000:
        raise ValueError("scan_batch_size must be between 1 and 1000")

    engine = create_job_database_engine(selected_settings)
    session_factory = create_job_session_factory(engine)
    qdrant_client = create_qdrant_client(selected_settings)

    try:
        embeddings = EmbeddingFactory.create(selected_settings)
        source = PostgresJobIndexSource(session_factory)
        vector_index = QdrantJobVectorIndex(
            client=qdrant_client,
            embeddings=embeddings,
            settings=selected_settings,
        )

        await vector_index.ensure_collection()

        scanned = 0
        indexed = 0
        unchanged = 0
        batches = 0

        async for jobs in source.iter_batches(batch_size=scan_batch_size):
            scanned += len(jobs)

            pending_jobs = await vector_index.get_jobs_requiring_index(jobs)

            unchanged += len(jobs) - len(pending_jobs)

            result = await vector_index.index_jobs(pending_jobs)

            indexed += result.indexed
            batches += result.batches

        summary = JobIndexSyncSummary(
            scanned=scanned,
            indexed=indexed,
            unchanged=unchanged,
            batches=batches
        )

        return summary.model_dump(mode="json")

    finally:
        await qdrant_client.close()
        await engine.dispose()