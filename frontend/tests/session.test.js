import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import {
  clearAccessToken, forgetAuthenticatedUser, getAccessToken,
  getSessionContext, isSessionCurrent, revisionKey,
  saveAccessToken, setAuthenticatedUser,
} from "../src/core/auth-storage.js";
import {
  loadConversationThreads, persistConversationThreads,
} from "../src/core/conversation-storage.js";

class MemoryStorage {
  values = new Map();
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

beforeEach(() => {
  globalThis.localStorage = new MemoryStorage();
  globalThis.sessionStorage = new MemoryStorage();
  forgetAuthenticatedUser();
});

test("logout invalidates the current session", () => {
  saveAccessToken("token-a");
  setAuthenticatedUser("alice");
  const session = getSessionContext();
  clearAccessToken();
  assert.equal(getAccessToken(), null);
  assert.equal(isSessionCurrent(session), false);
});

test("switching account rejects the previous session", () => {
  saveAccessToken("token-a");
  setAuthenticatedUser("alice");
  const previous = getSessionContext();
  saveAccessToken("token-b");
  setAuthenticatedUser("bob");
  assert.equal(isSessionCurrent(previous), false);
  assert.equal(getSessionContext().userId, "bob");
});

test("revision change from another tab invalidates the token", () => {
  saveAccessToken("token-a");
  setAuthenticatedUser("alice");
  localStorage.setItem(revisionKey("alice"), "another-revision");
  assert.equal(getAccessToken(), null);
  assert.equal(getSessionContext(), null);
});

test("another account revision does not end this session", () => {
  saveAccessToken("token-a");
  setAuthenticatedUser("alice");
  localStorage.setItem(revisionKey("bob"), "another-revision");
  assert.equal(getAccessToken(), "token-a");
});

test("conversation metadata is isolated by account", () => {
  saveAccessToken("token-a");
  setAuthenticatedUser("alice");
  persistConversationThreads([{
    threadId: "alice-thread", title: "Private", updatedAt: new Date().toISOString(),
  }]);
  saveAccessToken("token-b");
  setAuthenticatedUser("bob");
  assert.deepEqual(loadConversationThreads(), []);
  saveAccessToken("new-token-a");
  setAuthenticatedUser("alice");
  assert.equal(loadConversationThreads()[0].threadId, "alice-thread");
});
