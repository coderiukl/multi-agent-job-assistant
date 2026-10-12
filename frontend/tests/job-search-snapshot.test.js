import assert from "node:assert/strict";
import test from "node:test";

import {
  createJobSearchSnapshot,
  createJobSearchFilters,
  getActiveJobSearchPage,
  getJobSearchPage,
  isSameJobSearchSnapshot,
  rememberJobSearchPage,
} from "../src/features/jobs/job-search-snapshot.js";

function result(page, jobIds) {
  return {
    query: "frontend fresher",
    total: 20,
    page,
    pageSize: 10,
    items: jobIds.map((jobId) => ({ job: { job_id: jobId } })),
  };
}

test("keeps every visited page in the same search snapshot", () => {
  const firstPage = result(1, ["job-1", "job-2"]);
  const secondPage = result(2, ["job-3", "job-4"]);
  const snapshot = createJobSearchSnapshot("find jobs", firstPage);

  rememberJobSearchPage(snapshot, "relevance", secondPage);

  assert.equal(getJobSearchPage(snapshot, "relevance", 1), firstPage);
  assert.equal(getJobSearchPage(snapshot, "relevance", 2), secondPage);
  assert.equal(getActiveJobSearchPage(snapshot), secondPage);
});

test("restores independently cached sort results", () => {
  const relevantPage = result(1, ["relevant-job"]);
  const newestPage = result(1, ["newest-job"]);
  const snapshot = createJobSearchSnapshot("find jobs", relevantPage);

  rememberJobSearchPage(snapshot, "newest", newestPage);

  assert.equal(getJobSearchPage(snapshot, "relevance", 1), relevantPage);
  assert.equal(getJobSearchPage(snapshot, "newest", 1), newestPage);
  assert.equal(getActiveJobSearchPage(snapshot), newestPage);
});

test("does not reuse a snapshot for a different result set", () => {
  const firstPage = result(1, ["job-1"]);
  const snapshot = createJobSearchSnapshot("find jobs", firstPage);

  assert.equal(
    isSameJobSearchSnapshot(snapshot, "find jobs", firstPage),
    true,
  );
  assert.equal(
    isSameJobSearchSnapshot(
      snapshot,
      "find jobs",
      result(1, ["different-job"]),
    ),
    false,
  );
});

test("does not reuse a snapshot when search filters change", () => {
  const firstPage = result(1, ["job-1"]);
  const snapshot = createJobSearchSnapshot(
    "find jobs",
    firstPage,
    { locations: ["Hồ Chí Minh"] },
  );

  assert.equal(
    isSameJobSearchSnapshot(
      snapshot,
      "find jobs",
      firstPage,
      { locations: ["Hà Nội"] },
    ),
    false,
  );
});

test("creates OR filters for multiple requested locations", () => {
  assert.deepEqual(
    createJobSearchFilters({
      location: "Hồ Chí Minh và Hà Nội",
      seniority: "intern",
      workMode: null,
    }),
    {
      locations: ["Hồ Chí Minh", "Hà Nội"],
      seniority_levels: ["intern"],
      work_modes: [],
    },
  );
});
