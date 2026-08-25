import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings

from app.crawlers.registry import DEFAULT_JOB_SOURCE_REGISTRY, JobSourceRegistry
from app.database import create_job_database_engine, create_job_session_factory
from app.normalizers.job import JobNormalizer
from app.repositories import (
    CompositeJobRepository,
    JobRepository,
    LocalJsonlJobRepository,
    PostgresNormalizedJobRepository
)
from app.services.job_crawling import JobCrawlingService


SUPPORTED_SOURCES = frozenset(
    DEFAULT_JOB_SOURCE_REGISTRY.names
)

def build_job_repository(*, data_dir: Path, settings: Settings) -> tuple[JobRepository, AsyncEngine | None]:
    local_repository = LocalJsonlJobRepository(data_dir)

    if settings.job_storage_backend == "jsonl":
        return local_repository, None

    engine = create_job_database_engine(settings)
    session_factory = create_job_session_factory(engine)

    postgres_repository = PostgresNormalizedJobRepository(session_factory)
    composite_repository = CompositeJobRepository(
        raw_repository=local_repository,
        normalized_repository=postgres_repository
    )

    return composite_repository, engine
async def crawl_jobs(
    *,
    source_name: str,
    limit: int,
    cursor: str | None,
    data_dir: Path,
    timeout_seconds: float,
    registry: JobSourceRegistry = DEFAULT_JOB_SOURCE_REGISTRY,
    settings: Settings | None = None
) -> dict[str, Any]:
    selected_settings = settings or get_settings()
    normalized_source_name = source_name.strip().casefold()
    source_definition = registry.get(normalized_source_name)

    if limit < 1 or limit > source_definition.max_limit:
        raise ValueError(
            f"{normalized_source_name} limit must be between "
            f"1 and {source_definition.max_limit}."
        )

    repository, database_engine = (
        build_job_repository(
            data_dir=data_dir,
            settings=selected_settings,
        )
    )

    normalizer = JobNormalizer()

    timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 10.0),
    )

    headers = {
        "Accept": "application/json",
        "User-Agent": "multi-agent-job-assistant/1.0",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            source = registry.create(
                normalized_source_name,
                client
            )

            service = JobCrawlingService(
                source=source,
                normalizer=normalizer,
                repository=repository,
            )

            batch_id = build_batch_id(normalized_source_name)

            result = await service.crawl(
                batch_id=batch_id,
                cursor=cursor,
                limit=limit,
            )

        return result.model_dump(mode="json")
    
    finally:
        if database_engine is not None:
            await database_engine.dispose()


def build_batch_id(source_name: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{source_name}-{timestamp}"


def print_result(result: dict[str, Any]) -> None:
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


def print_error(error: Exception) -> None:
    payload = {
        "status": "failed",
        "error_type": type(error).__name__,
        "message": str(error),
    }

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )
