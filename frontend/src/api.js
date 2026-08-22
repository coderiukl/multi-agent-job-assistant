const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const INTENT_ENDPOINT = "/api/v1/conversation/intent-analysis";
const CV_ENDPOINT = "/api/v1/cvs";

export class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export async function analyzeConversationIntent({ message, hasCv }) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${INTENT_ENDPOINT}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        has_cv: hasCv,
        has_jd: false,
      }),
    });
  } catch (error) {
    throw new ApiError(
      "Không thể kết nối với backend. Hãy kiểm tra FastAPI và CORS.",
      0,
      error,
    );
  }

  const responseBody = await parseJsonResponse(response);

  if (!response.ok) {
    throw new ApiError(
      responseBody?.message ||
        responseBody?.detail ||
        responseBody?.error?.message ||
        "Không thể xử lý yêu cầu.",
      response.status,
      responseBody,
    );
  }

  return normalizeIntentResponse(responseBody, hasCv);
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
      "Không thể upload CV lên backend. Hãy kiểm tra FastAPI và CORS.",
      0,
      error,
    );
  }

  const responseBody = await parseJsonResponse(response);

  if (!response.ok) {
    throw new ApiError(
      responseBody?.message ||
        responseBody?.detail ||
        responseBody?.error?.message ||
        "Không thể upload hoặc xử lý CV.",
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

function normalizeIntentResponse(responseBody, hasCv) {
  const data = responseBody?.data ?? responseBody;
  const primaryIntent = data?.primary_intent ?? "general_question";
  const confidence = data?.confidence ?? null;

  return {
    answer: buildAssistantAnswer(data, hasCv),
    primaryIntent,
    confidence,
    hasCv,
  };
}

function buildAssistantAnswer(data, hasCv) {
  if (data?.needs_clarification && data?.clarification_question) {
    return data.clarification_question;
  }

  const label = formatIntentLabel(data?.primary_intent);
  const confidenceText =
    typeof data?.confidence === "number"
      ? ` Độ tin cậy: ${Math.round(data.confidence * 100)}%.`
      : "";
  const cvText = hasCv
    ? " Mình cũng đã ghi nhận rằng bạn đang đính kèm CV cho lượt hỏi này."
    : "";

  return `Mình đã phân loại yêu cầu này là “${label}”.${confidenceText}${cvText}`;
}

function formatIntentLabel(intent) {
  const labels = {
    cv_analysis: "phân tích CV",
    job_search: "tìm việc",
    job_matching: "ghép việc phù hợp",
    career_advice: "tư vấn nghề nghiệp",
    cover_letter: "viết cover letter",
    general_question: "câu hỏi chung",
    clarification: "cần làm rõ thêm",
  };

  return labels[intent] ?? "câu hỏi chung";
}
