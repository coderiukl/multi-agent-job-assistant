function resultFingerprint(result) {
  const jobIds = Array.isArray(result?.items)
    ? result.items.map((item) => item?.job?.job_id ?? "")
    : [];

  return JSON.stringify([
    result?.query ?? "",
    Number(result?.total) || 0,
    jobIds,
  ]);
}

export function createJobSearchFilters(searchContext) {
  if (!searchContext) return {};

  const locations = String(searchContext.location ?? "")
    .split(/\s*[,;|]\s*|\s+(?:và|hoặc|and|or)\s+/iu)
    .map((location) => location.trim())
    .filter(Boolean);

  return {
    locations: [...new Set(locations)],
    seniority_levels: searchContext.seniority
      ? [searchContext.seniority]
      : [],
    work_modes: searchContext.workMode
      ? [searchContext.workMode]
      : [],
  };
}

export function createJobSearchSnapshot(query, result, filters = {}) {
  const snapshot = {
    key: JSON.stringify([
      String(query ?? "").trim(),
      filters,
      resultFingerprint(result),
    ]),
    query: String(query ?? "").trim(),
    filters,
    currentSort: "relevance",
    activePages: {},
    pages: {},
  };

  return rememberJobSearchPage(snapshot, "relevance", result);
}

export function isSameJobSearchSnapshot(
  snapshot,
  query,
  result,
  filters = {},
) {
  if (!snapshot) return false;

  const expected = createJobSearchSnapshot(query, result, filters);
  return snapshot.key === expected.key;
}

export function rememberJobSearchPage(snapshot, sort, result) {
  const normalizedSort = sort || "relevance";
  const page = Math.max(1, Number(result?.page) || 1);

  snapshot.pages[normalizedSort] ??= {};
  snapshot.pages[normalizedSort][page] = result;
  snapshot.activePages[normalizedSort] = page;
  snapshot.currentSort = normalizedSort;

  return snapshot;
}

export function getJobSearchPage(snapshot, sort, page) {
  const normalizedSort = sort || "relevance";
  const normalizedPage = Math.max(1, Number(page) || 1);

  return snapshot?.pages?.[normalizedSort]?.[normalizedPage] ?? null;
}

export function getActiveJobSearchPage(snapshot) {
  const sort = snapshot?.currentSort || "relevance";
  const page = snapshot?.activePages?.[sort] || 1;

  return getJobSearchPage(snapshot, sort, page);
}
