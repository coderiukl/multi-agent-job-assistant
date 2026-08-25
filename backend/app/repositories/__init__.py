from app.repositories.cv import CVRepository, LocalJsonCVRepository
from app.repositories.job import JobRepository, LocalJsonlJobRepository, NormalizedJobRepository, RawJobRepository
from app.repositories.composite_job import CompositeJobRepository
from app.repositories.postgres_job import PostgresNormalizedJobRepository

__all__ = [
    "CVRepository",
    "LocalJsonCVRepository",
    "RawJobRepository",
    "NormalizedJobRepository",
    "JobRepository",
    "LocalJsonlJobRepository",
    "PostgresNormalizedJobRepository",
    "CompositeJobRepository",
]
