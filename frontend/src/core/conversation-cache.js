const DATABASE_NAME = "multi-agent-job-assistant";
const DATABASE_VERSION = 1;
const STORE_NAME = "conversation-snapshots";

let databasePromise = null;
const writeQueues = new Map();

function openDatabase() {
  if (!globalThis.indexedDB) {
    return Promise.reject(new Error("IndexedDB is not available."));
  }

  if (databasePromise) {
    return databasePromise;
  }

  databasePromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);

    request.addEventListener("upgradeneeded", () => {
      const database = request.result;

      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: "threadId" });
      }
    });

    request.addEventListener("success", () => resolve(request.result));
    request.addEventListener("error", () => reject(request.error));
  });

  return databasePromise;
}

async function writeSnapshot(snapshot) {
  const database = await openDatabase();

  await new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(snapshot);
    transaction.addEventListener("complete", resolve);
    transaction.addEventListener("abort", () => reject(transaction.error));
    transaction.addEventListener("error", () => reject(transaction.error));
  });
}

export function persistConversationSnapshot(threadId, snapshot) {
  if (!threadId) return Promise.resolve();

  const previousWrite = writeQueues.get(threadId) ?? Promise.resolve();
  const nextWrite = previousWrite
    .catch(() => {})
    .then(() => writeSnapshot({
      ...snapshot,
      threadId,
      savedAt: new Date().toISOString(),
    }))
    .catch((error) => {
      console.warn("Conversation snapshot could not be saved:", error);
    });

  writeQueues.set(threadId, nextWrite);
  nextWrite.finally(() => {
    if (writeQueues.get(threadId) === nextWrite) {
      writeQueues.delete(threadId);
    }
  });

  return nextWrite;
}

export async function loadConversationSnapshot(threadId) {
  if (!threadId) return null;

  try {
    await writeQueues.get(threadId);
    const database = await openDatabase();

    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(threadId);
      request.addEventListener("success", () => resolve(request.result ?? null));
      request.addEventListener("error", () => reject(request.error));
    });
  } catch (error) {
    console.warn("Conversation snapshot could not be loaded:", error);
    return null;
  }
}

export async function deleteConversationSnapshot(threadId) {
  if (!threadId) return;

  try {
    await writeQueues.get(threadId);
    const database = await openDatabase();

    await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(threadId);
      transaction.addEventListener("complete", resolve);
      transaction.addEventListener("abort", () => reject(transaction.error));
      transaction.addEventListener("error", () => reject(transaction.error));
    });
  } catch (error) {
    console.warn("Conversation snapshot could not be deleted:", error);
  }
}

export async function clearConversationCache() {
  try {
    await Promise.allSettled(writeQueues.values());
    const database = databasePromise
      ? await databasePromise.catch(() => null)
      : null;

    database?.close();
    databasePromise = null;
    writeQueues.clear();

    if (!globalThis.indexedDB) return;

    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(DATABASE_NAME);
      request.addEventListener("success", resolve);
      request.addEventListener("blocked", resolve);
      request.addEventListener("error", () => reject(request.error));
    });
  } catch (error) {
    console.warn("Conversation cache could not be cleared:", error);
  }
}
