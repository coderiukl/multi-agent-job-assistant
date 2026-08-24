const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const CONVERSATION_ENDPOINT = "/api/v1/conversation/messages";
const CV_ENDPOINT = "/api/v1/cvs";

export class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export async function sendConversationMessage({
  message,
  cvId = null,
  jobDescription = null,
}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${CONVERSATION_ENDPOINT}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        cv_id: cvId,
        job_description: jobDescription,
      }),
    });
  } catch (error) {
    throw new ApiError("Khong the ket noi voi backend.", 0, error);
  }

  const responseBody = await parseJsonResponse(response);

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(responseBody),
      response.status,
      responseBody,
    );
  }

  return normalizeConversationResponse(responseBody);
}

export async function uploadCv(file) {
  const formData = new FormData();
  formData.append("file", file);

  let response;

  try {
    response = await fetch(`${API_BASE_URL}${CV_ENDPOINT}`, {
      method: "POST",
      body: formData,
    });
  } catch (error) {
    throw new ApiError(
      "Khong the upload CV len backend. Hay kiem tra FastAPI va CORS.",
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

  return responseBody?.data ?? responseBody;
}

async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function normalizeConversationResponse(responseBody) {
  const data = responseBody?.data ?? responseBody;
  const intent = data?.intent ?? {};

  return {
    answer:
      data?.assistant_message ??
      "He thong da tiep nhan yeu cau cua ban.",
    status: data?.status ?? "completed",
    route: data?.route ?? "general_question",
    primaryIntent: intent?.primary_intent ?? "general_question",
    confidence:
      typeof intent?.confidence === "number" ? intent.confidence : null,
    cvId: data?.cv_id ?? null,
    missingInputs: Array.isArray(data?.missing_inputs)
      ? data.missing_inputs
      : [],
  };
}

function extractErrorMessage(responseBody) {
  return (
    responseBody?.error?.message ||
    responseBody?.message ||
    responseBody?.detail ||
    "Khong the xu ly yeu cau."
  );
}
