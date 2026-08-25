import logging
from datetime import UTC, date
from pathlib import Path
from typing import Any

import aiofiles
import pendulum
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageException
from app.database import (
    JobModel,
    create_job_database_engine,
    create_job_session_factory,
)
from app.repositories import (
    PostgresNormalizedJobRepository,
)
from app.schemas.job import NormalizedJob
from app.schemas.job_storage import (
    JobUpsertSummary,
    JobVersionRecord,
)


logger = logging.getLogger(__name__)


async def import_jsonl_jobs(
    *,
    target_date: date,
    data_dir: Path,
    timezone_name: str = "Asia/Ho_Chi_Minh",
    source: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    selected_settings = settings or get_settings()

    if (
        selected_settings.job_storage_backend
        != "postgres"
    ):
        raise ValueError(
            "JOB_STORAGE_BACKEND must be postgres "
            "to import JSONL jobs."
        )

    normalized_directory = (
        data_dir / "normalized"
    )

    if not normalized_directory.is_dir():
        raise FileNotFoundError(
            "Normalized jobs directory was not found: "
            f"{normalized_directory}"
        )

    target_timezone = pendulum.timezone(
        timezone_name
    )

    normalized_source = (
        source.strip().casefold()
        if source is not None
        else None
    )

    jsonl_paths = sorted(
        normalized_directory.glob("*.jsonl")
    )

    if normalized_source is not None:
        jsonl_paths = [
            path
            for path in jsonl_paths
            if path.stem.casefold()
            == normalized_source
        ]

    latest_jobs: dict[str, NormalizedJob] = {}

    files_scanned = 0
    lines_scanned = 0
    invalid_lines = 0
    matched_versions = 0

    for path in jsonl_paths:
        files_scanned += 1

        try:
            async with aiofiles.open(
                path,
                mode="r",
                encoding="utf-8",
            ) as input_file:
                line_number = 0

                async for line in input_file:
                    line_number += 1
                    lines_scanned += 1

                    if not line.strip():
                        continue

                    try:
                        record = (
                            JobVersionRecord
                            .model_validate_json(line)
                        )
                    except ValidationError:
                        invalid_lines += 1

                        logger.warning(
                            "Invalid JSONL job record skipped",
                            extra={
                                "path": str(path),
                                "line_number": (
                                    line_number
                                ),
                            },
                        )
                        continue

                    job = record.job
                    crawled_at = job.crawled_at

                    if crawled_at.tzinfo is None:
                        crawled_at = (
                            crawled_at.replace(
                                tzinfo=UTC
                            )
                        )

                    local_date = (
                        crawled_at
                        .astimezone(target_timezone)
                        .date()
                    )

                    if local_date != target_date:
                        continue

                    matched_versions += 1

                    previous_job = latest_jobs.get(
                        job.job_id
                    )

                    if (
                        previous_job is None
                        or job.crawled_at
                        >= previous_job.crawled_at
                    ):
                        latest_jobs[job.job_id] = job

        except OSError as exc:
            raise StorageException(
                message=(
                    "A normalized JSONL file could "
                    f"not be read: {path}"
                ),
            ) from exc

    engine = create_job_database_engine(
        selected_settings
    )
    session_factory = create_job_session_factory(
        engine
    )

    try:
        existing_ids: set[str] = set()

        if latest_jobs:
            async with session_factory() as session:
                database_result = await session.execute(
                    select(JobModel.job_id).where(
                        JobModel.job_id.in_(
                            list(latest_jobs)
                        )
                    )
                )

                existing_ids = set(
                    database_result.scalars().all()
                )

        missing_jobs = [
            job
            for job_id, job
            in latest_jobs.items()
            if job_id not in existing_ids
        ]

        repository = (
            PostgresNormalizedJobRepository(
                session_factory
            )
        )

        if missing_jobs:
            summary = await repository.upsert_many(
                missing_jobs
            )
        else:
            summary = JobUpsertSummary()

    finally:
        await engine.dispose()

    return {
        "target_date": target_date.isoformat(),
        "timezone": timezone_name,
        "source": normalized_source,
        "files_scanned": files_scanned,
        "lines_scanned": lines_scanned,
        "invalid_lines": invalid_lines,
        "matched_versions": matched_versions,
        "unique_jobs_for_date": len(
            latest_jobs
        ),
        "already_present": len(existing_ids),
        "inserted_count": summary.inserted,
        "updated_count": summary.updated,
        "unchanged_count": summary.unchanged,
    }