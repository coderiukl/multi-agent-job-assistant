const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const ENDPOINTS = {
  conversation: "/api/v1/conversation/messages",
  joSearch: "/api/v1/jobs/search",
  cvUpload: "/api/v1/cvs",
}

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
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
  const responseBody = await requestJson(
    ENDPOINTS.conversation,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        cv_id: cvId,
        job_description: jobDescription,
      }),
    },
    "Không thể kết nối với dịch vụ hội thoại.",
  );

  return normalizeConversationResponse(responseBody)

}

export async function searchJobs({
  query,
  filters = {},
  sort = "relevance",
  page = 1,
  pageSize = 10,
}) {
  const responseBody = await requestJson(
    ENDPOINTS.joSearch,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        filters,
        sort,
        page,
        page_size: pageSize,
      }),
    },
    "Không thể kết nối với dịch vụ tìm kiếm việc làm.",
  );

  const data = responseBody?.data ?? responseBody;

  return normalizeJobSearchResult(data);
}

export async function uploadCv(file) {
  const formData = new FormData();
  formData.append("file", file);

  const responseBody = await requestJson(
    ENDPOINTS.cvUpload,
    {
      method: "POST",
      body: formData,
    },
    "Không thể tải CV lên backend.",
  );

  const data = responseBody?.data ?? responseBody;

  return {
    fileId: data?.fileId ?? data?.file_id ?? null,
    fileName: data?.fileName ?? data?.file_name ?? file.name,
    fileSize: data?.fileSize ?? data?.file_size ?? file.size,
    contentType: data?.content_type ?? file.type,
    inspection: data?.inspection ?? null,
    extraction: data?.extraction ?? null,
    ocr: data?.ocr ?? null,
    profile: data?.profile ?? null,
  };
}

export async function requestJson(endpoint, options, networkErrorMessage) {
  let response;

  try {
    response = await fetch(
      `${API_BASE_URL}${endpoint}`,
      options,
    );
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

function normalizeConversationResponse(responseBody) {
  const data = responseBody?.data ?? responseBody;
  const intent = data?.intent ?? {};

  return {
    answer: data?.assistant_message ?? "Hệ thống đã tiếp nhận yêu cầu của bạn.",
    status: data?.status ?? "completed",
    route: data?.route ?? "general_question",
    primaryIntent: intent?.primary_intent ?? "general_question",
    confidence: typeof intent?.confidence === "number" ? intent.confidence : null,
    cvId: data?.cv_id ?? null,
    missingInputs: Array.isArray(data?.missing_inputs) ? data.missing_inputs : [],
    jobSearchResult: data?.job_search_result ? normalizeJobSearchResult(data.job_search_result) : null,
  };
}

function normalizeJobSearchResult(data) {
  if (!data || typeof data !== "object") {
    return {
      query: "",
      strategy: "postgres",
      total: 0,
      page: 1,
      pageSize: 10,
      items: [],
    };
  }

  const items = Array.isArray(data.items)
    ? data.items.map(normalizeJobSearchHit) : [];

  return {
    query: data.query ?? "",
    strategy: data.strategy ?? "postgres",
    total: typeof data.total === "number" ? data.total : items.length,
    page: typeof data.page === "number" ? data.page: 1,
    pageSize: typeof data.page_size === "number" ? data.page_size : 10,
    items,
  };
}

function normalizeJobSearchHit(hit) {
  return {
    job: hit?.job ?? {},
    score: {
      semantic: toNullableNumber(hit?.score?.semantic),
      keyword: toNumber(hit?.score?.keyword),
      filterMatch: toNumber(hit?.score?.filter_match),
      freshness: toNumber(hit?.score?.freshness),
      final: toNumber(hit?.score?.final),
    },
    matchedTerms: Array.isArray(hit?.matched_terms) ? hit.matched_terms : [],
    reasons: Array.isArray(hit?.reasons) ? hit.reasons : [],
  };
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function toNullableNumber(value) {
  if (value === null || value === undefined) {
    return null
  }

  const number = Number(value)

  return Number.isFinite(number) ? number : null;
}
function extractErrorMessage(responseBody) {
  const validationDetails = responseBody?.detail

  if (Array.isArray(validationDetails)) {
    return validationDetails
    .map((item) => item?.msg)
    .filter(Boolean)
    .join("; ");
  }
  return (
    responseBody?.error?.message ||
    responseBody?.message ||
    responseBody?.detail ||
    "Không thể xử lý yêu cầu." 
  );
}
