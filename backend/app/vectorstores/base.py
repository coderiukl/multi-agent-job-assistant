from typing import Protocol

from app.schemas.job import NormalizedJob
from app.schemas.job_index import JobIndexingSummary

class JobVectorIndex(Protocol):
    async def ensure_collection(self) -> None:
        ...

    async def index_jobs(self, jobs: list[NormalizedJob]) -> JobIndexingSummary:
        ...