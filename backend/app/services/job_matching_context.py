import hashlib
import re
import unicodedata
from collections.abc import Iterable
from datetime import date

from app.schemas.cv_profile import CVProfile
from app.schemas.job import SeniorityLevel, normalize_single_line
from app.schemas.job_matching import (
    MAX_MATCH_REQUIREMENTS,
    CVEvidenceItem,
    JobMatchTarget,
    JobRequirement,
    MatchDimension,
)

# Keywords are matched on accent-folded, lower-cased text as whole words
# (an optional plural "s"/"es" is allowed), so "intern" does not match
# "international" (BUG-004). Dimensions are checked in this order.
DIMENSION_KEYWORDS: tuple[tuple[MatchDimension, tuple[str, ...]], ...] = (
    (
        MatchDimension.LANGUAGES_AND_CERTIFICATIONS,
        (
            "certificate",
            "certification",
            "certified",
            "english",
            "language",
            "ielts",
            "toeic",
            "toefl",
            "japanese",
            "jlpt",
            "chung chi",
            "tieng anh",
            "tieng nhat",
            "ngon ngu",
            "ngoai ngu",
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
            "graduate",
            "dai hoc",
            "cu nhan",
            "bang cap",
            "hoc van",
            "tot nghiep",
        ),
    ),
    (
        MatchDimension.EXPERIENCE,
        (
            "experience",
            "experienced",
            "year",
            "senior",
            "junior",
            "intern",
            "internship",
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
            "proficiency",
            "technology",
            "technologies",
            "framework",
            "tool",
            "stack",
            "ky nang",
            "thanh thao",
            "cong nghe",
            "cong cu",
            "kien thuc",
        ),
    ),
)


def _keyword_regex(keywords: Iterable[str]) -> re.Pattern[str]:
    alternatives = "|".join(
        re.escape(keyword).replace(r"\ ", r"\s+")
        for keyword in sorted(keywords, key=len, reverse=True)
    )
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?:e?s)?(?![a-z0-9])")


_DIMENSION_PATTERNS: tuple[tuple[MatchDimension, re.Pattern[str]], ...] = tuple(
    (dimension, _keyword_regex(keywords)) for dimension, keywords in DIMENSION_KEYWORDS
)

# "programming language", "ngôn ngữ lập trình"... describe a technical skill,
# not a spoken language (BUG-004).
_TECHNICAL_LANGUAGE_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:(?:programming|scripting|query|markup|coding)\s+languages?"
    r"|ngon\s+ngu\s+(?:lap\s+trinh|truy\s+van|kich\s+ban))(?![a-z0-9])"
)

# A line introduced by a requirements header ("Yêu cầu: Python, FastAPI")
# is a requirement even when it contains no dimension keyword (BUG-003).
_REQUIREMENT_HEADER_PATTERN = re.compile(
    r"^(?:yeu\s+cau(?:\s+cong\s+viec)?|requirements?|required|qualifications?"
    r"|must[\s-]+haves?|nice[\s-]+to[\s-]+haves?|tech(?:nical)?\s+stack|stack"
    r"|technologies|cong\s+nghe|tieu\s+chuan|dieu\s+kien|uu\s+tien)\s*[:\-–—]"
)
_LIST_SEPARATOR_PATTERN = re.compile(r"\s*[,/|]\s*")

# Only split sentences on punctuation followed by whitespace (or the end),
# so "2.5 năm", "Node.js" and "ASP.NET" stay intact (BUG-010).
_SEGMENT_SPLIT_PATTERN = re.compile(r"\r?\n|[•●▪◦·]|[.!?;]+(?=\s|$)")
_BULLET_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*+>]+|\(?\d{1,2}[.)])\s+")
_HAS_LETTER_PATTERN = re.compile(r"[^\W\d_]")


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


def split_job_description(description: str) -> list[str]:
    """Split a JD into requirement-sized lines/bullets/sentences."""
    segments: list[str] = []
    for raw in _SEGMENT_SPLIT_PATTERN.split(description):
        text = _BULLET_PREFIX_PATTERN.sub("", raw or "").strip(" \t-–—:")
        if text and _HAS_LETTER_PATTERN.search(text):
            segments.append(text)
    return _unique_text(segments)


def classify_requirement(text: str) -> MatchDimension | None:
    """Return the dimension of a JD line, or None when it is not recognised."""
    folded = _fold_text(text)
    has_technical_language = bool(_TECHNICAL_LANGUAGE_PATTERN.search(folded))
    without_technical_language = _TECHNICAL_LANGUAGE_PATTERN.sub(" ", folded)

    for dimension, pattern in _DIMENSION_PATTERNS:
        if pattern.search(without_technical_language):
            return dimension

    if has_technical_language:
        return MatchDimension.TECHNICAL_SKILLS
    return None


def _looks_like_skill_list(text: str) -> bool:
    """"Python, FastAPI, Docker" – short, mostly technology-like items.

    Technology names are rarely written with Vietnamese diacritics, which
    keeps benefit lines such as "Lương cao, thưởng tháng 13" out.
    """
    body = text.split(":", 1)[1] if ":" in text else text
    items = [
        item.strip() for item in _LIST_SEPARATOR_PATTERN.split(body) if item.strip()
    ]
    if len(items) < 2 or any(len(item.split()) > 3 for item in items):
        return False
    plain = sum(1 for item in items if _fold_text(item) == item.casefold())
    return plain * 2 > len(items)


def _is_unlabelled_requirement(text: str, *, allow_skill_lists: bool) -> bool:
    if _REQUIREMENT_HEADER_PATTERN.search(_fold_text(text)):
        return True
    return allow_skill_lists and _looks_like_skill_list(text)


def _limit_candidates(
    candidates: list[tuple[MatchDimension, str]], limit: int
) -> list[tuple[MatchDimension, str]]:
    """Keep at most ``limit`` candidates without starving any dimension.

    When a job has more requirements than the agent can assess in one call,
    take them round-robin across dimensions (preserving order inside each
    dimension) instead of truncating the tail, which would drop every
    experience/education line of a job with many listed skills.
    """
    if len(candidates) <= limit:
        return candidates

    by_dimension: dict[MatchDimension, list[tuple[MatchDimension, str]]] = {}
    for candidate in candidates:
        by_dimension.setdefault(candidate[0], []).append(candidate)

    selected: set[int] = set()
    positions = {id(candidate): index for index, candidate in enumerate(candidates)}
    queues = [list(items) for items in by_dimension.values()]
    while len(selected) < limit and any(queues):
        for queue in queues:
            if queue and len(selected) < limit:
                selected.add(positions[id(queue.pop(0))])

    return [candidates[index] for index in sorted(selected)]


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

    segments = split_job_description(job.description)
    # Structured skills already cover the skill list of crawled jobs; plain
    # comma lists are only trusted for pasted JDs without them.
    allow_skill_lists = not job.skills
    for text in segments:
        dimension = classify_requirement(text)
        if dimension is None and _is_unlabelled_requirement(
            text, allow_skill_lists=allow_skill_lists
        ):
            # Skill lists and "Requirements: ..." lines without a dimension
            # keyword are technical requirements (BUG-003).
            dimension = MatchDimension.TECHNICAL_SKILLS
        if dimension is not None:
            candidates.append((dimension, text[:1000]))

    if not candidates:
        # Never score a pasted JD against zero requirements (which always gives
        # overall_score 0): fall back to every JD line as a requirement.
        candidates = [
            (MatchDimension.TECHNICAL_SKILLS, text[:1000]) for text in segments
        ]

    unique: list[tuple[MatchDimension, str]] = []
    seen: set[tuple[MatchDimension, str]] = set()
    for dimension, text in candidates:
        normalized = normalize_single_line(text)
        key = (dimension, normalized.casefold())
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append((dimension, normalized))

    return [
        JobRequirement(
            requirement_id=_stable_id("req", dimension.value, text),
            dimension=dimension,
            text=text,
        )
        for dimension, text in _limit_candidates(unique, MAX_MATCH_REQUIREMENTS)
    ]


TOTAL_YEARS_FIELD_PATH = "work_experiences.total_years"

_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_MONTH_FIRST_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*((?:19|20)\d{2})(?!\d)")
_YEAR_FIRST_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[/.\-]\s*(\d{1,2})(?!\d)")


def _parse_month_index(value: str | None) -> int | None:
    """Return months since year 0 for a free-form date, or None if unparseable."""
    if not value:
        return None
    match = _MONTH_FIRST_RE.search(value)
    if match and 1 <= int(match.group(1)) <= 12:
        return int(match.group(2)) * 12 + int(match.group(1)) - 1
    match = _YEAR_FIRST_RE.search(value)
    if match and 1 <= int(match.group(2)) <= 12:
        return int(match.group(1)) * 12 + int(match.group(2)) - 1
    match = _YEAR_RE.search(value)
    if match:
        return int(match.group(1)) * 12
    return None


def calculate_total_experience_years(
    profile: CVProfile, *, today: date | None = None
) -> float | None:
    """Sum work experience in years, merging overlapping roles.

    Roles with an unparseable start or end date are ignored rather than guessed.
    """
    today = today or date.today()
    now_index = today.year * 12 + today.month - 1
    intervals: list[tuple[int, int]] = []

    for item in profile.work_experiences:
        start = _parse_month_index(item.start_date)
        end = now_index if item.is_current else _parse_month_index(item.end_date)
        if start is None or end is None or end <= start:
            continue
        intervals.append((start, min(end, now_index)))

    if not intervals:
        return None

    intervals.sort()
    total_months = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total_months += current_end - current_start
            current_start, current_end = start, end
    total_months += current_end - current_start

    return round(total_months / 12, 1) if total_months > 0 else None


def build_cv_evidence_catalog(
    profile: CVProfile, *, today: date | None = None
) -> list[CVEvidenceItem]:
    candidates: list[tuple[MatchDimension, str, str]] = []

    total_years = calculate_total_experience_years(profile, today=today)
    if total_years is not None:
        candidates.append(
            (
                MatchDimension.EXPERIENCE,
                TOTAL_YEARS_FIELD_PATH,
                f"Tổng thời gian kinh nghiệm làm việc: khoảng {total_years:g} năm "
                "(tính từ ngày bắt đầu và kết thúc trong CV)",
            )
        )

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
