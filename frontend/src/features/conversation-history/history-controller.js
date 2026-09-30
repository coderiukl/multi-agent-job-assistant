import {
  deleteConversationHistory,
  getConversationHistory,
  listConversationThreads,
} from "../../api.js";
import {
  MAX_CONVERSATION_TITLE_LENGTH,
} from "../../core/constants.js";
import {
  persistConversationThreads,
  persistThreadId,
} from "../../core/conversation-storage.js";
import {
  deleteConversationSnapshot,
  loadConversationSnapshot,
  persistConversationSnapshot,
} from "../../core/conversation-cache.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";

const RESULT_FIELDS = {
  job_search: "jobSearchResult",
  job_matching: "jobMatchingResult",
  cv_analysis: "cvAnalysisResult",
  career_advice: "careerAdviceResult",
  cover_letter: "coverLetterResult",
};

const RESULT_TYPE_LABELS = {
  job_search: "Việc làm",
  job_matching: "So khớp",
  cv_analysis: "CV",
  career_advice: "Tư vấn",
  cover_letter: "Thư",
};

export function createHistoryController({
  addMessage,
  resetConversation,
  showError,
}) {
  let searchQuery = "";

  function saveThreadId(threadId) {
    state.threadId = threadId;
    persistThreadId(threadId);
  }

  function saveConversationThreads() {
    persistConversationThreads(state.conversationThreads);
  }

  function createConversationTitle(message) {
    const normalizedMessage = String(message ?? "")
      .replace(/\s+/g, " ")
      .trim();

    if (!normalizedMessage) return "Cuộc trò chuyện mới";
    if (normalizedMessage.length <= MAX_CONVERSATION_TITLE_LENGTH) {
      return normalizedMessage;
    }

    return normalizedMessage
      .slice(0, MAX_CONVERSATION_TITLE_LENGTH - 1)
      .trimEnd() + "…";
  }

  function rememberConversationThread({
    threadId,
    firstMessage,
    context = null,
    touch = true,
  }) {
    const existingThread = state.conversationThreads.find(
      (thread) => thread.threadId === threadId,
    );
    const nextThread = {
      ...existingThread,
      threadId,
      title:
        existingThread?.title ?? createConversationTitle(firstMessage),
      preview: firstMessage || existingThread?.preview || "",
      hasCv: Boolean(context?.cvId || existingThread?.hasCv),
      hasJd: Boolean(context?.jobDescription || existingThread?.hasJd),
      resultTypes: existingThread?.resultTypes ?? [],
      pinned: Boolean(existingThread?.pinned),
      updatedAt: touch
        ? new Date().toISOString()
        : existingThread?.updatedAt ?? new Date().toISOString(),
    };

    state.conversationThreads = [
      nextThread,
      ...state.conversationThreads.filter(
        (thread) => thread.threadId !== threadId,
      ),
    ];

    saveConversationThreads();
    renderConversationHistory();
  }

  function updateConversationThread(threadId, patch) {
    const exists = state.conversationThreads.some(
      (thread) => thread.threadId === threadId,
    );
    if (!exists) return;

    state.conversationThreads = state.conversationThreads.map(
      (thread) => thread.threadId === threadId
        ? { ...thread, ...patch }
        : thread,
    );
    saveConversationThreads();
    renderConversationHistory();
  }

  function cacheCurrentConversation() {
    const latestContext = [...state.messages]
      .reverse()
      .find((message) => message.context)?.context ?? {
        cvId: state.uploadedCvId,
        cvName: state.uploadedCvName,
        jobDescription: state.jobDescription || null,
      };

    return persistConversationSnapshot(state.threadId, {
      messages: state.messages,
      results: state.conversationResults,
      latestContext,
      cvId: latestContext?.cvId ?? state.uploadedCvId,
      cvName: latestContext?.cvName ?? state.uploadedCvName,
      jobDescription: latestContext?.jobDescription ?? state.jobDescription ?? null,
      pendingHumanReview: state.pendingHumanReview,
    });
  }

  function formatConversationTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const today = new Date();
    const isToday =
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate();

    return new Intl.DateTimeFormat("vi-VN", isToday
      ? { hour: "2-digit", minute: "2-digit" }
      : { day: "2-digit", month: "2-digit" }
    ).format(date);
  }

  function renderConversationHistory() {
    const list = elements.conversationHistoryList;
    const emptyState = elements.conversationHistoryEmpty;
    if (!list || !emptyState) return;

    const query = searchQuery.trim().toLocaleLowerCase("vi-VN");
    const threads = [...state.conversationThreads]
      .filter((thread) => {
        if (!query) return true;
        return [thread.title, thread.preview]
          .filter(Boolean)
          .some((value) => String(value)
            .toLocaleLowerCase("vi-VN")
            .includes(query));
      })
      .sort((left, right) => {
        if (left.pinned !== right.pinned) {
          return Number(right.pinned) - Number(left.pinned);
        }
        return new Date(right.updatedAt) - new Date(left.updatedAt);
      });

    list.innerHTML = "";
    emptyState.hidden = threads.length > 0;
    updateEmptyState(Boolean(query));

    for (const group of groupThreadsByDate(threads)) {
      const section = document.createElement("section");
      const heading = document.createElement("h3");
      const groupList = document.createElement("div");

      section.className = "conversation-history-group";
      heading.className = "conversation-history-group-title";
      heading.textContent = group.label;
      groupList.className = "conversation-history-group-list";

      for (const thread of group.threads) {
        groupList.append(createThreadRow(thread));
      }

      section.append(heading, groupList);
      list.append(section);
    }
  }

  function updateEmptyState(filtered) {
    const emptyState = elements.conversationHistoryEmpty;
    const title = emptyState?.querySelector("strong");
    const description = emptyState?.querySelector("span");
    const action = elements.historyEmptyNewChatButton;
    if (!title || !description) return;

    title.textContent = filtered
      ? "Không tìm thấy cuộc trò chuyện"
      : "Chưa có cuộc trò chuyện";
    description.textContent = filtered
      ? "Thử một từ khóa khác hoặc xóa bộ lọc tìm kiếm."
      : "Bắt đầu một cuộc trò chuyện để lưu lại nội dung và kết quả.";
    if (action) action.hidden = filtered;
  }

  function createThreadRow(thread) {
    const row = document.createElement("div");
    const button = document.createElement("button");
    const menuButton = document.createElement("button");
    const menu = document.createElement("div");
    const title = document.createElement("span");
    const preview = document.createElement("span");
    const footer = document.createElement("span");
    const badges = document.createElement("span");
    const time = document.createElement("span");

    row.className = "conversation-history-row";
    row.dataset.historyRow = thread.threadId;

    button.type = "button";
    button.className = "conversation-history-item";
    button.dataset.threadId = thread.threadId;
    button.classList.toggle("is-active", thread.threadId === state.threadId);
    button.title = thread.title;
    if (thread.threadId === state.threadId) {
      button.setAttribute("aria-current", "true");
    }

    title.className = "conversation-history-title";
    title.textContent = thread.title;
    preview.className = "conversation-history-preview";
    preview.textContent = thread.preview || "Chưa có nội dung xem trước";

    footer.className = "conversation-history-footer";
    badges.className = "conversation-history-badges";
    if (thread.pinned) badges.append(createBadge("Đã ghim", "●"));
    if (thread.hasCv) badges.append(createBadge("Có CV", "CV"));
    if (thread.hasJd) badges.append(createBadge("Có JD", "JD"));
    if (thread.hasPendingHumanReview) {
      badges.append(createBadge("Đang chờ duyệt", "Duyệt"));
    }

    const resultType = thread.resultTypes?.at(-1);
    if (resultType) {
      badges.append(createBadge(
        "Có kết quả",
        RESULT_TYPE_LABELS[resultType] ?? "Result",
      ));
    }

    time.className = "conversation-history-time";
    time.textContent = formatConversationTime(thread.updatedAt);
    footer.append(badges, time);
    button.append(title, preview, footer);

    menuButton.type = "button";
    menuButton.className = "conversation-history-menu-button";
    menuButton.dataset.historyMenuButton = thread.threadId;
    menuButton.setAttribute(
      "aria-label",
      `Tùy chọn cho cuộc trò chuyện ${thread.title}`,
    );
    menuButton.title = "Tùy chọn";
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.textContent = "⋯";

    menu.className = "conversation-history-menu";
    menu.dataset.historyMenu = thread.threadId;
    menu.hidden = true;
    menu.append(
      createMenuAction(
        thread.pinned ? "Bỏ ghim" : "Ghim",
        "toggle-pin",
        thread.threadId,
      ),
      createMenuAction("Đổi tên", "rename", thread.threadId),
      createMenuAction("Xóa", "delete", thread.threadId, true),
    );

    row.append(button, menuButton, menu);
    return row;
  }

  function createMenuAction(label, action, threadId, danger = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.historyAction = action;
    button.dataset.historyThreadId = threadId;
    button.textContent = label;
    button.classList.toggle("is-danger", danger);
    return button;
  }

  function createBadge(label, text) {
    const badge = document.createElement("span");
    badge.className = "conversation-history-badge";
    badge.title = label;
    badge.textContent = text;
    return badge;
  }

  function groupThreadsByDate(threads) {
    const groups = new Map();
    for (const thread of threads) {
      const label = getDateGroupLabel(thread);
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(thread);
    }
    return [...groups].map(([label, groupedThreads]) => ({
      label,
      threads: groupedThreads,
    }));
  }

  function getDateGroupLabel(thread) {
    if (thread.pinned) return "Đã ghim";

    const date = new Date(thread.updatedAt);
    const today = new Date();
    const startOfToday = new Date(
      today.getFullYear(), today.getMonth(), today.getDate(),
    );
    const startOfDate = new Date(
      date.getFullYear(), date.getMonth(), date.getDate(),
    );
    const daysAgo = Math.round(
      (startOfToday - startOfDate) / 86_400_000,
    );

    if (daysAgo <= 0) return "Hôm nay";
    if (daysAgo === 1) return "Hôm qua";
    if (daysAgo <= 7) return "7 ngày qua";
    return "Cũ hơn";
  }

  function setSearchQuery(value) {
    searchQuery = String(value ?? "");
    renderConversationHistory();
  }

  function closeHistoryMenus() {
    const list = elements.conversationHistoryList;
    if (!list) return;

    for (const menu of list.querySelectorAll("[data-history-menu]")) {
      menu.hidden = true;
    }
    for (const button of list.querySelectorAll("[data-history-menu-button]")) {
      button.setAttribute("aria-expanded", "false");
    }
  }

  function toggleHistoryMenu(threadId) {
    const menu = elements.conversationHistoryList?.querySelector(
      `[data-history-menu="${threadId}"]`,
    );
    const button = elements.conversationHistoryList?.querySelector(
      `[data-history-menu-button="${threadId}"]`,
    );
    const willOpen = Boolean(menu?.hidden);

    closeHistoryMenus();
    if (!menu || !button || !willOpen) return;
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    menu.querySelector("button")?.focus();
  }

  function togglePinned(threadId) {
    const thread = state.conversationThreads.find(
      (item) => item.threadId === threadId,
    );
    if (thread) updateConversationThread(threadId, { pinned: !thread.pinned });
  }

  function startRename(threadId) {
    const thread = state.conversationThreads.find(
      (item) => item.threadId === threadId,
    );
    const title = elements.conversationHistoryList
      ?.querySelector(`[data-history-row="${threadId}"]`)
      ?.querySelector(".conversation-history-title");
    if (!thread || !title) return;

    const input = document.createElement("input");
    let completed = false;
    input.className = "conversation-history-rename-input";
    input.value = thread.title;
    input.maxLength = MAX_CONVERSATION_TITLE_LENGTH;
    title.replaceWith(input);
    input.focus();
    input.select();

    const finish = ({ cancel = false } = {}) => {
      if (completed) return;
      completed = true;
      const nextTitle = input.value.replace(/\s+/g, " ").trim();
      if (!cancel && nextTitle) {
        updateConversationThread(threadId, { title: nextTitle });
      } else {
        renderConversationHistory();
      }
    };

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") finish();
      if (event.key === "Escape") finish({ cancel: true });
    });
    input.addEventListener("blur", () => finish());
  }

  async function deleteThread(threadId) {
    if (!threadId) return;
    const thread = state.conversationThreads.find(
      (item) => item.threadId === threadId,
    );
    if (!window.confirm(`Xóa cuộc trò chuyện “${thread?.title ?? "này"}”?`)) {
      return;
    }

    try {
      await deleteConversationHistory(threadId);
    } catch (error) {
      showError(error?.message ?? "Không thể xóa cuộc trò chuyện.");
      return;
    }

    state.conversationThreads = state.conversationThreads.filter(
      (item) => item.threadId !== threadId,
    );
    await deleteConversationSnapshot(threadId);
    saveConversationThreads();
    if (threadId === state.threadId) {
      resetConversation();
      return;
    }
    renderConversationHistory();
  }

  async function handleHistoryClick(event) {
    const menuButton = event.target.closest("[data-history-menu-button]");
    if (menuButton) {
      toggleHistoryMenu(menuButton.dataset.historyMenuButton);
      return;
    }

    const actionButton = event.target.closest("[data-history-action]");
    if (actionButton) {
      const threadId = actionButton.dataset.historyThreadId;
      const action = actionButton.dataset.historyAction;
      closeHistoryMenus();
      if (action === "toggle-pin") togglePinned(threadId);
      if (action === "rename") startRename(threadId);
      if (action === "delete") await deleteThread(threadId);
      return;
    }

    const button = event.target.closest("[data-thread-id]");
    if (!button) return;
    const threadId = button.dataset.threadId;
    if (!threadId || threadId === state.threadId) return;

    saveThreadId(threadId);
    window.location.reload();
  }

  function handleDocumentClick(event) {
    if (!event.target.closest(".conversation-history-row")) {
      closeHistoryMenus();
    }
  }

  function handleDocumentKeydown(event) {
    if (event.key === "Escape") closeHistoryMenus();
  }

  async function restoreConversationHistory() {
    const cachedHistory = await loadConversationSnapshot(state.threadId);

    try {
      const serverHistory = await getConversationHistory(state.threadId);
      const history = mergeConversationHistory(serverHistory, cachedHistory);
      if (!history.messages.length) return false;

      saveThreadId(history.threadId);
      for (const message of history.messages) {
        addMessage({
          role: message.role,
          text: message.text,
          context: message.context,
          result: message.result,
        }, { cache: false });
      }

      const firstUserMessage = history.messages.find(
        (message) => message.role === "user",
      );
      const latestUserMessage = [...history.messages]
        .reverse()
        .find((message) => message.role === "user");
      const resultTypes = [
        ...new Set((history.results ?? []).flatMap(({ conversation }) =>
          Object.entries(RESULT_FIELDS)
            .filter(([, field]) => conversation?.[field])
            .map(([type]) => type),
        )),
      ];

      if (firstUserMessage) {
        rememberConversationThread({
          threadId: history.threadId,
          firstMessage: firstUserMessage.text,
          context: history.latestContext,
          touch: false,
        });
        updateConversationThread(history.threadId, {
          preview: latestUserMessage?.text ?? firstUserMessage.text,
          hasCv: Boolean(history.cvId),
          hasJd: Boolean(history.jobDescription),
          resultTypes,
        });
      }

      elements.suggestionList.hidden = true;
      return history;
    } catch (error) {
      console.warn("Conversation history could not be restored:", error);

      if (cachedHistory?.messages?.length) {
        return restoreCachedConversation(cachedHistory);
      }

      return null;
    }
  }

  async function restoreConversationThreads() {
    const hadLocalThreads = state.conversationThreads.length > 0;

    try {
      const serverThreads = await listConversationThreads();
      const localThreads = new Map(
        state.conversationThreads.map((thread) => [thread.threadId, thread]),
      );

      state.conversationThreads = serverThreads.map((thread) => {
        const localThread = localThreads.get(thread.threadId);
        return {
          ...thread,
          title: localThread?.title ?? thread.title,
          pinned: Boolean(localThread?.pinned),
        };
      });

      saveConversationThreads();

      const currentThreadExists = state.conversationThreads.some(
        (thread) => thread.threadId === state.threadId,
      );
      if (
        !hadLocalThreads &&
        !currentThreadExists &&
        state.conversationThreads.length
      ) {
        saveThreadId(state.conversationThreads[0].threadId);
      }

      renderConversationHistory();
      return state.conversationThreads;
    } catch (error) {
      console.warn("Conversation threads could not be restored:", error);
      renderConversationHistory();
      return state.conversationThreads;
    }
  }

  function mergeConversationHistory(serverHistory, cachedHistory) {
    if (!cachedHistory?.messages?.length) return serverHistory;

    const useCachedMessages =
      cachedHistory.messages.length > serverHistory.messages.length;

    return {
      ...serverHistory,
      messages: useCachedMessages
        ? cachedHistory.messages
        : serverHistory.messages,
      results: serverHistory.results?.length
        ? serverHistory.results
        : cachedHistory.results ?? [],
      latestContext: serverHistory.latestContext ?? cachedHistory.latestContext ?? null,
      cvId: serverHistory.cvId ?? cachedHistory.cvId ?? null,
      cvName: serverHistory.cvName ?? cachedHistory.cvName ?? null,
      jobDescription: serverHistory.jobDescription ?? cachedHistory.jobDescription ?? null,
      pendingHumanReview: serverHistory.pendingHumanReview ?? null,
    };
  }

  function restoreCachedConversation(cachedHistory) {
    const history = {
      threadId: cachedHistory.threadId,
      messages: cachedHistory.messages ?? [],
      results: cachedHistory.results ?? [],
      latestContext: cachedHistory.latestContext ?? null,
      cvId: cachedHistory.cvId ?? null,
      cvName: cachedHistory.cvName ?? null,
      jobDescription: cachedHistory.jobDescription ?? null,
      pendingHumanReview: cachedHistory.pendingHumanReview ?? null,
    };

    for (const message of history.messages) {
      addMessage(message, { cache: false });
    }

    elements.suggestionList.hidden = true;
    return history;
  }

  return {
    cacheCurrentConversation,
    closeHistoryMenus,
    handleDocumentClick,
    handleDocumentKeydown,
    handleHistoryClick,
    rememberConversationThread,
    renderConversationHistory,
    restoreConversationHistory,
    restoreConversationThreads,
    saveThreadId,
    setSearchQuery,
    updateConversationThread,
  };
}
