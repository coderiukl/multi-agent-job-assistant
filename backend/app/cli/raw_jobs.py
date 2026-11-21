"""Raw-layer commands.

``backfill-raw-jobs``  loads the JSONL raw archive (data/jobs/raw/<source>/
                       <date>/<batch_id>.jsonl) into ``raw.job_records``.
``reprocess-raw-jobs`` re-runs the source mappers and the normalizer over the
                       newest raw payload of every job and upserts the result,
                       so mapper/normalizer/skill-taxonomy changes reach the
                       ``jobs`` table without crawling the sources again.
"""

import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.crawlers.base import JobSource
from app.crawlers.registry import DEFAULT_JOB_SOURCE_REGISTRY, JobSourceRegistry
from app.database import create_job_database_engine, create_job_session_factory
from app.normalizers.job import JobNormalizer
from app.repositories.postgres_job import PostgresNormalizedJobRepository
from app.repositories.postgres_raw_job import PostgresRawJobRepository
from app.schemas.job import NormalizedJob, RawJob
from app.schemas.job_storage import JobWriteStatus

LOGGER = logging.getLogger(__name__)
NORMALIZATION_ERRORS = (KeyError, TypeError, ValueError, ValidationError)


def _require_postgres(settings: Settings) -> None:
    if settings.job_storage_backend != "postgres":
        raise ValueError("JOB_STORAGE_BACKEND must be postgres for raw-layer commands.")


async def backfill_raw_jobs(
    *,
    data_dir: Path,
    source: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    selected_settings = settings or get_settings()
    _require_postgres(selected_settings)

    raw_root = data_dir / "raw"
    if not raw_root.is_dir():
        raise ValueError(f"Raw job directory does not exist: {raw_root}")

    pattern = f"{source.casefold()}/*/*.jsonl" if source else "*/*/*.jsonl"
    files = sorted(raw_root.glob(pattern))

    engine = create_job_database_engine(selected_settings)
    repository = PostgresRawJobRepository(create_job_session_factory(engine))

    records = inserted = invalid_lines = 0

    try:
        for path in files:
            jobs, invalid = read_raw_jsonl(path)
            invalid_lines += invalid
            records += len(jobs)

            if jobs:
                inserted += await repository.save_raw_records(
                    batch_id=path.stem,
                    jobs=jobs,
                )
    finally:
        await engine.dispose()

    summary = {
        "source": source,
        "files": len(files),
        "records": records,
        "inserted": inserted,
        "already_present": records - inserted,
        "invalid_lines": invalid_lines,
    }
    LOGGER.info("Raw job backfill completed", extra=summary)
    return summary


def read_raw_jsonl(path: Path) -> tuple[list[RawJob], int]:
    jobs: list[RawJob] = []
    invalid = 0

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                jobs.append(RawJob.model_validate_json(line))
            except ValidationError:
                invalid += 1
                LOGGER.warning(
                    "Invalid raw job line skipped",
                    extra={"path": str(path), "line": line_number},
                )

    return jobs, invalid


def normalize_raw_jobs(
    *,
    raw_jobs: list[RawJob],
    source_for: Callable[[str], JobSource],
    normalizer: JobNormalizer,
) -> tuple[list[NormalizedJob], Counter[str]]:
    """Map + normalize like ``JobCrawlingService``; returns jobs and failures."""
    normalized: list[NormalizedJob] = []
    failures: Counter[str] = Counter()

    for raw_job in raw_jobs:
        try:
            candidate = source_for(raw_job.source).map_to_candidate(raw_job)
            normalized.append(normalizer.normalize(candidate))
        except NORMALIZATION_ERRORS as exc:
            failures[type(exc).__name__] += 1
            LOGGER.warning(
                "Raw job could not be re-normalized",
                extra={
                    "source": raw_job.source,
                    "source_job_id": raw_job.source_job_id,
                    "error_type": type(exc).__name__,
                },
            )

    return normalized, failures


async def reprocess_raw_jobs(
    *,
    source: str | None = None,
    batch_size: int = 500,
    index: bool = True,
    dry_run: bool = False,
    settings: Settings | None = None,
    registry: JobSourceRegistry = DEFAULT_JOB_SOURCE_REGISTRY,
) -> dict[str, Any]:
    selected_settings = settings or get_settings()
    _require_postgres(selected_settings)

    if source is not None:
        source = registry.get(source).name

    engine = create_job_database_engine(selected_settings)
    session_factory = create_job_session_factory(engine)
    raw_repository = PostgresRawJobRepository(session_factory)
    job_repository = PostgresNormalizedJobRepository(session_factory)
    normalizer = JobNormalizer()

    scanned = 0
    statuses: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    changed_job_ids: list[str] = []

    try:
        # Mappers never use the HTTP client; it only satisfies the factory.
        async with httpx.AsyncClient() as client:
            sources: dict[str, JobSource] = {}

            def source_for(name: str) -> JobSource:
                if name not in sources:
                    sources[name] = registry.create(name, client)
                return sources[name]

            async for raw_jobs in raw_repository.iter_latest_records(
                source=source,
                batch_size=batch_size,
            ):
                scanned += len(raw_jobs)
                normalized, batch_failures = normalize_raw_jobs(
                    raw_jobs=raw_jobs,
                    source_for=source_for,
                    normalizer=normalizer,
                )
                failures.update(batch_failures)

                summary = (
                    await job_repository.preview_upsert(normalized)
                    if dry_run
                    else await job_repository.upsert_many(normalized)
                )
                for result in summary.results:
                    statuses[result.status.value] += 1
                    if result.status != JobWriteStatus.UNCHANGED:
                        changed_job_ids.append(result.job_id)
    finally:
        await engine.dispose()

    index_result: dict[str, Any] | None = None

    if index and changed_job_ids and not dry_run:
        from app.cli.index_jobs import sync_job_index

        index_result = await sync_job_index(
            scan_batch_size=100,
            source=source,
            job_ids=changed_job_ids,
            settings=selected_settings,
        )

    result = {
        "source": source,
        "dry_run": dry_run,
        "scanned_raw_records": scanned,
        "inserted": statuses[JobWriteStatus.INSERTED.value],
        "updated": statuses[JobWriteStatus.UPDATED.value],
        "unchanged": statuses[JobWriteStatus.UNCHANGED.value],
        "failed": sum(failures.values()),
        "failures_by_type": dict(failures),
        "index": index_result,
    }
    LOGGER.info("Raw job reprocessing completed", extra={"source": source})
    return result
