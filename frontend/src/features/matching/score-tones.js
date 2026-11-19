/**
 * Maps backend scores and enums to visual tones. Pure functions so they can
 * be unit-tested without a DOM.
 */

/** Score is 0–100 as returned by the backend. */
export function getScoreTone(score) {
  const value = Number(score);

  if (!Number.isFinite(value)) {
    return "is-score-low";
  }

  if (value >= 75) {
    return "is-score-high";
  }

  return value >= 50 ? "is-score-mid" : "is-score-low";
}

const RECOMMENDATION_TONES = {
  strong_match: "tone-strong",
  good_match: "tone-good",
  partial_match: "tone-partial",
  low_match: "tone-low",
};

export function getRecommendationTone(recommendation) {
  return RECOMMENDATION_TONES[recommendation] ?? "tone-partial";
}

const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };

/** Stable sort: high → medium → low, unknown priorities last. */
export function sortByPriority(items) {
  return [...(Array.isArray(items) ? items : [])]
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const leftRank = PRIORITY_ORDER[left.item?.priority] ?? 3;
      const rightRank = PRIORITY_ORDER[right.item?.priority] ?? 3;

      return leftRank - rightRank || left.index - right.index;
    })
    .map(({ item }) => item);
}

export const EVIDENCE_STATUS_ORDER = [
  "missing",
  "partial",
  "matched",
  "not_applicable",
];

/** Groups requirement evidence by status, in the order a reader acts on. */
export function groupEvidenceByStatus(evidence) {
  const groups = new Map(EVIDENCE_STATUS_ORDER.map((status) => [status, []]));

  for (const item of Array.isArray(evidence) ? evidence : []) {
    const status = groups.has(item?.status) ? item.status : "missing";
    groups.get(status).push(item);
  }

  return EVIDENCE_STATUS_ORDER
    .map((status) => ({ status, items: groups.get(status) }))
    .filter((group) => group.items.length > 0);
}
