import hashlib
import re
import unicodedata
from collections.abc import Iterable

from app.schemas.cv_profile import CVProfile
from app.schemas.job import SeniorityLevel, normalize_single_line
from app.schemas.job_matching import (
    CVEvidenceItem,
    JobMatchTarget,
    JobRequirement,
    MatchDimension,
)

DIMENSION_KEYWORDS: tuple[tuple[MatchDimension, tuple[str, ...]], ...] = (
    (
        MatchDimension.LANGUAGES_AND_CERTIFICATIONS,
        (
            "certificate",
            "certification",
            "certified",
            "english",
            "language",
            "chung chi",
            "tieng anh",
            "ngon ngu",
        ),
    ),
    (
        MatchDimension.EDUCATION,
        (
            "degree",
            "bachelor",
            "master",
            "university",
            "education",
            "dai hoc",
            "cu nhan",
            "bang cap",
            "hoc van",
        ),
    ),
    (
        MatchDimension.EXPERIENCE,
        (
            "experience",
            "years",
            "year of",
            "senior",
            "junior",
            "intern",
            "kinh nghiem",
            "thuc tap",
        ),
    ),
    (
        MatchDimension.PROJECTS,
        ("project", "portfolio", "github", "du an"),
    ),
    (
        MatchDimension.TECHNICAL_SKILLS,
        (
            "skill",
            "knowledge",
            "proficient",
            "technology",
            "framework",
            "tool",
            "ky nang",
            "thanh thao",
            "cong nghe",
            "cong cu",
            "kien thuc",
        ),
    ),
)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).casefold().encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return folded.replace("đ", "d")


def _unique_text(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue
        normalized = normalize_single_line(value)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)

    return result


def build_job_requirements(job: JobMatchTarget) -> list[JobRequirement]:
    candidates: list[tuple[MatchDimension, str]] = [
        (MatchDimension.TECHNICAL_SKILLS, skill) for skill in job.skills
    ]

    if job.seniority_level != SeniorityLevel.UNKNOWN:
        candidates.append(
            (
                MatchDimension.EXPERIENCE,
                f"Seniority level: {job.seniority_level.value}",
            )
        )

    segments = re.split(r"(?:\r?\n|[.!?;]+)", job.description)
    for text in _unique_text(segments):
        lowered = _fold_text(text)
        for dimension, keywords in DIMENSION_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                candidates.append((dimension, text[:1000]))
                break

    requirements: list[JobRequirement] = []
    seen: set[tuple[MatchDimension, str]] = set()
    for dimension, text in candidates:
        normalized = normalize_single_line(text)
        key = (dimension, normalized.casefold())
        if not normalized or key in seen:
            continue
        seen.add(key)
        requirements.append(
            JobRequirement(
                requirement_id=_stable_id("req", dimension.value, normalized),
                dimension=dimension,
                text=normalized,
            )
        )
        if len(requirements) >= 100:
            break

    return requirements


def build_cv_evidence_catalog(profile: CVProfile) -> list[CVEvidenceItem]:
    candidates: list[tuple[MatchDimension, str, str]] = []

    for index, skill in enumerate(profile.skills):
        candidates.append((MatchDimension.TECHNICAL_SKILLS, f"skills[{index}]", skill))

    for index, item in enumerate(profile.work_experiences):
        prefix = f"work_experiences[{index}]"
        candidates.append(
            (
                MatchDimension.EXPERIENCE,
                f"{prefix}.job_title",
                item.job_title or "",
            )
        )
        for field_name, values in (
            ("responsibilities", item.responsibilities),
            ("achievements", item.achievements),
        ):
            for value_index, value in enumerate(values):
                candidates.append(
                    (
                        MatchDimension.EXPERIENCE,
                        f"{prefix}.{field_name}[{value_index}]",
                        value,
                    )
                )

    for index, item in enumerate(profile.educations):
        text = " - ".join(
            value
            for value in (item.degree, item.field_of_study, item.institution)
            if value
        )
        candidates.append((MatchDimension.EDUCATION, f"educations[{index}]", text))

    for index, item in enumerate(profile.projects):
        prefix = f"projects[{index}]"
        candidates.append(
            (
                MatchDimension.PROJECTS,
                prefix,
                " - ".join(value for value in (item.name, item.description) if value),
            )
        )
        for technology_index, technology in enumerate(item.technologies):
            candidates.append(
                (
                    MatchDimension.TECHNICAL_SKILLS,
                    f"{prefix}.technologies[{technology_index}]",
                    technology,
                )
            )

    for index, item in enumerate(profile.certifications):
        candidates.append(
            (
                MatchDimension.LANGUAGES_AND_CERTIFICATIONS,
                f"certifications[{index}]",
                " - ".join(value for value in (item.name, item.issuer) if value),
            )
        )

    for index, item in enumerate(profile.languages):
        candidates.append(
            (
                MatchDimension.LANGUAGES_AND_CERTIFICATIONS,
                f"languages[{index}]",
                " - ".join(value for value in (item.name, item.proficiency) if value),
            )
        )

    catalog: list[CVEvidenceItem] = []
    seen: set[tuple[MatchDimension, str, str]] = set()
    for dimension, field_path, text in candidates:
        normalized = normalize_single_line(text)
        key = (dimension, field_path, normalized.casefold())
        if not normalized or key in seen:
            continue
        seen.add(key)
        catalog.append(
            CVEvidenceItem(
                cv_evidence_id=_stable_id(
                    "cv", dimension.value, field_path, normalized
                ),
                dimension=dimension,
                field_path=field_path,
                text=normalized[:1000],
            )
        )
        if len(catalog) >= 500:
            break

    return catalog
