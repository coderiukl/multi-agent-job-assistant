import { searchJobs } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";

export function createJobsController({
  clearError,
  renderJobSearchResult,
  showError,
  showJobErrorState,
  showJobLoading,
}) {
  async function handleConversationSearch(
    query,
    conversationSearchResult,
  ) {
    state.lastSearchQuery = query;
    state.currentSort = "relevance";
    elements.jobSort.value = "relevance";

    if (conversationSearchResult) {
      renderJobSearchResult(conversationSearchResult);
      return;
    }

    state.isJobSearchLoading = true;
    showJobLoading();

    try {
      const searchResult = await searchJobs({
        query,
        sort: state.currentSort,
        page: 1,
        pageSize: 10,
      });

      renderJobSearchResult(searchResult);
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
    state.isJobSearchLoading = true;

    clearError();
    showJobLoading();

    try {
      const result = await searchJobs({
        query: state.lastSearchQuery,
        sort,
        page: 1,
        pageSize: 10,
      });

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
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const nextPage = Number(page);

    if (
      !state.lastSearchQuery ||
      state.isSending ||
      state.isJobSearchLoading ||
      !Number.isInteger(nextPage) ||
      nextPage < 1 ||
      nextPage > totalPages ||
      nextPage === currentResult?.page
    ) {
      return;
    }

    state.isJobSearchLoading = true;
    clearError();
    showJobLoading();

    try {
      const result = await searchJobs({
        query: state.lastSearchQuery,
        sort: state.currentSort,
        page: nextPage,
        pageSize,
      });

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
