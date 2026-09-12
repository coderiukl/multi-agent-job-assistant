export function appendMessage(messageList, {role, text}) {
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