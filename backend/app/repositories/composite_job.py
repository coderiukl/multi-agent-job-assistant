from pathlib import Path

from app.repositories.job import  NormalizedJobRepository, RawJobRepository
from app.schemas.job import NormalizedJob, RawJob
from app.schemas.job_storage import JobUpsertSummary

class CompositeJobRepository:
    def __init__(
        self, 
        *, 
        raw_repository: RawJobRepository,
        normalized_repository: NormalizedJobRepository
    ) -> None:
        self._raw_repository = raw_repository
        self._normalized_repository = normalized_repository

    async def save_raw_batch(self, *, source: str, batch_id: str, jobs: list[RawJob]) -> Path:
        return await self._raw_repository.save_raw_batch(
            source=source,
            batch_id=batch_id,
            jobs=jobs,
        )

    async def upsert_many(self, jobs: list[NormalizedJob]) -> JobUpsertSummary:
        return await self._normalized_repository.upsert_many(jobs)
    
