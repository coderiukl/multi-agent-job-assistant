from pathlib import Path
from typing import Protocol

from app.repositories.job import NormalizedJobRepository, RawJobRepository
from app.schemas.job import NormalizedJob, RawJob
from app.schemas.job_storage import JobUpsertSummary


class RawJobRecordStore(Protocol):
    async def save_raw_records(self, *, batch_id: str, jobs: list[RawJob]) -> int: ...


class CompositeJobRepository:
    def __init__(
        self,
        *,
        raw_repository: RawJobRepository,
        normalized_repository: NormalizedJobRepository,
        raw_record_store: RawJobRecordStore | None = None,
    ) -> None:
        self._raw_repository = raw_repository
        self._normalized_repository = normalized_repository
        self._raw_record_store = raw_record_store

    async def save_raw_batch(
        self, *, source: str, batch_id: str, jobs: list[RawJob]
    ) -> Path:
        # The JSONL file stays the durable archive of the HTTP responses; the
        # PostgreSQL raw layer makes the same payloads queryable (dbt) and
        # re-processable. A failure of either fails the crawl, which Airflow
        # retries; both writes are idempotent.
        path = await self._raw_repository.save_raw_batch(
            source=source,
            batch_id=batch_id,
            jobs=jobs,
        )

        if self._raw_record_store is not None:
            await self._raw_record_store.save_raw_records(
                batch_id=batch_id,
                jobs=jobs,
            )

        return path

    async def upsert_many(self, jobs: list[NormalizedJob]) -> JobUpsertSummary:
        return await self._normalized_repository.upsert_many(jobs)
