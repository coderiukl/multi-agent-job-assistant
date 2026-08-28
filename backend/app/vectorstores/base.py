from typing import Protocol

from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary

class JobVectorIndex(Protocol):
    async def ensure_collection(self) -> None:
        ...

    async def get_jobs_requiring_index(self, jobs: list[NormalizedJob]) -> list[NormalizedJob]:
        ...
        
    async def index_jobs(self, jobs: list[NormalizedJob]) -> JobIndexingSummary:
        ...