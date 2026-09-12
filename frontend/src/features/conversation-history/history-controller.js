import {
  deleteConversationHistory,
  getConversationHistory,
} from "../../api.js";
import {
  MAX_CONVERSATION_TITLE_LENGTH,
  MAX_SAVED_CONVERSATIONS,
} from "../../core/constants.js";
import {
  persistConversationThreads,
  persistThreadId,
} from "../../core/conversation-storage.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";

export function createHistoryController({
  addMessage,
  resetConversation,
  showError,
}) {
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

    if (!normalizedMessage) {
      return "Cuộc trò chuyện mới";
    }

    if (normalizedMessage.length <= MAX_CONVERSATION_TITLE_LENGTH) {
      return normalizedMessage;
    }

    return (
      normalizedMessage
        .slice(0, MAX_CONVERSATION_TITLE_LENGTH - 1)
        .trimEnd() + "…"
    );
  }

  function rememberConversationThread({ threadId, firstMessage }) {
    const existingThread = state.conversationThreads.find(
      (thread) => thread.threadId === threadId,
    );
    const nextThread = {
      threadId,
      title:
        existingThread?.title ??
        createConversationTitle(firstMessage),
      updatedAt: new Date().toISOString(),
    };

    state.conversationThreads = [
      nextThread,
      ...state.conversationThreads.filter(
        (thread) => thread.threadId !== threadId,
      ),
    ].slice(0, MAX_SAVED_CONVERSATIONS);

    saveConversationThreads();
    renderConversationHistory();
  }

  function formatConversationTime(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "";
    }

    const today = new Date();
    const isToday =
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate();

    if (isToday) {
      return new Intl.DateTimeFormat("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    }

    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  }

  function renderConversationHistory() {
    const list = elements.conversationHistoryList;
    const emptyState = elements.conversationHistoryEmpty;

    if (!list || !emptyState) {
      return;
    }

    list.innerHTML = "";
    emptyState.hidden = state.conversationThreads.length > 0;

    for (const thread of state.conversationThreads) {
      const row = document.createElement("div");
      const button = document.createElement("button");
      const deleteButton = document.createElement("button");

      row.className = "conversation-history-row";
      button.type = "button";
      button.className = "conversation-history-item";
      button.dataset.threadId = thread.threadId;

      deleteButton.type = "button";
      deleteButton.className = "conversation-history-delete";
      deleteButton.dataset.deleteThreadId = thread.threadId;
      deleteButton.setAttribute(
        "aria-label",
        `Xóa cuộc trò chuyện ${thread.title}`,
      );
      deleteButton.title = "Xóa cuộc trò chuyện";
      deleteButton.textContent = "×";

      const isActive = thread.threadId === state.threadId;
      button.classList.toggle("is-active", isActive);

      if (isActive) {
        button.setAttribute("aria-current", "true");
      }

      const title = document.createElement("span");
      title.className = "conversation-history-title";
      title.textContent = thread.title;

      const time = document.createElement("span");
      time.className = "conversation-history-time";
      time.textContent = formatConversationTime(thread.updatedAt);

      button.append(title, time);
      row.append(button, deleteButton);
      list.append(row);
    }
  }

  async function deleteThread(threadId) {
    if (!threadId) {
      return;
    }

    const thread = state.conversationThreads.find(
      (item) => item.threadId === threadId,
    );
    const confirmed = window.confirm(
      `Xóa cuộc trò chuyện “${thread?.title ?? "này"}”?`,
    );

    if (!confirmed) {
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
    saveConversationThreads();

    if (threadId === state.threadId) {
      resetConversation();
      return;
    }

    renderConversationHistory();
  }

  async function handleHistoryClick(event) {
    const deleteButton = event.target.closest(
      "[data-delete-thread-id]",
    );

    if (deleteButton) {
      await deleteThread(deleteButton.dataset.deleteThreadId);
      return;
    }

    const button = event.target.closest("[data-thread-id]");

    if (!button) {
      return;
    }

    const threadId = button.dataset.threadId;

    if (!threadId || threadId === state.threadId) {
      return;
    }

    saveThreadId(threadId);
    window.location.reload();
  }

  async function restoreConversationHistory() {
    try {
      const history = await getConversationHistory(state.threadId);

      if (!history.messages.length) {
        return false;
      }

      saveThreadId(history.threadId);

      for (const message of history.messages) {
        addMessage({ role: message.role, text: message.text });
      }

      const firstUserMessage = history.messages.find(
        (message) => message.role === "user",
      );

      if (firstUserMessage) {
        rememberConversationThread({
          threadId: history.threadId,
          firstMessage: firstUserMessage.text,
        });
      }

      elements.suggestionList.hidden = true;
      return true;
    } catch (error) {
      console.warn(
        "Conversation history could not be restored:",
        error,
      );
      return false;
    }
  }

  return {
    handleHistoryClick,
    rememberConversationThread,
    renderConversationHistory,
    restoreConversationHistory,
    saveThreadId,
  };
}
