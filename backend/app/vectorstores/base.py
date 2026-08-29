from typing import Protocol

from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary
from app.schemas.job_search import JobVectorSearchHit

class JobVectorIndex(Protocol):
    async def ensure_collection(self) -> None:
        ...

    async def get_jobs_requiring_index(self, jobs: list[NormalizedJob]) -> list[NormalizedJob]:
        ...
        
    async def index_jobs(self, jobs: list[NormalizedJob]) -> JobIndexingSummary:
        ...

    async def search_jobs(self, *, query, limit: int) -> list[JobVectorSearchHit]:
        ...