from pydantic import BaseModel, ConfigDict, Field

class CVSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PersonalInformation(CVSchema):
    full_name: str | None = Field(description="Candidate's full name.")
    email: str | None = Field(description="Candidate's email address.")
    phone: str | None = Field(description="Candidate's phone number.")
    location: str | None = Field(description="Candidate's location.")
    linkedin_url: str | None = Field(description="LinkedIn profile URL.")
    github_url: str | None = Field(description="GitHub profile URL.")
    portfolio_url: str | None = Field(description="Portfolio or personal website URL.")

class WorkExperience(CVSchema):
    job_title: str | None
    company: str | None
    location: str | None
    start_date: str | None
    end_date: str | None
    is_current: bool
    responsibilities: list[str]

class Education(CVSchema):
    insitiution: str | None
    degree: str | None
    field_of_study: str | None
    start_date: str | None
    end_date: str | None

class Project(CVSchema):
    name: str | None
    description: str | None
    technologies: str | None
    url: str | None

class Certification(CVSchema):
    name: str | None
    issuer: str | None
    issue_date: str | None
    credential_url: str | None

class Language(CVSchema):
    name: str
    proficiency: str | None

class CVProfile(CVSchema):
    personal_information: PersonalInformation
    professional_summary: str | None
    skills: list[str]
    work_experiences: list[WorkExperience]
    educations: list[Education]
    projects: list[Project]
    certifications: list[Certification]
    languages: list[Language]