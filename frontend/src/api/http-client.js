const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  networkErrorMessage = "Không thể kết nối với backend.",
) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, options);
  } catch (error) {
    throw new ApiError(
      `${networkErrorMessage} Hãy kiểm tra FastAPI và CORS.`,
      0,
      error,
    );
  }

  const responseBody = await parseJsonResponse(response);

  if (!response.ok) {
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
    return details.map((item) => item?.msg).filter(Boolean).join(", ");
  }

  return (
    responseBody?.error?.message ||
    responseBody?.message ||
    responseBody?.detail ||
    "Không thể xử lý yêu cầu."
  );
}