
from collections.abc import Mapping
from typing import Any

from backend.app.schemas.conversations_intent import (
    ConversationIntent,
    IntentAnalysisResult,
)

INTENT_LABELS = tuple(intent.value for intent in ConversationIntent)


def normalize_intent_result(value: Mapping[str, Any] | IntentAnalysisResult) -> dict[str, Any]:

    result = IntentAnalysisResult.model_validate(value)
    return result.model_dump(mode="json")


def score_intent(
    prediction: Mapping[str, Any] | IntentAnalysisResult,
    reference: Mapping[str, Any],
) -> dict[str, float]:

    actual = normalize_intent_result(prediction)

    required = (
        "primary_intent",
        "secondary_intents",
        "requires_cv",
        "requires_jd",
        "needs_clarification",
    )

    missing = [key for key in required if key not in reference]

    if missing:
        raise ValueError(f"Missing reference fields: {missing}")

    expected_primary = ConversationIntent(reference["primary_intent"]).value

    expected_secondary = {
        ConversationIntent(item).value
        for item in reference["secondary_intents"]
    }

    actual_secondary = set(actual["secondary_intents"])

    tp = len(actual_secondary & expected_secondary)
    fp = len(actual_secondary - expected_secondary)
    fn = len(expected_secondary - actual_secondary)

    # An exact match is meaningful even for two empty sets.
    secondary_exact = float(actual_secondary == expected_secondary)

    # Per-example precision/recall use zero for undefined cases.
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    scores = {
        "primary_accuracy": float(actual["primary_intent"] == expected_primary),
        "secondary_exact_match": secondary_exact,
        "secondary_tp": float(tp),
        "secondary_fp": float(fp),
        "secondary_fn": float(fn),
        "secondary_f1_example": f1,
        "requires_cv_accuracy": float(actual["requires_cv"] == reference["requires_cv"]),
        "requires_jd_accuracy": float(actual["requires_jd"] == reference["requires_jd"]),
        "clarification_accuracy": float(
            actual["needs_clarification"] == reference["needs_clarification"]
        ),
    }

    scores["all_fields_correct"] = float(
        scores["primary_accuracy"] == 1.0
        and scores["secondary_exact_match"] == 1.0
        and scores["requires_cv_accuracy"] == 1.0
        and scores["requires_jd_accuracy"] == 1.0
        and scores["clarification_accuracy"] == 1.0
    )

    return scores


def aggregate_intent_scores(
    predictions: list[Mapping[str, Any] | IntentAnalysisResult],
    references: list[Mapping[str, Any]],
) -> dict[str, float]:
    
    if not predictions or len(predictions) != len(references):
        raise ValueError(
            "Predictions and references must have equal, "
            "non-zero lengths."
        )

    scores = [
        score_intent(prediction, reference)
        for prediction, reference
        in zip(predictions, references, strict=True)
    ]

    count = len(scores)

    def mean(key: str) -> float:
        return sum(row[key] for row in scores) / count

    # Calculate Macro-F1 across the full intent label set.
    labels = INTENT_LABELS
    f1_per_label = []

    for label in labels:
        tp = fp = fn = 0

        for prediction, reference in zip(predictions, references, strict=True):
            actual = normalize_intent_result(prediction)["primary_intent"]
            expected = ConversationIntent(reference["primary_intent"]).value

            tp += int(actual == label and expected == label)
            fp += int(actual == label and expected != label)
            fn += int(actual != label and expected == label)

        denominator = 2 * tp + fp + fn
        f1_per_label.append(2 * tp / denominator if denominator else 0.0)

    # Micro-F1 over all secondary-intent decisions.
    total_tp = sum(row["secondary_tp"] for row in scores)
    total_fp = sum(row["secondary_fp"] for row in scores)
    total_fn = sum(row["secondary_fn"] for row in scores)

    denominator = 2 * total_tp + total_fp + total_fn

    return {
        "samples": float(count),
        "primary_accuracy": mean("primary_accuracy"),
        "primary_macro_f1": sum(f1_per_label) / len(labels),
        "secondary_exact_match": mean("secondary_exact_match"),
        "secondary_micro_f1": (2 * total_tp / denominator if denominator else 0.0),
        "requires_cv_accuracy": mean("requires_cv_accuracy"),
        "requires_jd_accuracy": mean("requires_jd_accuracy"),
        "clarification_accuracy": mean("clarification_accuracy"),
        "all_fields_correct": mean("all_fields_correct"),
    }
