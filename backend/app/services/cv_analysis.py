import logging
from collections.abc import Mapping

from app.agents.cv_analysis_agent import CVAnalysisAgent
from app.schemas.cv_analysis import (
    CVAnalysisAssessment,
    CVAnalysisDimension,
    CVAnalysisInput,
    CVAnalysisResult,
    CVQualityLevel,
)


logger = logging.getLogger(__name__)


DEFAULT_DIMENSION_WEIGHTS: dict[CVAnalysisDimension, float] = {
    CVAnalysisDimension.COMPLETENESS: 0.15,
    CVAnalysisDimension.PROFESSIONAL_SUMMARY: 0.10,
    CVAnalysisDimension.SKILLS: 0.20,
    CVAnalysisDimension.WORK_EXPERIENCE: 0.15,
    CVAnalysisDimension.PROJECTS: 0.25,
    CVAnalysisDimension.EDUCATION_AND_CREDENTIALS: 0.15,
}


BREAKDOWN_FIELD_BY_DIMENSION: dict[CVAnalysisDimension, str] = {
    CVAnalysisDimension.COMPLETENESS: "completeness",
    CVAnalysisDimension.PROFESSIONAL_SUMMARY: "professional_summary",
    CVAnalysisDimension.SKILLS: "skills",
    CVAnalysisDimension.WORK_EXPERIENCE: "work_experience",
    CVAnalysisDimension.PROJECTS: "projects",
    CVAnalysisDimension.EDUCATION_AND_CREDENTIALS: "education_and_credentials",
}


class CVAnalysisService:
    def __init__(
        self,
        *,
        agent: CVAnalysisAgent,
        dimension_weights: Mapping[CVAnalysisDimension, float] | None = None,
    ) -> None:
        self._agent = agent
        self._dimension_weights = dict(dimension_weights or DEFAULT_DIMENSION_WEIGHTS)

        self._validate_weights()

    async def analyze(self, analysis_input: CVAnalysisInput) -> CVAnalysisResult:
        assessment = await self._agent.analyze(analysis_input)
        overall_score = self._calculate_overall_score(assessment)
        quality_level = self._determine_quality_level(overall_score)

        result = CVAnalysisResult(
            **assessment.model_dump(),
            overall_score=overall_score,
            quality_level=quality_level,
        )

        logger.info(
            "CV analysis completed",
            extra={
                "overall_score": overall_score,
                "quality_level": quality_level.value,
                "confidence": assessment.confidence,
            },
        )

        return result

    def _calculate_overall_score(self, assessment: CVAnalysisAssessment) -> float:
        weighted_score = 0.0

        for dimension, weight in (self._dimension_weights.items()):
            field_name = BREAKDOWN_FIELD_BY_DIMENSION[dimension]

            dimension_score = float(
                getattr(
                    assessment.breakdown,
                    field_name,
                )
            )

            weighted_score += dimension_score * weight

        return round(weighted_score, 2)

    @staticmethod
    def _determine_quality_level(overall_score: float) -> CVQualityLevel:
        if overall_score >= 85:
            return CVQualityLevel.EXCELLENT

        if overall_score >= 70:
            return CVQualityLevel.GOOD

        if overall_score >= 50:
            return CVQualityLevel.NEEDS_IMPROVEMENT

        return CVQualityLevel.WEAK

    def _validate_weights(self) -> None:
        expected_dimensions = set(CVAnalysisDimension)
        configured_dimensions = set(self._dimension_weights)
        missing_dimensions = expected_dimensions - configured_dimensions
        extra_dimensions = configured_dimensions - expected_dimensions

        if missing_dimensions or extra_dimensions:
            raise ValueError(
                "dimension_weights must contain every CV "
                "analysis dimension exactly once."
            )

        if any(
            weight <= 0
            for weight in self._dimension_weights.values()
        ):
            raise ValueError(
                "All CV analysis dimension weights must "
                "be positive."
            )

        total_weight = sum(self._dimension_weights.values())

        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(
                "CV analysis dimension weights must sum "
                "to 1.0."
            )