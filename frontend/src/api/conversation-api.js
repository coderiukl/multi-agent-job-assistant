import { requestJson } from "./http-client.js";
import { normalizeConversationResponse } from "./normalizers.js";

const CONVERSATION_ENDPOINT = "/api/v1/conversation/messages";

export async function sendConversationMessage({
  threadId,
  message,
  cvId = null,
  jobDescription = null,
}) {
  const responseBody = await requestJson(
    CONVERSATION_ENDPOINT,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        thread_id: threadId,
        message,
        cv_id: cvId,
        job_description: jobDescription,
      }),
    },
    "Không thể kết nối với dịch vụ hội thoại.",
  );

  return normalizeConversationResponse(responseBody);
}

export async function getConversationHistory(threadId) {
  const encodedThreadId = encodeURIComponent(threadId);

  const responseBody = await requestJson(
    `/api/v1/conversation/threads/${encodedThreadId}/messages`,
    { method: "GET" },
    "Không thể tải lịch sử cuộc trò chuyện.",
  );

  const data = responseBody?.data ?? responseBody;

  return {
    threadId: data?.thread_id ?? threadId,
    messages: normalizeHistoryMessages(data?.messages),
  };
}

export async function deleteConversationHistory(threadId) {
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
    }))
    .filter((message) => message.text.trim());
}