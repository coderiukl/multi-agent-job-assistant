export function appendMessage(messageList, {role, text, context = null}) {
    const article = document.createElement("article");

    article.className = `message ${role}-message`;

    if (role === "assistant") {
        const avatar = document.createElement("div");

        avatar.className = "assistant-avatar";
        avatar.textContent = "AI";

        article.append(avatar);
    }

    const bubble = document.createElement("div");

    bubble.className = "message-bubble";

    const paragraph = document.createElement("p");

    paragraph.textContent = text;

    bubble.append(paragraph);

    if (context?.cvId || context?.cvName) {
        const cvAttachment = document.createElement("div");

        cvAttachment.className = "message-attachment";
        cvAttachment.textContent = `CV: ${context.cvName || "CV đã đính kèm"}`;
        bubble.append(cvAttachment);
    }

    if (context?.jobDescription) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        const description = document.createElement("p");

        details.className = "message-job-description";
        summary.textContent = "JD đã đính kèm";
        description.textContent = context.jobDescription;

        details.append(summary, description);
        bubble.append(details);
    }

    article.append(bubble);
    messageList.append(article);
}

export function showTypingIndicator(messageList) {
    if (messageList.querySelector(`#typing-indicator`)) {
        return;
    }

    const article = document.createElement("article");

    article.id = "typing-indicator";
    article.className = "message assistant-message";
    article.innerHTML = `
    <div class="assistant-avatar">AI</div>
    <div class="typing-indicator" aria-label="Job Search AI đang xử lý">
        <span></span>
        <span></span>
        <span></span>
    </div>
    `;

    messageList.append(article);
}

export function removeTypingIndicator(messageList) {
    messageList.querySelector("#typing-indicator")?.remove();
}

export function scrollMessagesToBottom(messageList) {
    messageList.scrollTo({
        top: messageList.scrollHeight,
        behavior: "smooth",
    });
}
