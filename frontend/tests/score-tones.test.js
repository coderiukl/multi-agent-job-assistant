import assert from "node:assert/strict";
import test from "node:test";

import {
  getRecommendationTone,
  getScoreTone,
  groupEvidenceByStatus,
  sortByPriority,
} from "../src/features/matching/score-tones.js";

test("score tone follows backend 0-100 scale", () => {
  assert.equal(getScoreTone(92), "is-score-high");
  assert.equal(getScoreTone(75), "is-score-high");
  assert.equal(getScoreTone(74.9), "is-score-mid");
  assert.equal(getScoreTone(50), "is-score-mid");
  assert.equal(getScoreTone(12), "is-score-low");
  assert.equal(getScoreTone(undefined), "is-score-low");
  assert.equal(getScoreTone("not-a-number"), "is-score-low");
});

test("recommendation tone maps every backend enum and falls back safely", () => {
  assert.equal(getRecommendationTone("strong_match"), "tone-strong");
  assert.equal(getRecommendationTone("good_match"), "tone-good");
  assert.equal(getRecommendationTone("partial_match"), "tone-partial");
  assert.equal(getRecommendationTone("low_match"), "tone-low");
  assert.equal(getRecommendationTone("unknown"), "tone-partial");
});

test("sortByPriority orders high to low and keeps original order within a priority", () => {
  const items = [
    { id: 1, priority: "low" },
    { id: 2, priority: "high" },
    { id: 3, priority: "medium" },
    { id: 4, priority: "high" },
    { id: 5 },
  ];

  assert.deepEqual(
    sortByPriority(items).map((item) => item.id),
    [2, 4, 3, 1, 5],
  );
  assert.deepEqual(sortByPriority(null), []);
  assert.equal(items[0].id, 1, "input array must not be mutated");
});

test("groupEvidenceByStatus groups requirements with missing first", () => {
  const groups = groupEvidenceByStatus([
    { requirement: "Python", status: "matched" },
    { requirement: "Spark", status: "missing" },
    { requirement: "SQL", status: "partial" },
    { requirement: "Airflow", status: "missing" },
    { requirement: "Legacy", status: "unexpected" },
  ]);

  assert.deepEqual(
    groups.map((group) => [group.status, group.items.map((item) => item.requirement)]),
    [
      ["missing", ["Spark", "Airflow", "Legacy"]],
      ["partial", ["SQL"]],
      ["matched", ["Python"]],
    ],
  );
  assert.deepEqual(groupEvidenceByStatus(undefined), []);
});
