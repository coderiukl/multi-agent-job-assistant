import {
    CONVERSATION_THREAD_KEY,
    CONVERSATION_THREADS_KEY,
    CONVERSATION_OWNER_KEY,
    MAX_SAVED_CONVERSATIONS,
} from "./constants.js";

export function createThreadId() {
    return crypto.randomUUID();
}

export function getOrCreateThreadId() {
    try {
        const storedThreadId = localStorage.getItem(CONVERSATION_THREAD_KEY);

        if (storedThreadId) {
            return storedThreadId;
        }

        const threadId = createThreadId();

        localStorage.setItem(CONVERSATION_THREAD_KEY, threadId);

        return threadId;
    } catch {
        return createThreadId();
    }
}

export function persistThreadId(threadId) {
    try {
        localStorage.setItem(CONVERSATION_THREAD_KEY, threadId);
    } catch {}
}

export function loadConversationThreads() {
    try {
        const storedValue = localStorage.getItem(CONVERSATION_THREADS_KEY);

        if (!storedValue) {
            return [];
        }

        const parsedValue = JSON.parse(storedValue);

        if (!Array.isArray(parsedValue)) {
            return [];
        }

        return parsedValue
            .filter(isValidStoredThread)
            .map(normalizeStoredThread)
            .slice(0, MAX_SAVED_CONVERSATIONS);
    } catch {
        return [];
    }
}

export function persistConversationThreads(threads) {
    try {
        localStorage.setItem(CONVERSATION_THREADS_KEY, JSON.stringify(threads));
    } catch {
        
    }
}

export function clearConversationStorage() {
    try {
        localStorage.removeItem(CONVERSATION_THREAD_KEY);
        localStorage.removeItem(CONVERSATION_THREADS_KEY);
        localStorage.removeItem(CONVERSATION_OWNER_KEY);
    } catch {}
}

export function getConversationStorageOwner() {
    try {
        return localStorage.getItem(CONVERSATION_OWNER_KEY);
    } catch {
        return null;
    }
}

export function setConversationStorageOwner(userId) {
    if (typeof userId !== "string" || !userId.trim()) {
        throw new TypeError("A valid user ID is required.");
    }

    localStorage.setItem(CONVERSATION_OWNER_KEY, userId);
}

function isValidStoredThread(item) {
    return (
        typeof item?.threadId === "string" &&
        typeof item?.title === "string" &&
        typeof item?.updatedAt === "string" &&
        item?.isDraft != true
    );
}

function normalizeStoredThread(item) {
    return {
        ...item,
        pinned: Boolean(item.pinned),
        hasCv: Boolean(item.hasCv),
        hasJd: Boolean(item.hasJd),
        resultTypes: Array.isArray(item.resultTypes)
            ? item.resultTypes.filter((value) => typeof value === "string")
            : [],
        preview: typeof item.preview === "string" ? item.preview : "",
    };
}
