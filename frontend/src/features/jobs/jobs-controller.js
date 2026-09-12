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

  return {
    handleConversationSearch,
    handleSortChange,
  };
}
