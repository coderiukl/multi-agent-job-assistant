const TOKEN_KEY = "multi-agent-job-assistant-access-token";
const USER_KEY = "multi-agent-job-assistant-auth-user";
const REVISION_KEY = "multi-agent-job-assistant-auth-revision";

let verifiedSession = null;

export const revisionKey = (userId) =>
  `job-assistant:revision:${userId}`;

export function getStoredUserId() {
  return sessionStorage.getItem(USER_KEY);
}

export function getAccessToken() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const userId = getStoredUserId();
  const revision = sessionStorage.getItem(REVISION_KEY);

  if (
    userId &&
    revision !== localStorage.getItem(revisionKey(userId))
  ) {
    return null;
  }

  return token;
}

export function saveAccessToken(token) {
  if (typeof token !== "string" || !token.trim()) {
    throw new TypeError("Invalid token.");
  }

  forgetAuthenticatedUser();
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function setAuthenticatedUser(userId) {
  const accessToken = getAccessToken();

  if (
    !accessToken ||
    typeof userId !== "string" ||
    !userId
  ) {
    throw new Error("Authenticated session is required.");
  }

  const key = revisionKey(userId);
  const revision =
    localStorage.getItem(key) ?? crypto.randomUUID();

  localStorage.setItem(key, revision);
  sessionStorage.setItem(USER_KEY, userId);
  sessionStorage.setItem(REVISION_KEY, revision);

  verifiedSession = Object.freeze({
    userId,
    accessToken,
    revision,
  });
}

export function isSessionCurrent(session) {
  return Boolean(
    session &&
    session === verifiedSession &&
    session.accessToken === getAccessToken() &&
    session.revision ===
      localStorage.getItem(revisionKey(session.userId))
  );
}

export function getSessionContext() {
  return isSessionCurrent(verifiedSession)
    ? verifiedSession
    : null;
}

export function clearAccessToken() {
  const userId = getStoredUserId();

  verifiedSession = null;
  sessionStorage.removeItem(TOKEN_KEY);

  if (userId) {
    localStorage.setItem(
      revisionKey(userId),
      crypto.randomUUID(),
    );
  }
}

export function forgetAuthenticatedUser() {
  verifiedSession = null;
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(REVISION_KEY);
}