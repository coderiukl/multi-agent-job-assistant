import {
  getSessionContext,
  isSessionCurrent,
  getStoredUserId,
} from "./auth-storage.js";

const LEGACY_DATABASE = "multi-agent-job-assistant";
const STORE = "conversation-snapshots";

const databases = new Map();
const writeQueues = new Map();

const databaseName = (userId) =>
  userId
    ? `${LEGACY_DATABASE}:${userId}`
    : LEGACY_DATABASE;

function openDatabase(userId) {
  const name = databaseName(userId);

  if (!globalThis.indexedDB) {
    return Promise.reject(
      new Error("IndexedDB unavailable."),
    );
  }

  if (!databases.has(name)) {
    const promise = new Promise((resolve, reject) => {
      const request = indexedDB.open(name, 1);

      request.onupgradeneeded = () => {
        if (
          !request.result.objectStoreNames.contains(STORE)
        ) {
          request.result.createObjectStore(STORE, {
            keyPath: "threadId",
          });
        }
      };

      request.onsuccess = () => {
        const database = request.result;

        database.onversionchange = () => {
          database.close();
          databases.delete(name);
        };

        resolve(database);
      };

      request.onerror = () => {
        databases.delete(name);
        reject(request.error);
      };
    });

    databases.set(name, promise);
  }

  return databases.get(name);
}

function mutate(database, operation) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(
      STORE,
      "readwrite",
    );

    operation(transaction.objectStore(STORE));

    transaction.oncomplete = resolve;
    transaction.onabort = () =>
      reject(transaction.error);
    transaction.onerror = () =>
      reject(transaction.error);
  });
}

function enqueue(session, threadId, operation) {
  const key = `${session.userId}:${threadId}`;

  const next = (
    writeQueues.get(key) ?? Promise.resolve()
  )
    .catch(() => {})
    .then(async () => {
      if (!isSessionCurrent(session)) {
        return;
      }

      const database = await openDatabase(
        session.userId,
      );

      if (!isSessionCurrent(session)) {
        return;
      }

      await mutate(database, operation);
    })
    .catch((error) => {
      console.warn("Cache update failed:", error);
    });

  writeQueues.set(key, next);

  next.finally(() => {
    if (writeQueues.get(key) === next) {
      writeQueues.delete(key);
    }
  });

  return next;
}

export function persistConversationSnapshot(
  threadId,
  snapshot,
) {
  const session = getSessionContext();

  if (!session || !threadId) {
    return Promise.resolve();
  }

  const value = structuredClone({
    ...snapshot,
    threadId,
    savedAt: new Date().toISOString(),
  });

  return enqueue(
    session,
    threadId,
    (store) => store.put(value),
  );
}

export async function loadConversationSnapshot(
  threadId,
) {
  const session = getSessionContext();

  if (!session || !threadId) {
    return null;
  }

  try {
    await writeQueues.get(
      `${session.userId}:${threadId}`,
    );

    if (!isSessionCurrent(session)) {
      return null;
    }

    const database = await openDatabase(
      session.userId,
    );

    if (!isSessionCurrent(session)) {
      return null;
    }

    const value = await new Promise(
      (resolve, reject) => {
        const transaction = database.transaction(
          STORE,
          "readonly",
        );

        const request = transaction
          .objectStore(STORE)
          .get(threadId);

        request.onsuccess = () =>
          resolve(request.result ?? null);

        request.onerror = () =>
          reject(request.error);
      },
    );

    return isSessionCurrent(session)
      ? value
      : null;
  } catch (error) {
    console.warn("Cache read failed:", error);
    return null;
  }
}

export function deleteConversationSnapshot(
  threadId,
) {
  const session = getSessionContext();

  if (!session || !threadId) {
    return Promise.resolve();
  }

  return enqueue(
    session,
    threadId,
    (store) => store.delete(threadId),
  );
}

export async function clearConversationCache(
  userId = getStoredUserId(),
) {
  const pending = [...writeQueues].filter(
    ([key]) =>
      userId && key.startsWith(`${userId}:`),
  );

  await Promise.allSettled(
    pending.map(([, promise]) => promise),
  );

  if (!globalThis.indexedDB) {
    return;
  }

  const owners = userId
    ? [userId, null]
    : [null];

  for (const owner of owners) {
    const database = await openDatabase(owner);

    // Xóa store ngay cả khi tab khác đang mở database.
    await mutate(
      database,
      (store) => store.clear(),
    );

    database.close();
    databases.delete(databaseName(owner));
  }
}