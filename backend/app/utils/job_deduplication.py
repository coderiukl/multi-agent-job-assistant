import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime

from app.schemas.job import NormalizedJob

LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "ho chi minh": (
        "Ho Chi Minh",
        "Hồ Chí Minh",
        "HCM",
        "HCMC",
        "TP HCM",
        "TP.HCM",
        "TPHCM",
        "Sai Gon",
        "Sài Gòn",
    ),
    "ha noi": (
        "Ha Noi",
        "Hà Nội",
        "Hanoi",
        "HN",
    ),
    "da nang": (
        "Da Nang",
        "Đà Nẵng",
        "Danang",
    ),
}


def normalize_deduplication_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)

    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )

    lowercase = without_accents.casefold()

    return re.sub(r"[^a-z0-9]+", " ", lowercase).strip()


def normalize_job_location(value: str | None = None) -> str:
    if not value:
        return ""

    normalized = normalize_deduplication_text(value)

    replacements = (
        (
            r"\bho chi minh city\b",
            "ho chi minh",
        ),
        (
            r"\bthanh pho ho chi minh\b",
            "ho chi minh",
        ),
        (
            r"\btp hcm\b|\btphcm\b|\bhcmc\b|\bhcm\b|\bsai gon\b",
            "ho chi minh",
        ),
        (
            r"\bha noi city\b|\bthanh pho ha noi\b|\bhn\b",
            "ha noi",
        ),
        (
            r"\bda nang city\b|\bthanh pho da nang\b|\bdanang\b",
            "da nang",
        ),
        (
            r"\bviet nam\b|\bvietnam\b",
            "",
        ),
    )

    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def build_job_location_keys(value: str | None) -> list[str]:
    normalized = normalize_job_location(value)

    if not normalized:
        return []

    keys = [normalized]

    for canonical_key in LOCATION_ALIASES:
        if canonical_key in normalized and canonical_key not in keys:
            keys.append(canonical_key)

    return keys


def build_job_location_search_terms(value: str) -> list[str]:
    normalized = normalize_job_location(value)
    terms = [value]

    for canonical_key, aliases in LOCATION_ALIASES.items():
        if canonical_key in normalized:
            terms.extend(aliases)

    return list(dict.fromkeys(terms))


def build_job_deduplication_key(job: NormalizedJob) -> str:
    normalized_title = normalize_deduplication_text(job.title)
    normalized_company = normalize_deduplication_text(job.company)
    normalized_location = normalize_job_location(job.location)

    return "|".join(
        [
            normalized_title,
            normalized_company,
            normalized_location,
        ]
    )


def deduplicate_jobs(jobs: Iterable[NormalizedJob]) -> list[NormalizedJob]:
    preferred_jobs: dict[str, NormalizedJob] = {}

    for job in jobs:
        key = build_job_deduplication_key(job)
        current = preferred_jobs.get(key)

        if current is None:
            preferred_jobs[key] = job
            continue

        if _is_preferred_job(candidate=job, current=current):
            preferred_jobs[key] = job

    return list(preferred_jobs.values())


def _is_preferred_job(*, candidate: NormalizedJob, current: NormalizedJob) -> bool:
    return _job_quality(candidate) > _job_quality(current)


def _job_quality(job: NormalizedJob) -> tuple[int, int, int, float, str]:
    salary_information = int(job.salary_min is not None or job.salary_max is not None)

    timestamp_source = job.posted_at or job.crawled_at

    return (
        len(job.description),
        len(job.skills),
        salary_information,
        _ensure_utc(timestamp_source).timestamp(),
        job.job_id,
    )


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
