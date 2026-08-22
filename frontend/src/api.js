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

export async function analyzeConversationIntent({ message, cvId = null, jobDescription = null }) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${INTENT_ENDPOINT}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        cvId: cvId,
        job_description: jobDescription,
      }),
    });
  } catch (error) {
    throw new ApiError(
      "Không thể kết nối với backend.",
      0,
      error,
    );
  }

  const responseBody = await parseJsonResponse(response);

  if (!response.ok) {
    throw new ApiError(
      responseBody?.error?.message ||
        responseBody?.message ||
        responseBody?.detail ||
        "Không thể xử lý yêu cầu.",
      response.status,
      responseBody,
    );
  }

  return normalizeIntentResponse(responseBody, Boolean(cvId));
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

  if (data?.primary_intent === "small_talk") {
    return (
      "Xin chào! Mình có thể hỗ trợ bạn phân tích CV, " +
      "tìm việc, đánh giá độ phù hợp công việc và " +
      "định hướng nghề nghiệp."
    );
  }

  if (data?.primary_intent === "out_of_scope") {
    return (
      "Mình chuyên hỗ trợ CV, tìm việc, phỏng vấn và " +
      "định hướng nghề nghiệp. Bạn hãy đặt câu hỏi liên " +
      "quan đến các nội dung này nhé."
    );
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
    job_matching: "đánh giá độ phù hợp công việc",
    career_advice: "tư vấn nghề nghiệp",
    cover_letter: "viết cover letter",
    general_question: "câu hỏi nghề nghiệp chung",
    small_talk: "trò chuyện thông thường",
    out_of_scope: "ngoài phạm vi hỗ trợ",
    clarification: "cần làm rõ thêm",
  };

  return labels[intent] ?? "câu hỏi chung";
}