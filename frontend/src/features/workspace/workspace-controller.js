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

  // Below this width the history sidebar is an off-canvas drawer.
  const drawerQuery = window.matchMedia("(max-width: 1023px)");
  let focusBeforeHistoryDrawer = null;

  function isHistoryDrawerMode() {
    return drawerQuery.matches;
  }

  function setConversationHistoryOpen(open, { restoreFocus = true } = {}) {
    const wasOpen = state.historyOpen;

    state.historyOpen = open;
    elements.workspace?.setAttribute(
      "data-history-open",
      String(open),
    );

    const drawerMode = isHistoryDrawerMode();

    if (elements.sidebarScrim) {
      elements.sidebarScrim.hidden = !(drawerMode && open);
    }

    // While the drawer is open, keep keyboard and screen-reader focus in it.
    const isModalDrawer = drawerMode && open;
    for (const region of [
      document.querySelector("#chat-panel"),
      elements.resultsPanel,
      document.querySelector(".app-header"),
      elements.mobileTabs,
    ]) {
      region?.toggleAttribute("inert", isModalDrawer);
    }
    elements.conversationSidebar?.setAttribute(
      "aria-modal",
      String(isModalDrawer),
    );
    if (isModalDrawer) {
      elements.conversationSidebar?.setAttribute("role", "dialog");
    } else {
      elements.conversationSidebar?.removeAttribute("role");
    }

    if (elements.historyDrawerButton) {
      elements.historyDrawerButton.setAttribute(
        "aria-expanded",
        String(drawerMode && open),
      );
    }

    if (elements.toggleHistoryButton) {
      const label = drawerMode
        ? "Đóng lịch sử"
        : open
          ? "Thu gọn lịch sử"
          : "Mở lịch sử";

      elements.toggleHistoryButton.setAttribute(
        "aria-expanded",
        String(open),
      );
      elements.toggleHistoryButton.setAttribute("aria-label", label);
      elements.toggleHistoryButton.title = label;
    }

    if (!drawerMode || wasOpen === open) {
      return;
    }

    if (open) {
      focusBeforeHistoryDrawer = document.activeElement;
      requestAnimationFrame(() => {
        elements.conversationHistorySearch?.focus();
      });
      return;
    }

    if (
      restoreFocus &&
      focusBeforeHistoryDrawer instanceof HTMLElement &&
      focusBeforeHistoryDrawer.isConnected
    ) {
      focusBeforeHistoryDrawer.focus();
    }

    focusBeforeHistoryDrawer = null;
  }

  function toggleConversationHistory() {
    setConversationHistoryOpen(!state.historyOpen);
  }

  /** Closes the history drawer on narrow screens; no-op on desktop. */
  function closeHistoryDrawer(options) {
    if (isHistoryDrawerMode() && state.historyOpen) {
      setConversationHistoryOpen(false, options);
      return true;
    }

    return false;
  }

  function initializeWorkspaceLayout() {
    // Start with the drawer closed on narrow screens; keep the desktop
    // sidebar open.
    setConversationHistoryOpen(!isHistoryDrawerMode(), { restoreFocus: false });

    drawerQuery.addEventListener("change", (event) => {
      setConversationHistoryOpen(!event.matches, { restoreFocus: false });
    });
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
    closeHistoryDrawer,
    closeJobDetail,
    closeResultsPanel,
    handleMobileTabClick,
    initializeWorkspaceLayout,
    isHistoryDrawerMode,
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
