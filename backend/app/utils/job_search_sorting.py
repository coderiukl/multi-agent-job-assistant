from datetime import UTC, datetime

from app.schemas.job import SeniorityLevel
from app.schemas.job_search import JobSearchHit, JobSearchSort


def sort_job_search_hits(
    hits: list[JobSearchHit],
    sort: JobSearchSort,
) -> list[JobSearchHit]:
    if sort == JobSearchSort.NEWEST:
        return sorted(
            hits,
            key=lambda hit: (
                hit.job.seniority_level != SeniorityLevel.UNKNOWN,
                _job_timestamp(hit.job.posted_at, hit.job.crawled_at),
                hit.score.final,
                hit.job.job_id,
            ),
            reverse=True,
        )

    return sorted(
        hits,
        key=lambda hit: (
            hit.job.seniority_level != SeniorityLevel.UNKNOWN,
            hit.score.final,
            _job_timestamp(hit.job.posted_at, hit.job.crawled_at),
            hit.job.job_id,
        ),
        reverse=True,
    )


def _job_timestamp(posted_at: datetime | None, crawled_at: datetime) -> float:
    value = posted_at or crawled_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)

    return value.timestamp()
