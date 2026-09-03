from collections.abc import Iterable

from app.schemas.cv_profile import CVProfile
from app.schemas.job import normalize_single_line
from app.schemas.job_search_context import JobSearchContext

def _unique_values(values: Iterable[str | None], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue

        normalized = normalize_single_line(value)
        key = normalized.casefold()

        if not normalize_single_line or key in seen:
            continue

        seen.add(key)
        result.append(normalized)

        if len(result) >= limit:
            break

    return result

def _education_background(profile: CVProfile) -> list[str]:
    values: list[str] = []

    for education in profile.educations:
        parts = [part for part in [education.degree, education.field_of_study] if part]

        if parts:
            values.append(" - ".join(parts))

    return _unique_values(values, limit=10)

def build_job_search_context(profile: CVProfile) -> JobSearchContext:
    if profile is None:
        return None

    context = JobSearchContext(
        professional_summary=profile.professional_summary[:2000] if profile.professional_summary else None,
        skills=_unique_values(profile.skills, limit=50),
        recent_job_titles=_unique_values((experience.job_title for experience in profile.work_experiences), limit=10),
        education_background=_education_background(profile),
        project_technologies=_unique_values(
            (
                technology 
                for project in profile.projects 
                for technology in project.technologies
            ),
            limit=50,
        ),
        location=profile.personal_information.location,
    )

    return context if context.has_professional_data else None
