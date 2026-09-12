import {
    CONVERSATION_THREAD_KEY,
    CONVERSATION_THREADS_KEY,
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

        return parsedValue.filter(isValidStoredThread).slice(0, MAX_SAVED_CONVERSATIONS);
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

function isValidStoredThread(item) {
    return (
        typeof item?.threadId === "string" &&
        typeof item?.title === "string" &&
        typeof item?.updatedAt === "string" &&
        item?.isDraft != true
    );
}