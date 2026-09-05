from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.cv_profile import CVProfile
from app.schemas.job import normalize_multiline


class CareerAdviceSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AdvicePriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CareerReadinessLevel(StrEnum):
    READY = "ready"
    NEARLY_READY = "nearly_ready"
    DEVELOPING = "developing"
    EXPLORING = "exploring"


class CareerAdviceInput(CareerAdviceSchema):
    user_request: str = Field(min_length=1, max_length=2000)
    cv_profile: CVProfile | None = None

    @field_validator("user_request")
    @classmethod
    def normalize_user_request(cls, value: str) -> str:
        normalized = normalize_multiline(value)

        if not normalized:
            raise ValueError("user_request must not be empty.")

        return normalized


class CareerRoleRecommendation(CareerAdviceSchema):
    role_title: str = Field(min_length=1, max_length=300)
    readiness_level: CareerReadinessLevel
    rationale: str = Field(min_length=1, max_length=2000)
    cv_evidence: list[str] = Field(default_factory=list, max_length=10)
    development_needs: list[str] = Field(default_factory=list, max_length=10)


class CareerSkillGap(CareerAdviceSchema):
    skill: str = Field(min_length=1, max_length=300)
    priority: AdvicePriority
    reason: str = Field(min_length=1, max_length=1500)
    current_evidence: list[str] = Field(default_factory=list, max_length=10)
    recommended_action: str = Field(min_length=1, max_length=1500)


class CareerRoadmapStep(CareerAdviceSchema):
    phase: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=300)
    timeframe: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=1500)
    actions: list[str] = Field(default_factory=list, max_length=10)
    success_criteria: list[str] = Field(default_factory=list, max_length=10)


class PortfolioProjectSuggestion(CareerAdviceSchema):
    title: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=1500)
    skills_practiced: list[str] = Field(default_factory=list, max_length=15)
    suggested_features: list[str] = Field(default_factory=list, max_length=10)
    expected_deliverable: str = Field(min_length=1, max_length=1500)


class CareerNextAction(CareerAdviceSchema):
    priority: AdvicePriority
    action: str = Field(min_length=1, max_length=1500)
    reason: str = Field(min_length=1, max_length=1500)
    timeframe: str | None = Field(default=None, max_length=200)


class CareerAdviceAssessment(CareerAdviceSchema):
    career_goal: str = Field(min_length=1, max_length=1000)
    recommended_roles: list[CareerRoleRecommendation] = Field(default_factory=list, max_length=5)
    skill_gaps: list[CareerSkillGap] = Field(default_factory=list, max_length=15)
    roadmap: list[CareerRoadmapStep] = Field(default_factory=list, max_length=10)
    portfolio_projects: list[PortfolioProjectSuggestion] = Field(default_factory=list, max_length=5)
    next_actions: list[CareerNextAction] = Field(default_factory=list, max_length=10)
    summary: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0.0, le=1.0)


class CareerAdviceResult(CareerAdviceAssessment):
    is_personalized: bool
    top_priority_skills: list[str] = Field(default_factory=list, max_length=5)