import logging
from collections.abc import Mapping

from app.agents.job_matching_agent import JobMatchingAgent
from app.schemas.job_matching import (
    JobMatchingAssessment,
    JobMatchingInput,
    JobMatchingResult,
    MatchDimension,
    MatchRecommendation,
    MatchStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_DIMENSION_WEIGHTS: dict[MatchDimension, float] = {
    MatchDimension.TECHNICAL_SKILLS: 0.40,
    MatchDimension.EXPERIENCE: 0.25,
    MatchDimension.PROJECTS: 0.15,
    MatchDimension.EDUCATION: 0.10,
    MatchDimension.LANGUAGES_AND_CERTIFICATIONS: 0.10,
}


BREAKDOWN_FIELD_BY_DIMENSION: dict[MatchDimension, str] = {
    MatchDimension.TECHNICAL_SKILLS: "technical_skills",
    MatchDimension.EXPERIENCE: "experience",
    MatchDimension.PROJECTS: "projects",
    MatchDimension.EDUCATION: "education",
    MatchDimension.LANGUAGES_AND_CERTIFICATIONS: (
        "language_and_certifications"
    ),
}

class JobMatchingService:
    def __init__(self, *, agent: JobMatchingAgent, dimension_weights: Mapping[MatchDimension, float] | None = None) -> None:
        self._agent = agent
        self._dimension_weights = dict(dimension_weights or DEFAULT_DIMENSION_WEIGHTS)
        self._validate_weights()

    async def match(self, matching_input: JobMatchingInput) -> JobMatchingResult:
        assessment = await self._agent.assess(matching_input)

        applicable_dimensions = self._collect_applicable_dimensions(assessment)

        overall_score = self._calculate_overall_score(
            assessment=assessment,
            applicable_dimensions=applicable_dimensions,
        )

        recommendation = self._recommend(overall_score)

        result = JobMatchingResult(
            **assessment.model_dump(),
            job_id=matching_input.job.job_id,
            overall_score=overall_score,
            recommendation=recommendation,
        )

        logger.info(
            "Job matching completed",
            extra={
                "job_id": matching_input.job.job_id,
                "overall_score": overall_score,
                "recommendation": recommendation.value,
                "applicable_dimensions": [
                    dimension.value
                    for dimension in applicable_dimensions
                ],
            },
        )

        return result

    def _collect_applicable_dimensions(self, assessment: JobMatchingAssessment) -> list[MatchDimension]:
        applicable_dimensions: list[MatchDimension] = []

        for dimension in self._dimension_weights:
            dimension_evidence = [evidence for evidence in assessment.evidence if evidence.dimension == dimension]

            if not dimension_evidence:
                applicable_dimensions.append(dimension)
                continue

            has_applicable_requirement = any(
                evidence.status != MatchStatus.NOT_APPLICABLE
                for evidence in dimension_evidence
            )

            if has_applicable_requirement:
                applicable_dimensions.append(dimension)

        return applicable_dimensions

    def _calculate_overall_score(self, *, assessment: JobMatchingAssessment, applicable_dimensions: list[MatchDimension]) -> float:
        if not applicable_dimensions:
            return 0.0

        applicable_weight = sum(
            self._dimension_weights[dimension]
            for dimension in applicable_dimensions
        )

        if applicable_weight <= 0:
            return 0.0

        weighted_score = 0.0

        for dimension in applicable_dimensions:
            field_name = BREAKDOWN_FIELD_BY_DIMENSION[dimension]
            dimension_score = float(getattr(assessment.breakdown, field_name))
            dimension_weight = self._dimension_weights[dimension]
            weighted_score += dimension_score * dimension_weight

        normalized_score = weighted_score / applicable_weight

        return round(normalized_score, 2)

    @staticmethod
    def _recommend(overall_score: float) -> MatchRecommendation:
        if overall_score >= 85:
            return MatchRecommendation.STRONG_MATCH

        if overall_score >= 70:
            return MatchRecommendation.GOOD_MATCH

        if overall_score >= 50:
            return MatchRecommendation.PARTIAL_MATCH

        return MatchRecommendation.LOW_MATCH

    def _validate_weights(self) -> None:
        expected_dimensions = set(MatchDimension)
        configured_dimensions = set(self._dimension_weights)

        missing_dimensions = expected_dimensions - configured_dimensions
        extra_dimensions = configured_dimensions - expected_dimensions

        if missing_dimensions or extra_dimensions:
            raise ValueError(
                "dimension_weights must contain every matching "
                "dimension exactly once."
            )

        if any(weight <= 0 for weight in self._dimension_weights.values()):
            raise ValueError("All matching dimension weights must be positive.")

        total_weight = sum(self._dimension_weights.values())

        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Matching dimension weights must sum to 1.0. ")
        
