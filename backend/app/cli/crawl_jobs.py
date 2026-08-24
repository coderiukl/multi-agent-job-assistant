import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.crawlers.sources.himalayas import HimalayasJobSource
from app.normalizers.job import JobNormalizer
from app.repositories.job import LocalJsonlJobRepository
from app.services.job_crawling import JobCrawlingService


SUPPORTED_SOURCES = {"himalayas"}


async def crawl_jobs(
    *,
    source_name: str,
    limit: int,
    cursor: str | None,
    data_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    if source_name not in SUPPORTED_SOURCES:
        raise ValueError(
            f"Unsupported source: {source_name}. "
            f"Supported sources: {sorted(SUPPORTED_SOURCES)}"
        )

    if limit < 1 or limit > 20:
        raise ValueError("Himalayas limit must be between 1 and 20")

    repository = LocalJsonlJobRepository(data_dir)
    normalizer = JobNormalizer()

    timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=10.0,
    )

    headers = {
        "Accept": "application/json",
        "User-Agent": "multi-agent-job-assistant/1.0",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    ) as client:
        source = HimalayasJobSource(client)

        service = JobCrawlingService(
            source=source,
            normalizer=normalizer,
            repository=repository,
        )

        batch_id = build_batch_id(source_name)

        result = await service.crawl(
            batch_id=batch_id,
            cursor=cursor,
            limit=limit,
        )

    return result.model_dump(mode="json")


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
