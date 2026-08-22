import React, { useEffect, useRef, useState } from "react";

import { analyzeConversationIntent, uploadCv } from "./api.js";

const MAX_FILE_SIZE = 10 * 1024 * 1024;

const suggestions = [
  {
    title: "Phân tích CV",
    message: "Phân tích điểm mạnh và điểm cần cải thiện trong CV của tôi",
  },
  {
    title: "Tìm việc phù hợp",
    message: "Tìm các vị trí phù hợp với kinh nghiệm trong CV của tôi",
  },
  {
    title: "Lộ trình kỹ năng",
    message: "Tôi cần học thêm gì để trở thành Data Engineer?",
  },
];

const initialMessages = [
  {
    id: "welcome",
    role: "assistant",
    text:
      "Xin chào! Mình là trợ lý nghề nghiệp AI của bạn. Mình có thể phân tích CV, tìm kiếm công việc phù hợp và tư vấn lộ trình phát triển nghề nghiệp.",
  },
];

export default function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState("");
  const [selectedCvFile, setSelectedCvFile] = useState(null);
  const [cvUploadStatus, setCvUploadStatus] = useState("idle");
  const [cvUploadResult, setCvUploadResult] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const messageListRef = useRef(null);
  const cvUploadRequestRef = useRef(0);

  const isUploadingCv = cvUploadStatus === "uploading";
  const hasUploadedCv = Boolean(selectedCvFile) && cvUploadStatus === "uploaded";

  useEffect(() => {
    messageListRef.current?.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isSending]);

  function resetConversation() {
    setMessages(initialMessages);
    setDraft("");
    setError("");
  }

  function openCvPicker() {
    fileInputRef.current?.click();
  }

  async function handleCvSelection(event) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const validationError = validateCvFile(file);

    if (validationError) {
      setError(validationError);
      setCvUploadStatus("idle");
      setCvUploadResult(null);
      event.target.value = "";
      return;
    }

    const requestId = cvUploadRequestRef.current + 1;
    cvUploadRequestRef.current = requestId;
    setSelectedCvFile(file);
    setCvUploadStatus("uploading");
    setCvUploadResult(null);
    setError("");

    try {
      const result = await uploadCv(file);

      if (cvUploadRequestRef.current !== requestId) {
        return;
      }

      setCvUploadResult(result);
      setCvUploadStatus("uploaded");
    } catch (uploadError) {
      if (cvUploadRequestRef.current !== requestId) {
        return;
      }

      setCvUploadStatus("failed");
      setError(uploadError.message || "Không thể upload CV.");
    }
  }

  function removeCv() {
    cvUploadRequestRef.current += 1;
    setSelectedCvFile(null);
    setCvUploadStatus("idle");
    setCvUploadResult(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const message = draft.trim();

    if (!message || isSending) {
      return;
    }

    if (isUploadingCv) {
      setError("CV đang được tải lên và xử lý. Vui lòng chờ hoàn tất rồi gửi lại.");
      return;
    }

    setError("");
    setDraft("");
    setIsSending(true);
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: crypto.randomUUID(),
        role: "user",
        text: message,
      },
    ]);

    try {
      const result = await analyzeConversationIntent({
        message,
        hasCv: hasUploadedCv,
      });

      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: result.answer,
          hasCv: result.hasCv,
          confidence: result.confidence,
          primaryIntent: result.primaryIntent,
        },
      ]);
    } catch (submitError) {
      setError(submitError.message || "Đã xảy ra lỗi khi gửi yêu cầu.");
      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text:
            "Mình chưa thể xử lý yêu cầu này. Bạn hãy kiểm tra backend và thử lại.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="app-layout">
      <main className="chat-container">
        <header className="chat-header">
          <div>
            <h1>Job Search AI</h1>
            <p>Trợ lý nghề nghiệp AI</p>
          </div>

          <button
            type="button"
            className="secondary-button"
            onClick={resetConversation}
          >
            Chat mới
          </button>
        </header>

        <section
          className="chat-messages"
          ref={messageListRef}
          aria-live="polite"
        >
          {messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}

          {messages.length === 1 && (
            <section className="suggestion-list">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.title}
                  type="button"
                  className="suggestion-button"
                  onClick={() => setDraft(suggestion.message)}
                >
                  {suggestion.title}
                </button>
              ))}
            </section>
          )}

          {isSending && <TypingIndicator />}
        </section>

        <section className="chat-composer-container">
          {error && (
            <div className="error-message" role="alert">
              {error}
            </div>
          )}

          {selectedCvFile && (
            <div className="selected-file">
              <span>PDF</span>
              <div>
                <strong>{selectedCvFile.name}</strong>
                <small>{getCvUploadStatusText(cvUploadStatus, cvUploadResult)}</small>
              </div>
              <button type="button" aria-label="Xóa CV" onClick={removeCv}>
                ×
              </button>
            </div>
          )}

          <form className="chat-form" onSubmit={handleSubmit}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              hidden
              onChange={handleCvSelection}
            />

            <button
              type="button"
              className="attach-button"
              aria-label="Đính kèm CV"
              title="Đính kèm CV"
              disabled={isSending || isUploadingCv}
              onClick={openCvPicker}
            >
              +
            </button>

            <textarea
              rows="1"
              maxLength="2000"
              placeholder="Hỏi về CV, công việc hoặc định hướng nghề nghiệp..."
              aria-label="Nội dung tin nhắn"
              value={draft}
              disabled={isSending}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />

            <button
              type="submit"
              className="send-button"
              disabled={!draft.trim() || isSending || isUploadingCv}
              aria-label="Gửi tin nhắn"
            >
              ➤
            </button>
          </form>

          <p className="ai-warning">
            CareerPilot có thể mắc lỗi. Hãy kiểm tra lại những thông tin quan trọng.
          </p>
        </section>
      </main>
    </div>
  );
}

function Message({ message }) {
  if (message.role === "user") {
    return (
      <article className="message user-message">
        <div className="message-bubble">
          <p>{message.text}</p>
        </div>
      </article>
    );
  }

  return (
      <article className="message assistant-message">
        <div className="assistant-avatar">AI</div>
        <div className="message-wrapper">
          <div className="message-bubble">
            <p>{message.text}</p>
          </div>
      </div>
    </article>
  );
}

function TypingIndicator() {
  return (
    <article className="message assistant-message">
      <div className="assistant-avatar">AI</div>
      <div className="typing-indicator" aria-label="CareerPilot đang trả lời">
        <span />
        <span />
        <span />
      </div>
    </article>
  );
}

function validateCvFile(file) {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

  if (!isPdf) {
    return "CV phải là tệp PDF.";
  }

  if (file.size > MAX_FILE_SIZE) {
    return `Dung lượng CV không được vượt quá ${MAX_FILE_SIZE / 1024 / 1024} MB.`;
  }

  return null;
}

function getCvUploadStatusText(status, result) {
  if (status === "uploading") {
    return "Đang tải lên và xử lý...";
  }

  if (status === "uploaded") {
    return result?.file_id
      ? `Đã tải lên và xử lý xong (${result.file_id})`
      : "Đã tải lên và xử lý xong";
  }

  if (status === "failed") {
    return "Tải lên thất bại";
  }

  return "Đã chọn, chờ tải lên";
}
