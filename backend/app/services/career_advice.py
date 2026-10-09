import logging

from app.agents.career_advice_agent import CareerAdviceAgent
from app.schemas.career_advice import (
    AdvicePriority,
    CareerAdviceAssessment,
    CareerAdviceInput,
    CareerAdviceResult,
    CareerSkillGap,
)

logger = logging.getLogger(__name__)


PRIORITY_ORDER: dict[AdvicePriority, int] = {
    AdvicePriority.HIGH: 0,
    AdvicePriority.MEDIUM: 1,
    AdvicePriority.LOW: 2,
}


class CareerAdviceService:
    def __init__(self, *, agent: CareerAdviceAgent) -> None:
        self._agent = agent

    async def advise(self, advice_input: CareerAdviceInput) -> CareerAdviceResult:
        assessment = await self._agent.advise(advice_input)
        normalized_assessment = self._normalize_assessment(assessment)
        top_priority_skills = self._collect_top_priority_skills(
            normalized_assessment.skill_gaps
        )

        result = CareerAdviceResult(
            **normalized_assessment.model_dump(exclude={"confidence"}),
            is_personalized=advice_input.cv_profile is not None,
            top_priority_skills=top_priority_skills,
            confidence=self._calibrate_confidence(
                normalized_assessment.confidence,
                advice_input,
            ),
            model_confidence=normalized_assessment.confidence,
            matching_reliability=(
                advice_input.matching_execution.reliability_ratio
                if advice_input.matching_execution is not None
                else None
            ),
            data_quality_warnings=self._quality_warnings(advice_input),
        )

        logger.info(
            "Career advice completed",
            extra={
                "is_personalized": result.is_personalized,
                "recommended_role_count": len(result.recommended_roles),
                "top_priority_skill_count": len(result.top_priority_skills),
                "confidence": result.confidence,
            },
        )

        return result

    @staticmethod
    def _normalize_assessment(
        assessment: CareerAdviceAssessment,
    ) -> CareerAdviceAssessment:

        ordered_skill_gaps = sorted(
            assessment.skill_gaps,
            key=lambda item: PRIORITY_ORDER[item.priority],
        )

        ordered_roadmap = sorted(
            assessment.roadmap,
            key=lambda item: item.phase,
        )

        ordered_next_actions = sorted(
            assessment.next_actions,
            key=lambda item: PRIORITY_ORDER[item.priority],
        )

        return assessment.model_copy(
            update={
                "skill_gaps": ordered_skill_gaps,
                "roadmap": ordered_roadmap,
                "next_actions": ordered_next_actions,
            }
        )

    @staticmethod
    def _collect_top_priority_skills(skill_gaps: list[CareerSkillGap]) -> list[str]:
        selected_skills: list[str] = []
        seen: set[str] = set()

        for skill_gap in skill_gaps:
            normalized_key = skill_gap.skill.casefold()

            if normalized_key in seen:
                continue

            seen.add(normalized_key)
            selected_skills.append(skill_gap.skill)

            if len(selected_skills) == 5:
                break

        return selected_skills

    @staticmethod
    def _calibrate_confidence(
        model_confidence: float,
        advice_input: CareerAdviceInput,
    ) -> float:
        cap = 1.0
        if advice_input.cv_profile is None:
            cap = min(cap, 0.6)
        elif advice_input.cv_profile.needs_review:
            cap = min(cap, 0.7)

        execution = advice_input.matching_execution
        if execution is not None:
            cap = min(cap, 0.3 + 0.7 * execution.reliability_ratio)

        return round(min(model_confidence, cap), 3)

    @staticmethod
    def _quality_warnings(advice_input: CareerAdviceInput) -> list[str]:
        warnings: list[str] = []
        if advice_input.cv_profile is None:
            warnings.append("CV data was not available for personalized advice.")
        elif advice_input.cv_profile.needs_review:
            warnings.append("Some extracted CV fields require user review.")

        execution = advice_input.matching_execution
        if execution is not None and execution.failed:
            warnings.append(f"{execution.failed} job matching operation(s) failed.")
        if execution is not None and execution.skipped:
            warnings.append(f"{execution.skipped} job matching operation(s) timed out.")
        return warnings
