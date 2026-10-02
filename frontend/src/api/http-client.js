import {
  getAccessToken,
  getSessionContext,
  isSessionCurrent,
} from "../core/auth-storage.js";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);

    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export async function requestJson(
  endpoint,
  options = {},
  networkErrorMessage =
    "Không thể kết nối với backend.",
) {
  let response;

  const headers = new Headers(options.headers);
  const accessToken = getAccessToken();
  const session = getSessionContext();

  const isAuthEntryEndpoint = [
    "/api/v1/auth/login",
    "/api/v1/auth/register",
  ].includes(endpoint);

  if (!isAuthEntryEndpoint && !accessToken) {
    window.dispatchEvent(
      new CustomEvent("auth:unauthorized"),
    );

    throw new ApiError(
      "Bạn cần đăng nhập lại.",
      401,
    );
  }

  if (
    accessToken &&
    !isAuthEntryEndpoint &&
    !headers.has("Authorization")
  ) {
    headers.set(
      "Authorization",
      `Bearer ${accessToken}`,
    );
  }

  try {
    response = await fetch(
      `${API_BASE_URL}${endpoint}`,
      {
        ...options,
        headers,
      },
    );
  } catch (error) {
    if (
      !isAuthEntryEndpoint &&
      (
        getAccessToken() !== accessToken ||
        (session && !isSessionCurrent(session))
      )
    ) {
      throw new ApiError(
        "Phiên đăng nhập đã thay đổi.",
        401,
      );
    }

    throw new ApiError(
      `${networkErrorMessage} Hãy kiểm tra FastAPI và CORS.`,
      0,
      error,
    );
  }

  const responseBody =
    await parseJsonResponse(response);

  if (
    !isAuthEntryEndpoint &&
    (
      getAccessToken() !== accessToken ||
      (session && !isSessionCurrent(session))
    )
  ) {
    throw new ApiError(
      "Phiên đăng nhập đã thay đổi.",
      401,
    );
  }

  if (!response.ok) {
    if (
      response.status === 401 &&
      accessToken &&
      !isAuthEntryEndpoint
    ) {
      window.dispatchEvent(
        new CustomEvent("auth:unauthorized"),
      );
    }

    throw new ApiError(
      extractErrorMessage(responseBody),
      response.status,
      responseBody,
    );
  }

  return responseBody;
}

async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractErrorMessage(responseBody) {
  const details = responseBody?.detail;

  if (Array.isArray(details)) {
    return details
      .map((item) => item?.msg)
      .filter(Boolean)
      .join(", ");
  }

  return (
    responseBody?.error?.message ||
    responseBody?.message ||
    responseBody?.detail ||
    "Không thể xử lý yêu cầu."
  );
}