import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";

export function createWorkspaceController() {
  function setActiveWorkspacePanel(panel) {
    const nextPanel = panel === "results" ? "results" : "chat";

    state.activeWorkspacePanel = nextPanel;
    elements.workspace?.setAttribute("data-active-panel", nextPanel);

    for (const button of elements.mobileTabButtons) {
      const isActive = button.dataset.panel === nextPanel;

      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    }
  }

  function updateResultsToggleButton() {
    if (!elements.toggleResultsButton) {
      return;
    }

    elements.toggleResultsButton.setAttribute(
      "aria-expanded",
      String(state.resultsOpen),
    );
    elements.toggleResultsButton.classList.toggle(
      "is-active",
      state.resultsOpen,
    );

    const label = elements.toggleResultsButton.querySelector(
      ".results-toggle-label",
    );

    if (label) {
      label.textContent = state.resultsOpen
        ? "Ẩn kết quả"
        : "Xem kết quả";
    }
  }

  function setResultsAvailability(isAvailable) {
    state.resultsAvailable = isAvailable;

    if (elements.toggleResultsButton) {
      elements.toggleResultsButton.hidden = !isAvailable;
    }

    if (elements.mobileResultsTab) {
      elements.mobileResultsTab.hidden = !isAvailable;
    }
  }

  function openResultsPanel() {
    setResultsAvailability(true);
    state.resultsOpen = true;
    elements.workspace?.setAttribute("data-results-open", "true");
    elements.resultsPanel?.setAttribute("aria-hidden", "false");
    updateResultsToggleButton();

    if (window.matchMedia("(max-width: 640px)").matches) {
      setActiveWorkspacePanel("results");
    }
  }

  function closeResultsPanel() {
    state.resultsOpen = false;
    elements.workspace?.setAttribute("data-results-open", "false");
    elements.resultsPanel?.setAttribute("aria-hidden", "true");
    updateResultsToggleButton();
    setActiveWorkspacePanel("chat");
  }

  function toggleResultsPanel() {
    if (state.resultsOpen) {
      closeResultsPanel();
      return;
    }

    openResultsPanel();
  }

  function handleMobileTabClick(event) {
    const button = event.target.closest("[data-panel]");

    if (!button) {
      return;
    }

    if (button.dataset.panel === "results") {
      openResultsPanel();
      return;
    }

    setActiveWorkspacePanel("chat");
  }

  function toggleConversationHistory() {
    state.historyOpen = !state.historyOpen;
    elements.workspace?.setAttribute(
      "data-history-open",
      String(state.historyOpen),
    );

    if (!elements.toggleHistoryButton) {
      return;
    }

    const label = state.historyOpen
      ? "Thu gọn lịch sử"
      : "Mở lịch sử";

    elements.toggleHistoryButton.setAttribute(
      "aria-expanded",
      String(state.historyOpen),
    );
    elements.toggleHistoryButton.setAttribute("aria-label", label);
    elements.toggleHistoryButton.title = label;

    const icon = elements.toggleHistoryButton.querySelector("span");

    if (icon) {
      icon.textContent = state.historyOpen ? "‹" : "☰";
    }
  }

  function updateMobileResultsBadge(count) {
    if (!elements.mobileResultsBadge) {
      return;
    }

    const normalizedCount = Math.max(0, Number(count) || 0);

    elements.mobileResultsBadge.hidden = normalizedCount === 0;
    elements.mobileResultsBadge.textContent =
      normalizedCount > 99 ? "99+" : String(normalizedCount);
  }

  function isJobDetailOpen() {
    return elements.jobDetailDrawer.classList.contains("is-open");
  }

  function closeJobDetail() {
    const wasOpen = isJobDetailOpen();

    elements.jobDetailOverlay.hidden = true;
    elements.jobDetailDrawer.classList.remove("is-open");
    elements.jobDetailDrawer.setAttribute("aria-hidden", "true");
    state.selectedJob = null;

    if (
      wasOpen &&
      state.lastFocusedBeforeDrawer instanceof HTMLElement
    ) {
      state.lastFocusedBeforeDrawer.focus();
    }

    state.lastFocusedBeforeDrawer = null;
  }

  function trapJobDetailFocus(event) {
    const focusableElements = elements.jobDetailDrawer.querySelectorAll(
      [
        "a[href]",
        "button:not([disabled])",
        "textarea:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
      ].join(","),
    );

    if (!focusableElements.length) {
      event.preventDefault();
      elements.jobDetailDrawer.focus();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  return {
    closeJobDetail,
    closeResultsPanel,
    handleMobileTabClick,
    isJobDetailOpen,
    openResultsPanel,
    setActiveWorkspacePanel,
    setResultsAvailability,
    toggleConversationHistory,
    toggleResultsPanel,
    trapJobDetailFocus,
    updateMobileResultsBadge,
  };
}
