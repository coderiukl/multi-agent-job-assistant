import {
  CONVERSATION_THREAD_KEY,
  CONVERSATION_THREADS_KEY,
  CONVERSATION_OWNER_KEY,
  MAX_SAVED_CONVERSATIONS,
} from "./constants.js";

import {
  getSessionContext,
  getStoredUserId,
} from "./auth-storage.js";

export function createThreadId() {
  return crypto.randomUUID();
}

function scopedKey(key) {
  const session = getSessionContext();

  return session
    ? `${key}:${session.userId}`
    : null;
}

export function getOrCreateThreadId() {
  const key = scopedKey(CONVERSATION_THREAD_KEY);

  if (!key) {
    return createThreadId();
  }

  const threadId =
    localStorage.getItem(key) ?? createThreadId();

  localStorage.setItem(key, threadId);

  return threadId;
}

export function persistThreadId(threadId) {
  const key = scopedKey(CONVERSATION_THREAD_KEY);

  if (key) {
    localStorage.setItem(key, threadId);
  }
}

export function loadConversationThreads() {
  const key = scopedKey(CONVERSATION_THREADS_KEY);

  if (!key) {
    return [];
  }

  try {
    const items = JSON.parse(
      localStorage.getItem(key) ?? "[]",
    );

    if (!Array.isArray(items)) {
      return [];
    }

    return items
      .filter((item) =>
        typeof item?.threadId === "string" &&
        typeof item?.title === "string" &&
        typeof item?.updatedAt === "string" &&
        !item.isDraft
      )
      .slice(0, MAX_SAVED_CONVERSATIONS)
      .map((item) => ({
        ...item,
        pinned: Boolean(item.pinned),
        hasCv: Boolean(item.hasCv),
        hasJd: Boolean(item.hasJd),
        preview: String(item.preview ?? ""),
        resultTypes: Array.isArray(item.resultTypes)
          ? item.resultTypes
          : [],
      }));
  } catch {
    return [];
  }
}

export function persistConversationThreads(threads) {
  const key = scopedKey(CONVERSATION_THREADS_KEY);

  if (key) {
    localStorage.setItem(key, JSON.stringify(threads));
  }
}

export function clearConversationStorage(
  userId = getStoredUserId(),
) {
  for (const key of [
    CONVERSATION_THREAD_KEY,
    CONVERSATION_THREADS_KEY,
  ]) {
    if (userId) {
      localStorage.removeItem(`${key}:${userId}`);
    }

    // Xóa dữ liệu cũ chưa được tách theo tài khoản.
    localStorage.removeItem(key);
  }

  localStorage.removeItem(CONVERSATION_OWNER_KEY);
}