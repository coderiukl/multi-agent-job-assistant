import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
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
from app.services.job_matching_context import (
    TOTAL_YEARS_FIELD_PATH,
    build_cv_evidence_catalog,
    build_job_requirements,
    calculate_total_experience_years,
)
from app.utils.cv_privacy import cv_profile_for_llm

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
    MatchDimension.LANGUAGES_AND_CERTIFICATIONS: ("language_and_certifications"),
}

MANDATORY_PATTERN = re.compile(
    r"bắt buộc|bat buoc|mandatory|\bmust\b|\brequired\b",
    re.IGNORECASE,
)
# Negated or optional wording overrides a mandatory marker: "không bắt buộc",
# "not required", "non-mandatory", "optional", "là lợi thế"... (BUG-012).
OPTIONAL_PATTERN = re.compile(
    r"không\s+bắt\s+buộc|khong\s+bat\s+buoc|chưa\s+bắt\s+buộc"
    r"|\bnot\s+(?:strictly\s+)?(?:required|mandatory|a\s+must)\b"
    r"|\bnon[\s-]?(?:mandatory|required)\b|\bnot\s+necessary\b"
    r"|\boptional\b|\bpreferred\b|\bpreferably\b|\bnice[\s-]+to[\s-]+have\b"
    r"|\b(?:is\s+)?a\s+plus\b|\bbonus\b|\badvantage\b"
    r"|lợi\s+thế|loi\s+the|điểm\s+cộng|diem\s+cong|ưu\s+tiên|uu\s+tien",
    re.IGNORECASE,
)
_YEARS_UNIT = r"(?:năm|nam|years?|yrs?)"
_YEARS_NUMBER = r"(\d+(?:[.,]\d+)?)"
# "2-3", "2 – 3", "2 đến 3", "2 to 3": the lower bound is the minimum (BUG-011).
_YEARS_RANGE_TAIL = r"(?:\s*(?:-|–|—|~|đến|den|to)\s*\d+(?:[.,]\d+)?)?"
YEARS_REQUIREMENT_PATTERN = re.compile(
    # "tối thiểu 3 năm", "at least 3 years"
    r"(?:tối thiểu|ít nhất|toi thieu|it nhat|at least|minimum(?: of)?)"
    rf"\s*{_YEARS_NUMBER}{_YEARS_RANGE_TAIL}\s*\+?\s*{_YEARS_UNIT}"
    # "2 năm kinh nghiệm", "2-3 năm kinh nghiệm", "3+ years of experience"
    rf"|{_YEARS_NUMBER}{_YEARS_RANGE_TAIL}\s*\+?\s*"
    rf"{_YEARS_UNIT}\s*(?:kinh nghiệm|kinh nghiem|of experience|experience)"
    # "kinh nghiệm 2-3 năm", "experience: 3+ years"
    r"|(?:kinh nghiệm|kinh nghiem|experience)\s*(?:làm việc|lam viec)?\s*[:\-]?\s*"
    rf"(?:từ|tu|from)?\s*{_YEARS_NUMBER}{_YEARS_RANGE_TAIL}\s*\+?\s*{_YEARS_UNIT}",
    re.IGNORECASE,
)


def is_mandatory_requirement(text: str) -> bool:
    return bool(MANDATORY_PATTERN.search(text)) and not OPTIONAL_PATTERN.search(text)


def required_years(text: str) -> float | None:
    """Minimum years of experience stated by a requirement, if any."""
    match = YEARS_REQUIREMENT_PATTERN.search(text)
    if match is None:
        return None
    value = next(group for group in match.groups() if group is not None)
    return float(value.replace(",", "."))

MANDATORY_MISSING_SCORE_CAP = 49.99
MANDATORY_PARTIAL_SCORE_CAP = 69.99

MATCHING_PROMPT_VERSION = "job-matching-v3"
MATCHING_SCORING_VERSION = "weighted-rubric-v5-requirement-extraction-v2"


class JobMatchingService:
    def __init__(
        self,
        *,
        agent: JobMatchingAgent,
        dimension_weights: Mapping[MatchDimension, float] | None = None,
        model_version: str = "unknown",
        cache_size: int = 256,
    ) -> None:
        self._agent = agent
        self._dimension_weights = dict(dimension_weights or DEFAULT_DIMENSION_WEIGHTS)
        self._model_version = model_version
        self._cache_size = cache_size
        self._cache: OrderedDict[str, JobMatchingResult] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[JobMatchingResult]] = {}
        self._inflight_waiters: dict[str, int] = {}
        self._cache_lock = asyncio.Lock()
        self._validate_weights()

    async def match(self, matching_input: JobMatchingInput) -> JobMatchingResult:
        prepared_input = matching_input.model_copy(
            update={
                "requirements": build_job_requirements(matching_input.job),
                "cv_evidence_catalog": build_cv_evidence_catalog(
                    matching_input.cv_profile
                ),
            }
        )
        cache_key = self._build_cache_key(prepared_input)

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached.model_copy(update={"cache_hit": True})

            task = self._inflight.get(cache_key)
            if task is None:
                task = asyncio.create_task(self._match_uncached(prepared_input))
                self._inflight[cache_key] = task
                self._inflight_waiters[cache_key] = 0
            self._inflight_waiters[cache_key] += 1

        try:
            result = await asyncio.shield(task)
            async with self._cache_lock:
                self._cache[cache_key] = result
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            return result
        finally:
            async with self._cache_lock:
                remaining = self._inflight_waiters.get(cache_key, 1) - 1
                if remaining <= 0:
                    self._inflight_waiters.pop(cache_key, None)
                    self._inflight.pop(cache_key, None)
                    if not task.done():
                        task.cancel()
                else:
                    self._inflight_waiters[cache_key] = remaining

    async def _match_uncached(
        self, matching_input: JobMatchingInput
    ) -> JobMatchingResult:
        assessment = await self._agent.assess(matching_input)
        assessment = self._resolve_evidence(assessment, matching_input)
        assessment = self._apply_years_check(assessment, matching_input)

        applicable_dimensions = self._collect_applicable_dimensions(matching_input)

        overall_score = self._calculate_overall_score(
            assessment=assessment,
            applicable_dimensions=applicable_dimensions,
        )

        overall_score = self._apply_mandatory_gate(overall_score, assessment)

        recommendation = self._recommend(overall_score)

        calibrated_confidence = self._calibrate_confidence(
            model_confidence=assessment.confidence,
            matching_input=matching_input,
        )

        result = JobMatchingResult(
            **assessment.model_dump(exclude={"confidence"}),
            job_id=matching_input.job.job_id,
            overall_score=overall_score,
            recommendation=recommendation,
            confidence=calibrated_confidence,
            model_confidence=assessment.confidence,
        )

        logger.info(
            "Job matching completed",
            extra={
                "job_id": matching_input.job.job_id,
                "overall_score": overall_score,
                "recommendation": recommendation.value,
                "applicable_dimensions": [
                    dimension.value for dimension in applicable_dimensions
                ],
            },
        )

        return result

    def _collect_applicable_dimensions(
        self, matching_input: JobMatchingInput
    ) -> list[MatchDimension]:
        requirement_dimensions = {
            item.dimension for item in matching_input.requirements
        }
        return [
            dimension
            for dimension in self._dimension_weights
            if dimension in requirement_dimensions
        ]

    @staticmethod
    def _resolve_evidence(
        assessment: JobMatchingAssessment,
        matching_input: JobMatchingInput,
    ) -> JobMatchingAssessment:
        requirements = {
            item.requirement_id: item for item in matching_input.requirements
        }
        cv_evidence = {
            item.cv_evidence_id: item for item in matching_input.cv_evidence_catalog
        }
        resolved = []

        for item in assessment.evidence:
            if item.status == MatchStatus.NOT_APPLICABLE:
                continue
            requirement = requirements[item.requirement_id]
            resolved.append(
                item.model_copy(
                    update={
                        "requirement": requirement.text,
                        "cv_evidence": [
                            cv_evidence[evidence_id].text
                            for evidence_id in item.cv_evidence_ids
                        ],
                    }
                )
            )

        return assessment.model_copy(update={"evidence": resolved})

    @staticmethod
    def _apply_years_check(
        assessment: JobMatchingAssessment,
        matching_input: JobMatchingInput,
    ) -> JobMatchingAssessment:
        """Decide "at least N years" requirements in code, not with the LLM.

        Comparing a number is deterministic, and LLM flips between partial and
        missing here changed the final recommendation between runs.
        """
        total_years = calculate_total_experience_years(matching_input.cv_profile)
        years_item = next(
            (
                item
                for item in matching_input.cv_evidence_catalog
                if item.field_path == TOTAL_YEARS_FIELD_PATH
            ),
            None,
        )
        if total_years is None or years_item is None:
            return assessment

        updated = []
        for item in assessment.evidence:
            required = required_years(item.requirement)
            if required is None:
                updated.append(item)
                continue

            if total_years >= required:
                status = MatchStatus.MATCHED
            elif total_years >= required / 2:
                status = MatchStatus.PARTIAL
            else:
                status = MatchStatus.MISSING

            has_evidence = status != MatchStatus.MISSING
            note = (
                f" [Kiểm tra số năm: CV {total_years:g} năm, "
                f"yêu cầu tối thiểu {required:g} năm.]"
            )
            updated.append(
                item.model_copy(
                    update={
                        "status": status,
                        "cv_evidence_ids": (
                            [years_item.cv_evidence_id] if has_evidence else []
                        ),
                        "cv_evidence": [years_item.text] if has_evidence else [],
                        "explanation": item.explanation + note,
                    }
                )
            )

        breakdown = assessment.breakdown
        for dimension, field in BREAKDOWN_FIELD_BY_DIMENSION.items():
            supported = any(
                item.dimension == dimension
                and item.status in {MatchStatus.MATCHED, MatchStatus.PARTIAL}
                for item in updated
            )
            if not supported and getattr(breakdown, field) > 0:
                breakdown = breakdown.model_copy(update={field: 0.0})

        return assessment.model_copy(
            update={"evidence": updated, "breakdown": breakdown}
        )

    @staticmethod
    def _calibrate_confidence(
        *,
        model_confidence: float,
        matching_input: JobMatchingInput,
    ) -> float:
        requirement_quality = min(len(matching_input.requirements) / 8, 1.0)
        evidence_quality = min(
            len(matching_input.cv_evidence_catalog) / 12,
            1.0,
        )
        data_quality = 0.25 + 0.4 * requirement_quality + 0.35 * evidence_quality
        if matching_input.cv_profile.needs_review:
            data_quality *= 0.75
        return round(min(model_confidence, data_quality), 3)

    def _build_cache_key(self, matching_input: JobMatchingInput) -> str:
        payload = {
            "cv": cv_profile_for_llm(
                matching_input.cv_profile,
                purpose="job_matching",
            ),
            "job": matching_input.job.model_dump(mode="json"),
            "prompt_version": MATCHING_PROMPT_VERSION,
            "model_version": self._model_version,
            "scoring_version": MATCHING_SCORING_VERSION,
            "weights": {
                dimension.value: weight
                for dimension, weight in self._dimension_weights.items()
            },
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _calculate_overall_score(
        self,
        *,
        assessment: JobMatchingAssessment,
        applicable_dimensions: list[MatchDimension],
    ) -> float:
        if not applicable_dimensions:
            return 0.0

        applicable_weight = sum(
            self._dimension_weights[dimension] for dimension in applicable_dimensions
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
    def _apply_mandatory_gate(
        overall_score: float,
        assessment: JobMatchingAssessment,
    ) -> float:
        """Cap the score when an explicitly mandatory requirement is unmet.

        A weighted average lets strong skills hide an unmet hard requirement
        (e.g. "7 years required"). A missing one caps at low_match; a partly
        met one caps at partial_match so it never reaches good_match.
        """
        statuses = {
            item.status
            for item in assessment.evidence
            if is_mandatory_requirement(item.requirement)
        }
        if MatchStatus.MISSING in statuses:
            return min(overall_score, MANDATORY_MISSING_SCORE_CAP)
        if MatchStatus.PARTIAL in statuses:
            return min(overall_score, MANDATORY_PARTIAL_SCORE_CAP)
        return overall_score

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
                "dimension_weights must contain every matching dimension exactly once."
            )

        if any(weight <= 0 for weight in self._dimension_weights.values()):
            raise ValueError("All matching dimension weights must be positive.")

        total_weight = sum(self._dimension_weights.values())

        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Matching dimension weights must sum to 1.0. ")
