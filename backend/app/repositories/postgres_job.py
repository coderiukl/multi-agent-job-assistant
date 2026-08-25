from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import StorageException
from app.database.models import JobModel
from app.database.session import JobSessionFactory
from app.schemas.job import NormalizedJob
from app.schemas.job_storage import (
    JobUpsertResult,
    JobUpsertSummary,
    JobWriteStatus,
)

class PostgresNormalizedJobRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def upsert_many(self, jobs: list[NormalizedJob]) -> JobUpsertSummary:
        unique_jobs = self._deduplicate_batch(jobs)

        if not unique_jobs:
            return JobUpsertSummary()

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing_hashes = (
                        await self._load_existing_hashes(
                            session=session,
                            job_ids=list(unique_jobs)
                        )
                    )

                    results = self._build_results(
                        jobs=list(unique_jobs.values()),
                        existing_hashes=existing_hashes,
                    )

                    changed_jobs = [
                        job for job in unique_jobs.values()
                        if existing_hashes.get(job.job_id) != job.content_hash
                    ]

                    if changed_jobs: 
                        await session.execute(
                            self._build_upsert_statement(
                                changed_jobs
                            )
                        )

        except SQLAlchemyError as exc:
            raise StorageException(
                message=(
                    "Normalized jobs could not be stored "
                    "in PostgreSQL."
                )
            ) from exc

        return JobUpsertSummary(
            inserted=sum(
                result.status == JobWriteStatus.INSERTED
                for result in results
            ),
            updated=sum(
                result.status == JobWriteStatus.UPDATED
                for result in results
            ),
            unchanged=sum(
                result.status == JobWriteStatus.UNCHANGED
                for result in results
            ),
            results=results,
        )

    async def _load_existing_hashes(self, *, session: Any, job_ids: list[str]) -> dict[str, str]:
        statement = (
            select(
                JobModel.job_id,
                JobModel.content_hash,
            ).where(JobModel.job_id.in_(job_ids))
        )

        database_result = await session.execute(statement)

        return {
            row.job_id: row.content_hash
            for row in database_result
        }

    @staticmethod
    def _deduplicate_batch(jobs: Sequence[NormalizedJob]) -> dict[str, NormalizedJob]:
        return {
            job.job_id: job
            for job in jobs
        }

    @staticmethod
    def _build_results(*, jobs: list[NormalizedJob], existing_hashes: dict[str, str]) -> list[JobUpsertResult]:
        results: list[JobUpsertResult] = []

        for job in jobs:
            previous_hash = existing_hashes.get(job.job_id)

            if previous_hash is None:
                status = JobWriteStatus.INSERTED
            elif previous_hash == job.content_hash:
                status = JobWriteStatus.UNCHANGED
            else:
                status = JobWriteStatus.UPDATED

            results.append(
                JobUpsertResult(
                    job_id=job.job_id,
                    status=status,
                    previous_content_hash=previous_hash,
                    current_content_hash=job.content_hash,
                )
            )

        return results

    @staticmethod
    def _build_upsert_statement(jobs: list[NormalizedJob]) -> Any:
        rows = [PostgresNormalizedJobRepository._to_database_row(job) for job in jobs]

        statement = insert(JobModel).values(rows)
        excluded = statement.excluded

        return statement.on_conflict_do_update(
            index_elements=[JobModel.job_id],
            set_={
                "title": excluded.title,
                "company": excluded.company,
                "description": excluded.description,
                "location": excluded.location,
                "employment_type": excluded.employment_type,
                "work_mode": excluded.work_mode,
                "seniority_level": excluded.seniority_level,
                "skills": excluded.skills,
                "salary_min": excluded.salary_min,
                "salary_max": excluded.salary_max,
                "salary_period": excluded.salary_period,
                "salary_currency": excluded.salary_currency,
                "posted_at": excluded.posted_at,
                "expires_at": excluded.expires_at,
                "source": excluded.source,
                "source_job_id": excluded.source_job_id,
                "source_url": excluded.source_url,
                "crawled_at": excluded.crawled_at,
                "source_metadata": excluded.source_metadata,
                "content_hash": excluded.content_hash,
                "updated_at": func.now(),
            },
            where=JobModel.content_hash.is_distinct_from(
                excluded.content_hash
            ),
        )
    @staticmethod
    def _to_database_row(job: NormalizedJob) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "location": job.location,
            "employment_type": (
                job.employment_type.value
                if job.employment_type is not None
                else None
            ),
            "work_mode": job.work_mode.value,
            "seniority_level": job.seniority_level.value,
            "skills": job.skills,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_period": job.salary_period.value,
            "salary_currency": job.salary_currency,
            "posted_at": job.posted_at,
            "expires_at": job.expires_at,
            "source": job.source,
            "source_job_id": job.source_job_id,
            "source_url": str(job.source_url),
            "crawled_at": job.crawled_at,
            "source_metadata": job.source_metadata,
            "content_hash": job.content_hash,
        }
        
