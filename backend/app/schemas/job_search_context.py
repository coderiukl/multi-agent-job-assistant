from pydantic import Field, field_validator

from app.schemas.job import JobSchema, normalize_multiline, normalize_single_line

class JobSearchContext(JobSchema):
    professional_summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list, max_length=50)
    recent_job_titles: list[str] = Field(default_factory=list, max_length=10)
    education_background: list[str] = Field(default_factory=list, max_length=10)
    project_technologies: list[str] = Field(default_factory=list, max_length=50)
    location: str | None = Field(default=None, max_length=2000)

    @field_validator("professional_summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_multiline(value)

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_single_line(value)

    @field_validator(
        "skills", 
        "recent_job_titles", 
        "education_background",
        "project_technologies",
    )
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            item = normalize_single_line(value)
            key = item.casefold()

            if not item or key in seen:
                continue

            seen.add(key)
            normalized.append(item)

        return normalized

    @property
    def has_professional_data(self) -> bool:
        return any(
            [
                self.professional_summary,
                self.skills,
                self.recent_job_titles,
                self.education_background,
                self.project_technologies,
            ]
        )
        

