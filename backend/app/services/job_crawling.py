import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from app.crawlers.base import JobSource
from app.normalizers.job import JobNormalizer
from app.repositories.job import JobRepository
from app.schemas.job import NormalizedJob
from app.schemas.job_crawling import JobCrawlResult, JobNormalizationFailure

logger = logging.getLogger(__name__)

MAX_CRAWL_LIMIT = 100


class JobCrawlingService:
    def __init__(
        self,
        *,
        source: JobSource,
        normalizer: JobNormalizer,
        repository: JobRepository,
    ) -> None:
        self._source = source
        self._normalizer = normalizer
        self._repository = repository

    async def crawl_page(
        self,
        *,
        batch_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> JobCrawlResult:
        return await self.crawl(
            batch_id=batch_id or self._build_batch_id(),
            cursor=cursor,
            limit=limit,
        )

    async def crawl(
        self,
        *,
        batch_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> JobCrawlResult:
        self._validate_request(
            batch_id=batch_id,
            limit=limit,
        )

        source_name = self._source.source_name

        logger.info(
            "Job crawling batch started",
            extra={
                "source": source_name,
                "batch_id": batch_id,
                "cursor": cursor,
                "limit": limit,
            },
        )

        page = await self._source.fetch_page(
            cursor=cursor,
            limit=limit,
        )

        raw_file_path = await self._repository.save_raw_batch(
            source=source_name,
            batch_id=batch_id,
            jobs=page.items,
        )

        normalized_jobs: list[NormalizedJob] = []
        failures: list[JobNormalizationFailure] = []

        for raw_job in page.items:
            try:
                candidate = self._source.map_to_candidate(raw_job)
                normalized_job = self._normalizer.normalize(candidate)

                normalized_jobs.append(normalized_job)

            except (
                KeyError,
                TypeError,
                ValueError,
                ValidationError,
            ) as exc:
                logger.warning(
                    "Job record could not be normalized",
                    extra={
                        "source": source_name,
                        "source_job_id": raw_job.source_job_id,
                        "error_type": type(exc).__name__,
                    },
                    exc_info=True,
                )

                failures.append(
                    JobNormalizationFailure(
                        source_job_id=raw_job.source_job_id,
                        error_type=type(exc).__name__,
                    )
                )

        upsert_summary = await self._repository.upsert_many(normalized_jobs)

        result = JobCrawlResult(
            source=source_name,
            batch_id=batch_id,
            fetched_count=len(page.items),
            normalized_count=len(normalized_jobs),
            failed_count=len(failures),
            inserted_count=upsert_summary.inserted,
            updated_count=upsert_summary.updated,
            unchanged_count=upsert_summary.unchanged,
            raw_file_path=str(raw_file_path),
            normalized_job_ids=[
                result.job_id
                for result in upsert_summary.results
            ],
            current_cursor=cursor,
            next_cursor=page.next_cursor,
            failures=failures,
        )

        logger.info(
            "Job crawling batch completed",
            extra={
                "source": source_name,
                "batch_id": batch_id,
                "fetched_count": result.fetched_count,
                "normalized_count": result.normalized_count,
                "failed_count": result.failed_count,
                "inserted_count": result.inserted_count,
                "updated_count": result.updated_count,
                "unchanged_count": result.unchanged_count,
                "next_cursor": result.next_cursor,
            },
        )

        return result

    @staticmethod
    def _validate_request(*, batch_id: str, limit: int) -> None:
        if not batch_id.strip():
            raise ValueError("batch_id must not be empty.")

        if limit < 1 or limit > MAX_CRAWL_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_CRAWL_LIMIT}."
            )

    def _build_batch_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{self._source.source_name}-{timestamp}"
