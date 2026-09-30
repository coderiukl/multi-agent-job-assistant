const ACCESS_TOKEN_KEY = "multi-agent-job-assistant-access-token";

export function getAccessToken() {
  try {
    return sessionStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveAccessToken(token) {
  if (typeof token !== "string" || !token.trim()) {
    throw new TypeError("A valid access token is required.");
  }

  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken() {
  try {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  } catch {}
}
