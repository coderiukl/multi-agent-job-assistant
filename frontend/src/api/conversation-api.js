import { requestJson } from "./http-client.js";
import { normalizeConversationResponse } from "./normalizers.js";

const CONVERSATION_ENDPOINT = "/api/v1/conversation/messages";

export async function listConversationThreads() {
  const responseBody = await requestJson(
    "/api/v1/conversation/threads",
    { method: "GET" },
    "Không thể tải danh sách cuộc trò chuyện.",
  );
  const data = responseBody?.data ?? responseBody;

  if (!Array.isArray(data)) return [];

  return data.map((thread) => ({
    threadId: thread.thread_id,
    title: thread.title || "Cuộc trò chuyện",
    preview: thread.preview || "",
    hasCv: Boolean(thread.has_cv),
    hasJd: Boolean(thread.has_job_description),
    resultTypes: Array.isArray(thread.result_types)
      ? thread.result_types
      : [],
    hasPendingHumanReview: Boolean(thread.has_pending_human_review),
    createdAt: thread.created_at,
    updatedAt: thread.updated_at || thread.created_at,
  })).filter((thread) => typeof thread.threadId === "string");
}

export async function sendConversationMessage({
  threadId,
  turnId = crypto.randomUUID(),
  message,
  cvId = null,
  cvName = null,
  jobDescription = null,
}) {
  if (typeof threadId !== "string" || !threadId.trim()) {
    throw new TypeError(
      "threadId is required when sending a conversation message.",
    );
  } 

  const payload = {
    thread_id: threadId,
    turn_id: turnId,
    message,
  };

  if (cvId !== null && cvId !== undefined) {
    payload.cv_id = cvId;
  }

  if (cvName !== null && cvName !== undefined) {
    payload.cv_name = cvName;
  }

  if (jobDescription !== null && jobDescription !== undefined) {
    payload.job_description = jobDescription;
  }

  const responseBody = await requestJson(
    CONVERSATION_ENDPOINT,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Không thể kết nối với dịch vụ hội thoại.",
  );

  return normalizeConversationResponse(responseBody);
}

export async function resumeConversation({
  threadId,
  turnId = crypto.randomUUID(),
  action,
  feedback = null,
}) {
  const responseBody = await requestJson(
    "/api/v1/conversation/resume",
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        thread_id: threadId,
        turn_id: turnId,
        decision: {
          action,
          feedback,
        },
      }),
    },
    "Không thể tiếp tục quá trình tạo Cover Letter."
  );

  return normalizeConversationResponse(responseBody);
}

export async function getConversationHistory(threadId) {
  if (typeof threadId !== "string" || !threadId.trim()) {
    throw new TypeError("threadId is required when sending a conversation message.");
  }

  const encodedThreadId = encodeURIComponent(threadId);

  const responseBody = await requestJson(
    `/api/v1/conversation/threads/${encodedThreadId}/messages`,
    { method: "GET" },
    "Không thể tải lịch sử cuộc trò chuyện.",
  );

  const data = responseBody?.data ?? responseBody;
  const messages = normalizeHistoryMessages(data?.messages);
  const newestMessages = [...messages].reverse();
  const fallbackContext = normalizeMessageContext({
    cv_id: data?.cv_id,
    cv_name: data?.cv_name,
    job_description: data?.job_description,
  });
  let latestContextMessage = newestMessages
    .find((message) => message.context);

  if (!latestContextMessage && fallbackContext) {
    latestContextMessage = newestMessages
      .find((message) => message.role === "user");

    if (latestContextMessage) {
      latestContextMessage.context = fallbackContext;
    }
  }

  const latestResultMessage = newestMessages
    .find((message) => message.result);
  const storedResults = collectStoredResults(messages);
  const fallbackResult = data?.latest_result
    ? normalizeConversationResponse({ data: data.latest_result })
    : null;

  if (!storedResults.length && fallbackResult) {
    storedResults.push({
      conversation: fallbackResult,
      originalMessage:
        newestMessages.find((message) => message.role === "user")
          ?.text ?? "",
    });
  }

  return {
    threadId: data?.thread_id ?? threadId,
    messages,
    cvId: data?.cv_id ?? null,
    cvName: data?.cv_name ?? null,
    jobDescription: data?.job_description ?? null,
    latestContext: latestContextMessage?.context ?? fallbackContext,
    latestResult:
      latestResultMessage?.result ??
      fallbackResult,
    results: storedResults,
    latestUserText:
      newestMessages.find((message) => message.role === "user")
        ?.text ?? "",
    pendingHumanReview: normalizeHumanReview(data?.pending_human_review),
  };
}

export function normalizeHumanReview(review) {
  if (!review || typeof review !== "object") {
    return null;
  }

  return {
    reviewType: review.review_type ?? null,
    message: review.message ?? "",
    data: review.data ?? {},
  };
}

function collectStoredResults(messages) {
  const results = [];
  let originalMessage = "";

  for (const message of messages) {
    if (message.role === "user") {
      originalMessage = message.text;
      continue;
    }

    if (message.result) {
      results.push({
        conversation: message.result,
        originalMessage,
      });
    }
  }

  return results;
}

export async function deleteConversationHistory(threadId) {
  if (typeof threadId !== "string" || !threadId.trim()) {
    throw new TypeError("threadId is required when sending a conversation message.");
  }
  
  const encodedThreadId = encodeURIComponent(threadId);

  await requestJson(
    `/api/v1/conversation/threads/${encodedThreadId}`,
    { method: "DELETE" },
    "Không thể xóa cuộc trò chuyện.",
  );
}

function normalizeHistoryMessages(messages) {
  if (!Array.isArray(messages)) {
    return [];
  }

  return messages
    .filter((message) => {
      return (
        message?.role === "user" ||
        message?.role === "assistant"
      );
    })
    .map((message) => ({
      id:
        message?.message_id ??
        crypto.randomUUID(),
      role: message.role,
      text: message?.content ?? "",
      context: normalizeMessageContext(message?.metadata?.context),
      result: message?.metadata?.result
        ? normalizeConversationResponse({
            data: message.metadata.result,
          })
        : null,
    }))
    .filter((message) => message.text.trim());
}

function normalizeMessageContext(context) {
  if (!context || typeof context !== "object") {
    return null;
  }

  const normalized = {
    cvId: context.cv_id ?? null,
    cvName: context.cv_name ?? null,
    jobDescription: context.job_description ?? null,
  };

  return normalized.cvId || normalized.cvName || normalized.jobDescription
    ? normalized
    : null;
}
