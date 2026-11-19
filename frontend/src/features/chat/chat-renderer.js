import { createBrandMark, createIcon } from "../../shared/icons.js";
import {
  getExecutionStatusLabel,
  getRequiredInputLabel,
  getRouteLabel,
  getWorkflowStepLabel,
  getWorkflowTypeLabel,
} from "../../shared/labels.js";

/** Result types that have a dedicated view in the results panel. */
const ROUTES_WITH_RESULT_VIEW = new Set([
  "job_search",
  "job_matching",
  "cv_analysis",
  "career_advice",
  "cover_letter",
]);

/**
 * Keeps only what the transcript needs to show how a turn was executed.
 * Large result payloads stay in the results store, not in every message.
 */
export function summarizeTurnForMessage(conversation) {
  if (!conversation) {
    return null;
  }

  return {
    route: conversation.route ?? null,
    status: conversation.status ?? null,
    workflow: conversation.workflow ?? null,
    matchingExecution: conversation.matchingExecution ?? null,
    missingInputs: Array.isArray(conversation.missingInputs)
      ? conversation.missingInputs
      : [],
  };
}

export function appendMessage(messageList, { role, text, context = null, result = null }) {
  const article = document.createElement("article");

  article.className = `message ${role}-message`;

  const body = document.createElement("div");
  body.className = "message-body";

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.append(createBrandMark());
    article.append(avatar);

    body.append(createAssistantMeta(result));
  } else {
    article.setAttribute("aria-label", "Tin nhắn của bạn");
  }

  const textBlock = document.createElement("div");
  textBlock.className = "message-text";
  textBlock.textContent = text;
  body.append(textBlock);

  if (role === "user") {
    const attachments = createAttachments(context);

    if (attachments) {
      body.append(attachments);
    }
  }

  if (role === "assistant" && result) {
    const trace = createAgentTrace(result);

    if (trace) {
      body.append(trace);
    }

    const actions = createResultActions(result);

    if (actions) {
      body.append(actions);
    }
  }

  article.append(body);
  messageList.append(article);
}

function createAssistantMeta(result) {
  const meta = document.createElement("header");
  meta.className = "message-meta";

  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = "Job Search AI";
  meta.append(author);

  const routeLabel = getRouteLabel(result?.route);

  if (routeLabel) {
    const route = document.createElement("span");
    route.className = "message-route";
    route.textContent = routeLabel;
    meta.append(route);
  }

  return meta;
}

function createAttachments(context) {
  const hasCv = Boolean(context?.cvId || context?.cvName);
  const hasJd = Boolean(context?.jobDescription);

  if (!hasCv && !hasJd) {
    return null;
  }

  const container = document.createElement("div");
  container.className = "message-attachments";

  if (hasCv) {
    const chip = document.createElement("span");
    const label = document.createElement("span");

    chip.className = "message-attachment";
    label.textContent = context.cvName || "CV đã đính kèm";
    chip.append(createIcon("file"), label);
    container.append(chip);
  }

  if (hasJd) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const description = document.createElement("p");

    details.className = "message-job-description";
    summary.append(
      createIcon("briefcase"),
      document.createTextNode("Job Description đã đính kèm"),
      createIcon("chevron-down", "icon-chevron"),
    );
    description.textContent = context.jobDescription;

    details.append(summary, description);
    container.append(details);
  }

  return container;
}

/**
 * Renders the orchestration plan the backend actually executed for this
 * turn (workflow.steps / completed_steps), the matching execution summary
 * and any missing inputs. Nothing is rendered when the backend did not
 * report a multi-step workflow.
 */
function createAgentTrace(result) {
  const workflow = result.workflow;
  const steps = (workflow?.steps ?? []).filter((step) => step !== "completed");
  const completed = new Set(workflow?.completedSteps ?? []);
  const execution = result.matchingExecution;
  const missingInputs = result.missingInputs ?? [];
  const isWaiting = result.status === "waiting_for_human";
  // Single-agent turns are already labelled by route in the message header.
  const showSteps =
    steps.length > 1 && workflow?.workflowType !== "single_agent";

  if (!showSteps && !execution && !missingInputs.length) {
    return null;
  }

  const trace = document.createElement("section");
  trace.className = "agent-trace";
  trace.setAttribute("aria-label", "Các bước agent đã thực hiện");

  if (showSteps) {
    const header = document.createElement("div");
    header.className = "agent-trace-header";

    const title = document.createElement("span");
    title.className = "eyebrow";
    title.textContent = getWorkflowTypeLabel(workflow.workflowType) ?? "Quy trình";
    header.append(title);

    const count = document.createElement("span");
    count.className = "agent-trace-note";
    const doneCount = steps.filter((step) => completed.has(step)).length;
    count.innerHTML = `<strong>${doneCount}/${steps.length}</strong> bước hoàn tất`;
    header.append(count);

    trace.append(header);

    const list = document.createElement("ol");
    list.className = "agent-trace-steps";

    for (const step of steps) {
      const item = document.createElement("li");
      const dot = document.createElement("span");
      const isDone = completed.has(step);
      const isCurrentWaiting = isWaiting && step === workflow.currentStep;

      item.className = "agent-trace-step";
      item.classList.toggle("is-done", isDone);
      item.classList.toggle("is-waiting", !isDone && isCurrentWaiting);
      dot.className = "agent-trace-dot";

      if (isDone) {
        dot.append(createIcon("check"));
      }

      item.append(dot, document.createTextNode(getWorkflowStepLabel(step)));
      item.setAttribute(
        "aria-label",
        `${getWorkflowStepLabel(step)}: ${isDone ? "đã hoàn tất" : isCurrentWaiting ? "đang chờ bạn xác nhận" : "chưa thực hiện"}`,
      );
      list.append(item);
    }

    trace.append(list);
  }

  if (execution && execution.status !== "no_results") {
    const note = document.createElement("p");
    note.className = "agent-trace-note";
    note.innerHTML =
      `So khớp CV: <strong>${Number(execution.succeeded)}/${Number(execution.total)}</strong> công việc` +
      ` · ${escapeText(getExecutionStatusLabel(execution.status))}` +
      (execution.failed ? ` · ${Number(execution.failed)} lỗi` : "") +
      (execution.skipped ? ` · ${Number(execution.skipped)} bỏ qua` : "");
    trace.append(note);
  }

  if (missingInputs.length) {
    const missing = document.createElement("p");
    missing.className = "agent-trace-missing";
    missing.append(
      createIcon("alert", "icon-sm"),
      document.createTextNode(
        `Cần bổ sung: ${missingInputs.map(getRequiredInputLabel).join(", ")}`,
      ),
    );
    trace.append(missing);
  }

  return trace;
}

function createResultActions(result) {
  if (
    !ROUTES_WITH_RESULT_VIEW.has(result.route) ||
    result.status === "waiting_for_human" ||
    result.status === "failed"
  ) {
    return null;
  }

  const container = document.createElement("div");
  const button = document.createElement("button");

  container.className = "message-actions";
  button.type = "button";
  button.className = "link-button";
  button.dataset.openResult = result.route;
  button.append(
    document.createTextNode(`Xem kết quả ${getRouteLabel(result.route)?.toLowerCase() ?? ""}`.trim()),
    createIcon("arrow-right"),
  );
  container.append(button);

  return container;
}

function escapeText(value) {
  const span = document.createElement("span");
  span.textContent = value;
  return span.innerHTML;
}

export function showTypingIndicator(messageList) {
  if (messageList.querySelector("#typing-indicator")) {
    return;
  }

  const article = document.createElement("article");
  const avatar = document.createElement("div");
  const body = document.createElement("div");
  const indicator = document.createElement("div");
  const dots = document.createElement("span");
  const label = document.createElement("span");

  article.id = "typing-indicator";
  article.className = "message assistant-message";
  avatar.className = "message-avatar";
  avatar.append(createBrandMark());
  body.className = "message-body";
  indicator.className = "typing-indicator";
  indicator.setAttribute("role", "status");
  dots.className = "typing-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<span></span><span></span><span></span>";
  label.textContent = "Các agent đang xử lý yêu cầu…";

  indicator.append(dots, label);
  body.append(indicator);
  article.append(avatar, body);
  messageList.append(article);
}

export function removeTypingIndicator(messageList) {
  messageList.querySelector("#typing-indicator")?.remove();
}

export function scrollMessagesToBottom(messageList) {
  const scroller = messageList.closest(".conversation-scroll") ?? messageList;

  scroller.scrollTo({
    top: scroller.scrollHeight,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
  });
}
