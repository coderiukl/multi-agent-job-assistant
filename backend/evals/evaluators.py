import math
import re
from typing import Any

from app.graphs.conversation.planning import create_workflow_plan
from app.schemas.conversations_intent import IntentAnalysisResult

def _score(key: str, passed: bool) -> dict[str, Any]:
    return {
        "key": key,
        "score": float(passed),
    }

def _normalize_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").casefold(),
    ).strip()

def _normalize_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()

    return {
        _normalize_text(value)
        for value in values
        if _normalize_text(value)
    }

# Intent Analysis


def intent_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _score("intent_accuracy",outputs.get("primary_intent") == reference_outputs.get("primary_intent"))

def clarification_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _score("clarification_accuracy", outputs.get("needs_clarification") == reference_outputs.get("needs_clarification"))

def required_cv_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _score("required_cv_accuracy", outputs.get("requires_cv") == reference_outputs.get("requires_cv"))

def required_jd_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _score("required_jd_accuracy", outputs.get("requires_jd") == reference_outputs.get("requires_jd"))

def search_context_patch_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = outputs.get("search_context_patch", {})
    expected = reference_outputs.get("search_context_patch",{})

    checked_fields = (
        "role",
        "location",
        "seniority",
        "work_mode",
        "clear_fields",
    )

    comparisons: list[bool] = []

    for field in checked_fields:
        if field not in expected:
            continue

        if field == "clear_fields":
            comparisons.append(
                _normalize_set(actual.get(field, [])) == _normalize_set(expected.get(field, []))
            )
        else:
            comparisons.append(
                _normalize_text(actual.get(field)) == _normalize_text(expected.get(field))
            )

    return {
        "key": "search_context_patch_accuracy",
        "score": (
            sum(comparisons) / len(comparisons)
            if comparisons
            else 1.0
        ),
    }

def intent_schema_valid(
    outputs: dict[str, Any],
) -> dict[str, Any]:
    required_fields = {
        "primary_intent",
        "secondary_intents",
        "confidence",
        "requires_cv",
        "requires_jd",
        "search_context_patch",
        "needs_clarification",
    }

    valid = (
        required_fields.issubset(outputs)
        and isinstance(outputs.get("secondary_intents"), list)
        and isinstance(outputs.get("search_context_patch"), dict)
        and isinstance(outputs.get("needs_clarification"), bool)
    )

    return _score("intent_schema_valid", valid)

# Job Search Plan

def search_location_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(outputs.get("filters", {}).get("locations", []))
    expected = _normalize_set(reference_outputs.get("required_locations", []))

    return _score(
        "search_location_accuracy",
        expected.issubset(actual),
    )

def search_seniority_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(outputs.get("filters", {}).get("seniority_levels", []))
    expected = _normalize_set(reference_outputs.get("required_seniority_levels", []))

    forbidden = _normalize_set(reference_outputs.get( "forbidden_seniority_levels", []))

    valid = expected.issubset(actual) and not actual.intersection(forbidden)

    return _score("search_seniority_accuracy", valid)

def search_work_mode_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(
        outputs.get("filters", {}).get(
            "work_modes",
            [],
        )
    )
    expected = _normalize_set(
        reference_outputs.get(
            "required_work_modes",
            [],
        )
    )

    return _score(
        "search_work_mode_accuracy",
        expected.issubset(actual),
    )


def search_sort_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    expected = reference_outputs.get("sort")

    if expected is None:
        return {
            "key": "search_sort_accuracy",
            "score": 1.0,
        }

    return _score(
        "search_sort_accuracy",
        outputs.get("sort") == expected,
    )


def semantic_query_present(outputs: dict[str, Any]) -> dict[str, Any]:
    query = _normalize_text(outputs.get("semantic_query"))

    return _score(
        "semantic_query_present",
        len(query) >= 3,
    )

# Job Search Retrieval

def _result_job_ids(outputs: dict[str, Any]) -> list[str]:
    return [
        str(item.get("job", {}).get("job_id", ""))
        for item in outputs.get("items", [])
        if item.get("job", {}).get("job_id")
    ]


def recall_at_k(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    relevant = set(reference_outputs.get("relevant_job_ids", []))

    if not relevant:
        return {
            "key": "recall_at_k",
            "score": 1.0,
        }

    retrieved = set(_result_job_ids(outputs))

    return {
        "key": "recall_at_k",
        "score": len(relevant.intersection(retrieved))
        / len(relevant),
    }


def precision_at_k(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    relevant = set(reference_outputs.get("relevant_job_ids", []))
    retrieved = _result_job_ids(outputs)

    if not retrieved:
        return {
            "key": "precision_at_k",
            "score": 0.0 if relevant else 1.0,
        }

    relevant_count = sum(job_id in relevant for job_id in retrieved)

    return {
        "key": "precision_at_k",
        "score": relevant_count / len(retrieved),
    }


def ndcg_at_k(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    relevance = reference_outputs.get("relevance_by_job_id", {})
    retrieved = _result_job_ids(outputs)

    dcg = 0.0

    for index, job_id in enumerate(retrieved):
        gain = float(relevance.get(job_id, 0))
        dcg += (2**gain - 1) / math.log2(index + 2)

    ideal_gains = sorted(
        (float(value) for value in relevance.values()),
        reverse=True,
    )[: len(retrieved)]

    ideal_dcg = sum(
        (2**gain - 1) / math.log2(index + 2)
        for index, gain in enumerate(ideal_gains)
    )

    return {
        "key": "ndcg_at_k",
        "score": dcg / ideal_dcg if ideal_dcg else 1.0,
    }


def duplicate_free(outputs: dict[str, Any]) -> dict[str, Any]:
    job_ids = _result_job_ids(outputs)

    return _score(
        "duplicate_free",
        len(job_ids) == len(set(job_ids)),
    )


def forbidden_jobs_absent(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    forbidden = set(reference_outputs.get("forbidden_job_ids", []))
    retrieved = set(_result_job_ids(outputs))

    return _score(
        "forbidden_jobs_absent",
        not retrieved.intersection(forbidden),
    )


def unknown_seniority_after_known(outputs: dict[str, Any]) -> dict[str, Any]:
    levels = [
        item.get("job", {}).get(
            "seniority_level",
            "unknown",
        )
        for item in outputs.get("items", [])
    ]

    seen_unknown = False

    for level in levels:
        if level == "unknown":
            seen_unknown = True
            continue

        if seen_unknown:
            return _score(
                "unknown_seniority_after_known",
                False,
            )

    return _score(
        "unknown_seniority_after_known",
        True,
    )

# Job Matching

def matching_score_in_range(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    score = float(outputs.get("overall_score", -1))
    minimum = float(reference_outputs.get("score_min", 0))
    maximum = float(reference_outputs.get("score_max", 100))

    return _score(
        "matching_score_in_range",
        minimum <= score <= maximum,
    )


def matching_recommendation_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return _score(
        "matching_recommendation_accuracy",
        outputs.get("recommendation") == reference_outputs.get("expected_recommendation"),
    )


def recommendation_score_consistency(outputs: dict[str, Any],) -> dict[str, Any]:
    score = float(outputs.get("overall_score", -1))
    recommendation = outputs.get("recommendation")

    expected = (
        "strong_match"
        if score >= 85 else "good_match"
        if score >= 70 else "partial_match"
        if score >= 50 else "low_match"
    )

    return _score(
        "recommendation_score_consistency",
        recommendation == expected,
    )


def matching_evidence_grounded(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    cv_text = _normalize_text(inputs.get("cv_profile", {}))

    evidence_items = [
        evidence
        for item in outputs.get("evidence", [])
        for evidence in item.get("cv_evidence", [])
    ]

    if not evidence_items:
        positive_scores = [
            float(value)
            for value in outputs.get("breakdown", {}).values()
        ]

        return _score(
            "matching_evidence_grounded",
            not any(score > 0 for score in positive_scores),
        )

    grounded = sum(
        _normalize_text(evidence) in cv_text
        for evidence in evidence_items
    )

    return {
        "key": "matching_evidence_grounded",
        "score": grounded / len(evidence_items),
    }


def forbidden_claims_absent(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    forbidden = [
        _normalize_text(value)
        for value in reference_outputs.get("forbidden_claims", [])
    ]

    output_text = _normalize_text(
        {
            "summary": outputs.get("summary"),
            "strengths": outputs.get("strengths"),
            "gaps": outputs.get("gaps"),
            "evidence": outputs.get("evidence"),
        }
    )

    return _score(
        "forbidden_claims_absent",
        not any(
            claim and claim in output_text
            for claim in forbidden
        ),
    )

def secondary_intents_exact_match(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(outputs.get("secondary_intents", []))
    expected = _normalize_set(reference_outputs.get("secondary_intents", []))

    return _score(
        "secondary_intents_exact_match",
        actual == expected,
    )


def secondary_intents_precision(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(outputs.get("secondary_intents", []))
    expected = _normalize_set(reference_outputs.get("secondary_intents", []))

    if not actual:
        precision = 1.0 if not expected else 0.0
    else:
        precision = len(actual.intersection(expected)) / len(actual)

    return {
        "key": "secondary_intents_precision",
        "score": precision,
    }


def secondary_intents_recall(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    actual = _normalize_set(outputs.get("secondary_intents", []))
    expected = _normalize_set(reference_outputs.get("secondary_intents", []))

    if not expected:
        recall = 1.0 if not actual else 0.0
    else:
        recall = len(actual.intersection(expected)) / len(expected)

    return {
        "key": "secondary_intents_recall",
        "score": recall,
    }


def secondary_intents_valid(outputs: dict[str, Any]) -> dict[str, Any]:
    primary = outputs.get("primary_intent")
    secondary = outputs.get("secondary_intents", [])

    if not isinstance(secondary, list):
        return _score("secondary_intents_valid", False)

    normalized = [
        _normalize_text(intent)
        for intent in secondary
    ]

    valid = (
        len(normalized) == len(set(normalized))
        and _normalize_text(primary) not in normalized
    )

    return _score("secondary_intents_valid", valid)

def workflow_steps_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    expected_steps = reference_outputs.get("workflow_steps")

    if expected_steps is None:
        return {
            "key": "workflow_steps_accuracy",
            "score": 1.0,
        }

    try:
        intent = IntentAnalysisResult.model_validate(outputs)
        workflow = create_workflow_plan(intent)

        actual_steps = [step.value for step in workflow.steps]
    except (TypeError, ValueError):
        return _score("workflow_steps_accuracy", False)

    return _score(
        "workflow_steps_accuracy",
        actual_steps == expected_steps,
    )


def workflow_type_accuracy(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    expected_type = reference_outputs.get("workflow_type")

    if expected_type is None:
        return {
            "key": "workflow_type_accuracy",
            "score": 1.0,
        }

    try:
        intent = IntentAnalysisResult.model_validate(outputs)
        workflow = create_workflow_plan(intent)
        actual_type = workflow.workflow_type.value
    except (TypeError, ValueError):
        return _score("workflow_type_accuracy", False)

    return _score(
        "workflow_type_accuracy",
        actual_type == expected_type,
    )

INTENT_EVALUATORS = [
    intent_schema_valid,
    intent_accuracy,
    secondary_intents_valid,
    secondary_intents_exact_match,
    secondary_intents_precision,
    secondary_intents_recall,
    clarification_accuracy,
    required_cv_accuracy,
    required_jd_accuracy,
    search_context_patch_accuracy,
    workflow_steps_accuracy,
    workflow_type_accuracy,
]

JOB_SEARCH_PLAN_EVALUATORS = [
    semantic_query_present,
    search_location_accuracy,
    search_seniority_accuracy,
    search_work_mode_accuracy,
    search_sort_accuracy,
]

JOB_SEARCH_RETRIEVAL_EVALUATORS = [
    recall_at_k,
    precision_at_k,
    ndcg_at_k,
    duplicate_free,
    forbidden_jobs_absent,
    unknown_seniority_after_known,
]

JOB_MATCHING_EVALUATORS = [
    matching_score_in_range,
    matching_recommendation_accuracy,
    recommendation_score_consistency,
    matching_evidence_grounded,
    forbidden_claims_absent,
]