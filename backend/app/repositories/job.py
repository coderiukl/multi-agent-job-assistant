import asyncio
import hashlib
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import aiofiles
from pydantic import ValidationError

from app.core.exceptions import StorageException
from app.schemas.job import NormalizedJob, RawJob
from app.schemas.job_storage import (
    JobUpsertResult,
    JobUpsertSummary,
    JobVersionRecord,
    JobWriteStatus,
)

LOGGER = logging.getLogger(__name__)


class RawJobRepository(Protocol):
    async def save_raw_batch(
        self,
        *,
        source: str,
        batch_id: str,
        jobs: list[RawJob]
    ) -> Path:
        ...

class NormalizedJobRepository(Protocol):
    async def upsert_many(self, jobs: list[NormalizedJob]):
        ...

class JobRepository(RawJobRepository, NormalizedJobRepository, Protocol):
   pass

class LocalJsonlJobRepository:
    def __init__(self, root_dir: Path,) -> None:
        self._root_dir = root_dir
        self._raw_dir = root_dir / "raw"
        self._normalized_dir = root_dir / "normalized"

        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._normalized_dir.mkdir(parents=True, exist_ok=True)

        self._write_lock = asyncio.Lock()

    async def save_raw_batch(
        self,
        *,
        source: str,
        batch_id: str,
        jobs: list[RawJob],
    ) -> Path:
        safe_source = self._safe_component(source)
        safe_batch_id = self._safe_component(batch_id)

        for job in jobs:
            if job.source.casefold() != source.casefold():
                raise StorageException(
                    message=(
                        "Raw job source does not match the batch source."
                    ),
                )

        date_partition = jobs[0].crawled_at.date().isoformat() if jobs else "empty"

        destination_dir = self._raw_dir / safe_source / date_partition
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination = destination_dir / f"{safe_batch_id}.jsonl"

        lines = [
            job.model_dump_json()
            for job in jobs
        ]

        async with self._write_lock:
            await self._atomic_write_lines(
                destination,
                lines,
            )

        return destination

    async def upsert_many(self, jobs: list[NormalizedJob]) -> JobUpsertSummary:
        jobs_by_source: dict[str, list[NormalizedJob]] = defaultdict(list)

        for job in jobs:
            jobs_by_source[job.source].append(job)

        all_results: list[JobUpsertResult] = []

        async with self._write_lock:
            for source, source_jobs in jobs_by_source.items():
                results = await self._upsert_source(
                    source=source,
                    jobs=source_jobs,
                )
                all_results.extend(results)

        return JobUpsertSummary(
            inserted=sum(
                result.status == JobWriteStatus.INSERTED
                for result in all_results
            ),
            updated=sum(
                result.status == JobWriteStatus.UPDATED
                for result in all_results
            ),
            unchanged=sum(
                result.status == JobWriteStatus.UNCHANGED
                for result in all_results
            ),
            results=all_results,
        )

    async def _upsert_source(
        self,
        *,
        source: str,
        jobs: list[NormalizedJob],
    ) -> list[JobUpsertResult]:
        safe_source = self._safe_component(source)
        destination = self._normalized_dir / f"{safe_source}.jsonl"

        existing_text, existing_jobs = await self._load_current_jobs(destination)

        unique_jobs = {
            job.job_id: job
            for job in jobs
        }

        new_versions: list[JobVersionRecord] = []
        results: list[JobUpsertResult] = []

        for job in unique_jobs.values():
            previous_job = existing_jobs.get(job.job_id)

            if previous_job is None:
                status = JobWriteStatus.INSERTED

                new_versions.append(
                    JobVersionRecord(
                        operation=status,
                        job=job,
                    )
                )

            elif previous_job.content_hash == job.content_hash:
                status = JobWriteStatus.UNCHANGED

            else:
                status = JobWriteStatus.UPDATED

                new_versions.append(
                    JobVersionRecord(
                        operation=status,
                        job=job,
                    )
                )

            results.append(
                JobUpsertResult(
                    job_id=job.job_id,
                    status=status,
                    previous_content_hash=(
                        previous_job.content_hash
                        if previous_job is not None
                        else None
                    ),
                    current_content_hash=job.content_hash,
                )
            )

            if status != JobWriteStatus.UNCHANGED:
                existing_jobs[job.job_id] = job

        if new_versions:
            await self._atomic_append_versions(
                destination=destination,
                existing_text=existing_text,
                versions=new_versions,
            )

        return results

    async def _load_current_jobs(
        self,
        path: Path,
    ) -> tuple[str, dict[str, NormalizedJob]]:
        try:
            async with aiofiles.open(
                path,
                encoding="utf-8",
            ) as input_file:
                content = await input_file.read()

        except FileNotFoundError:
            return "", {}

        except OSError as exc:
            raise StorageException(
                message="The normalized job file could not be read.",
            ) from exc

        current_jobs: dict[str, NormalizedJob] = {}
        valid_lines: list[str] = []
        skipped_corrupt_lines = 0

        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue

            try:
                record = JobVersionRecord.model_validate_json(line)

            except ValidationError as exc:
                if self._is_json_syntax_error(exc):
                    skipped_corrupt_lines += 1
                    LOGGER.warning(
                        "Skipping invalid JSON normalized job record: "
                        "path=%s, line=%s",
                        path,
                        line_number,
                    )
                    continue

                raise StorageException(
                    message="The normalized job file is corrupted.",
                ) from exc

            valid_lines.append(line)
            current_jobs[record.job.job_id] = record.job

        if skipped_corrupt_lines == 0:
            return content, current_jobs

        sanitized_content = "\n".join(valid_lines)
        if sanitized_content:
            sanitized_content += "\n"

        return sanitized_content, current_jobs

    async def _atomic_append_versions(
        self,
        *,
        destination: Path,
        existing_text: str,
        versions: list[JobVersionRecord],
    ) -> None:
        temporary_path = destination.with_suffix(".jsonl.part")

        try:
            async with aiofiles.open(
                temporary_path,
                mode="w",
                encoding="utf-8",
            ) as output:
                if existing_text:
                    await output.write(existing_text.rstrip("\n"))
                    await output.write("\n")

                for version in versions:
                    await output.write(version.model_dump_json())
                    await output.write("\n")

            await asyncio.to_thread(
                os.replace,
                temporary_path,
                destination,
            )

        except OSError as exc:
            raise StorageException(
                message="Normalized jobs could not be stored.",
            ) from exc

        finally:
            try:
                await asyncio.to_thread(
                    temporary_path.unlink,
                    missing_ok=True,
                )
            except OSError:
                pass

    async def _atomic_write_lines(self, destination: Path, lines: list[str]) -> None:
        temporary_path = destination.with_suffix(".jsonl.part")

        try:
            async with aiofiles.open(
                temporary_path,
                mode="w",
                encoding="utf-8",
            ) as output:
                for line in lines:
                    await output.write(line)
                    await output.write("\n")

            await asyncio.to_thread(
                os.replace,
                temporary_path,
                destination,
            )

        except OSError as exc:
            raise StorageException(
                message="Raw jobs could not be stored.",
            ) from exc

        finally:
            try:
                await asyncio.to_thread(
                    temporary_path.unlink,
                    missing_ok=True,
                )
            except OSError:
                pass

    @staticmethod
    def _safe_component(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")

        if not normalized:
            raise StorageException(
                message="Storage path component is invalid.",
            )

        if len(normalized) <= 100:
            return normalized

        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

        return f"{normalized[:80]}-{digest}"

    @staticmethod
    def _is_json_syntax_error(exc: ValidationError) -> bool:
        for error in exc.errors():
            if error.get("type") == "json_invalid":
                return True

        return False
