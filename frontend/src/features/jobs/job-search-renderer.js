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
    const page = Math.max(1, Number(result?.page) || 1);
    const pageSize = Math.max(1, Number(result?.pageSize) || items.length || 10);
    const firstItem = items.length ? (page - 1) * pageSize + 1 : 0;
    const lastItem = items.length ? firstItem + items.length - 1 : 0;

    elements.resultCount.textContent =
      `Đang hiển thị ${firstItem}–${lastItem}/${total} công việc được đề xuất`;
    elements.searchStrategy.textContent =
      getStrategyLabel(result.strategy);

    updateMobileResultsBadge(total);
    openResultsPanel();
    renderMatchedTermChips(items);
    renderPagination({ page, pageSize, total });

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

function renderPagination({ page, pageSize, total }) {
  const container = elements.jobPagination;

  if (!container) return;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  container.innerHTML = "";
  container.hidden = totalPages <= 1;

  if (totalPages <= 1) return;

  container.append(createPageButton("‹", page - 1, {
    label: "Trang trước",
    disabled: page <= 1,
    className: "job-pagination-nav",
  }));

  const visiblePages = getVisiblePages(page, totalPages);

  for (let index = 0; index < visiblePages.length; index += 1) {
    const pageNumber = visiblePages[index];
    const previousPage = visiblePages[index - 1];

    if (previousPage && pageNumber - previousPage > 1) {
      const ellipsis = document.createElement("span");
      ellipsis.className = "job-pagination-ellipsis";
      ellipsis.textContent = "…";
      container.append(ellipsis);
    }

    container.append(createPageButton(String(pageNumber), pageNumber, {
      current: pageNumber === page,
      label: `Trang ${pageNumber}`,
    }));
  }

  container.append(createPageButton("›", page + 1, {
    label: "Trang sau",
    disabled: page >= totalPages,
    className: "job-pagination-nav",
  }));

  const summary = document.createElement("span");
  summary.className = "job-pagination-summary";
  summary.textContent = `Trang ${page}/${totalPages}`;
  container.append(summary);
}

function createPageButton(text, page, {
  current = false,
  disabled = false,
  label,
  className = "",
} = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.jobPage = String(page);
  button.textContent = text;
  button.disabled = disabled;
  button.setAttribute("aria-label", label);

  if (current) {
    button.classList.add("is-active");
    button.setAttribute("aria-current", "page");
  }

  return button;
}

function getVisiblePages(currentPage, totalPages) {
  return [...new Set([
    1,
    currentPage - 1,
    currentPage,
    currentPage + 1,
    totalPages,
  ])]
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((left, right) => left - right);
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
