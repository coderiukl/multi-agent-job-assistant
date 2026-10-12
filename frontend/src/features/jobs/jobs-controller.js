import { searchJobs } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import {
  createJobSearchSnapshot,
  createJobSearchFilters,
  getActiveJobSearchPage,
  getJobSearchPage,
  isSameJobSearchSnapshot,
  rememberJobSearchPage,
} from "./job-search-snapshot.js";

export function createJobsController({
  cacheConversation,
  clearError,
  renderJobSearchResult,
  showError,
  showJobErrorState,
  showJobLoading,
}) {
  function saveSearchPage(sort, result) {
    if (!state.jobSearchSnapshot) {
      state.jobSearchSnapshot = createJobSearchSnapshot(
        state.lastSearchQuery,
        result,
        {},
      );
    }

    rememberJobSearchPage(state.jobSearchSnapshot, sort, result);

    cacheConversation?.();
  }

  function renderSavedSearchPage(sort, page) {
    const savedResult = getJobSearchPage(
      state.jobSearchSnapshot,
      sort,
      page,
    );

    if (!savedResult) return false;

    state.currentSort = sort;
    state.jobSearchSnapshot.currentSort = sort;
    state.jobSearchSnapshot.activePages[sort] = Number(page);
    elements.jobSort.value = sort;
    renderJobSearchResult(savedResult);
    cacheConversation?.();
    return true;
  }

  async function handleConversationSearch(
    query,
    conversationSearchResult,
    searchContext = null,
  ) {
    const searchQuery = String(
      conversationSearchResult?.query || query || "",
    ).trim();
    const filters = createJobSearchFilters(searchContext);

    if (conversationSearchResult) {
      if (
        !isSameJobSearchSnapshot(
          state.jobSearchSnapshot,
          searchQuery,
          conversationSearchResult,
          filters,
        )
      ) {
        state.jobSearchSnapshot = createJobSearchSnapshot(
          searchQuery,
          conversationSearchResult,
          filters,
        );
      }

      state.lastSearchQuery = searchQuery;
      state.currentSort =
        state.jobSearchSnapshot.currentSort || "relevance";
      elements.jobSort.value = state.currentSort;

      const savedResult = getActiveJobSearchPage(
        state.jobSearchSnapshot,
      );

      renderJobSearchResult(savedResult || conversationSearchResult);
      cacheConversation?.();
      return;
    }

    state.lastSearchQuery = searchQuery;
    state.currentSort = "relevance";
    elements.jobSort.value = "relevance";

    if (
      state.jobSearchSnapshot?.query === searchQuery &&
      renderSavedSearchPage("relevance", 1)
    ) {
      return;
    }

    state.isJobSearchLoading = true;
    showJobLoading();

    try {
      const searchResult = await searchJobs({
        query: searchQuery,
        filters,
        sort: state.currentSort,
        page: 1,
        pageSize: 10,
      });

      state.jobSearchSnapshot = createJobSearchSnapshot(
        searchQuery,
        searchResult,
        filters,
      );
      renderJobSearchResult(searchResult);
      cacheConversation?.();
    } finally {
      state.isJobSearchLoading = false;
    }
  }

  async function handleSortChange(event) {
    const sort = event.target.value;

    if (
      !state.lastSearchQuery ||
      state.isSending ||
      state.isJobSearchLoading
    ) {
      return;
    }

    state.currentSort = sort;

    if (renderSavedSearchPage(sort, 1)) {
      return;
    }

    state.isJobSearchLoading = true;

    clearError();
    showJobLoading();

    try {
      const result = await searchJobs({
        query: state.lastSearchQuery,
        filters: state.jobSearchSnapshot?.filters ?? {},
        sort,
        page: 1,
        pageSize: 10,
      });

      saveSearchPage(sort, result);
      renderJobSearchResult(result);
    } catch (error) {
      showError(
        error?.message ||
          "Không thể sắp xếp lại kết quả.",
      );
      showJobErrorState();
    } finally {
      state.isJobSearchLoading = false;
    }
  }

  async function handlePageChange(page) {
    const currentResult = state.currentSearchResult;
    const total = Number(currentResult?.total) || 0;
    const pageSize = Number(currentResult?.pageSize) || 10;
    const currentPage = Number(currentResult?.page) || 1;
    const totalPages = Math.max(
      1,
      Math.ceil(total / pageSize),
      currentResult?.hasMore ? currentPage + 1 : currentPage,
    );
    const nextPage = Number(page);

    if (
      !state.lastSearchQuery ||
      state.isSending ||
      state.isJobSearchLoading ||
      !Number.isInteger(nextPage) ||
      nextPage < 1 ||
      nextPage > totalPages ||
      nextPage === currentPage
    ) {
      return;
    }

    if (renderSavedSearchPage(state.currentSort, nextPage)) {
      elements.jobResults.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    state.isJobSearchLoading = true;
    clearError();
    showJobLoading();

    try {
      const result = await searchJobs({
        query: state.lastSearchQuery,
        filters: state.jobSearchSnapshot?.filters ?? {},
        sort: state.currentSort,
        page: nextPage,
        pageSize,
      });

      saveSearchPage(state.currentSort, result);
      renderJobSearchResult(result);
      elements.jobResults.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      showError(error?.message || "Không thể tải trang kết quả này.");
      renderJobSearchResult(currentResult);
    } finally {
      state.isJobSearchLoading = false;
    }
  }

  return {
    handleConversationSearch,
    handlePageChange,
    handleSortChange,
  };
}
