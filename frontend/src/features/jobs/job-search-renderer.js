import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { getStrategyLabel } from "../../shared/labels.js";

export function createJobSearchRenderer({
  openResultsPanel,
  renderJobCard,
  showInitialJobState,
  showNoJobResults,
  updateMobileResultsBadge,
}) {
  function renderJobSearchResult(result) {
    const items = Array.isArray(result?.items)
      ? result.items
      : [];

    state.currentSearchResult = result;
    state.jobs = items;
    state.currentMatchingResult = null;

    elements.resultsSummary.hidden = false;
    elements.jobSort.disabled = false;
    elements.backToJobsButton.hidden = true;

    const total = Number.isFinite(Number(result?.total))
      ? Number(result.total)
      : items.length;

    elements.resultCount.textContent =
      `Đang hiển thị ${items.length}/${total} công việc được đề xuất`;
    elements.searchStrategy.textContent =
      getStrategyLabel(result.strategy);

    updateMobileResultsBadge(total);
    openResultsPanel();
    renderMatchedTermChips(items);

    if (!items.length) {
      showNoJobResults();
      return;
    }

    elements.jobResults.innerHTML =
      items.map(renderJobCard).join("");
  }

  function showJobSearchResultsFromState() {
    if (!state.currentSearchResult) {
      showInitialJobState();
      return;
    }

    renderJobSearchResult(state.currentSearchResult);
    openResultsPanel();
  }

  return {
    renderJobSearchResult,
    showJobSearchResultsFromState,
  };
}

function renderMatchedTermChips(items) {
  const matchedTerms = [
    ...new Set(
      items.flatMap((item) =>
        Array.isArray(item.matchedTerms)
          ? item.matchedTerms
          : [],
      ),
    ),
  ].slice(0, 6);

  elements.activeFilters.innerHTML = "";

  for (const term of matchedTerms) {
    const chip = document.createElement("span");

    chip.className = "filter-chip";
    chip.textContent = term;

    elements.activeFilters.append(chip);
  }
}
