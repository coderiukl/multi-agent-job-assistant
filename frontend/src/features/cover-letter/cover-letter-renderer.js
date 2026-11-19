import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { escapeHtml } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import { showToast } from "../../shared/toast.js";

export function createCoverLetterRenderer({
  openResultsPanel,
  showError,
  updateMobileResultsBadge,
}) {
  function renderCoverLetterResult(result) {
    state.currentCoverLetterResult = result;
    state.currentMatchingResult = null;
    state.currentCvAnalysisResult = null;
    state.currentCareerAdviceResult = null;

    elements.resultsEyebrow.textContent = "COVER LETTER";
    elements.resultsTitle.textContent = "Thư ứng tuyển";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    if (elements.jobPagination) elements.jobPagination.hidden = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    const confidence =
      typeof result.confidence === "number"
        ? `${Math.round(result.confidence * 100)}%`
        : null;

    elements.jobResults.innerHTML = `
      <section class="cover-letter-result" aria-label="Thư ứng tuyển">
        <header class="cover-letter-header">
          <div class="cover-letter-tags">
            <span class="badge">${escapeHtml(getLanguageLabel(result.language))}</span>
            <span class="badge">${escapeHtml(getToneLabel(result.tone))}</span>
            <span class="badge ${result.isPersonalized ? "badge-accent" : ""}">
              ${result.isPersonalized ? "Cá nhân hóa theo CV" : "Bản tổng quát"}
            </span>
          </div>

          <button type="button" class="btn btn-primary btn-sm" data-action="copy-cover-letter">
            ${icon("copy")} <span>Sao chép thư</span>
          </button>
        </header>

        <article class="cover-letter-paper" aria-label="Nội dung thư">
          ${
            result.subject
              ? `<p class="cover-letter-subject">Tiêu đề: <strong>${escapeHtml(result.subject)}</strong></p>`
              : ""
          }
          <pre class="cover-letter-text">${escapeHtml(result.fullText)}</pre>
        </article>

        <div class="cover-letter-meta">
          ${Number.isFinite(Number(result.wordCount)) ? `<span>${escapeHtml(result.wordCount)} từ</span>` : ""}
          ${confidence ? `<span>Độ tin cậy: ${escapeHtml(confidence)}</span>` : ""}
        </div>

        <div class="cover-letter-evidence-grid">
          ${renderEvidence("Bằng chứng từ CV đã sử dụng", result.cvEvidenceUsed)}
          ${renderEvidence("Yêu cầu công việc đã đề cập", result.jobRequirementsAddressed)}
        </div>
      </section>
    `;
    elements.jobResults.scrollTop = 0;

    updateMobileResultsBadge(1);
    openResultsPanel();
  }

  async function copyCoverLetter(button) {
    const fullText = state.currentCoverLetterResult?.fullText;

    if (!fullText) {
      showError("Không có nội dung thư để sao chép.");
      return;
    }

    try {
      await navigator.clipboard.writeText(fullText);

      const label = button.querySelector("span");
      const originalText = label?.textContent;

      if (label) label.textContent = "Đã sao chép";
      showToast("Đã sao chép thư ứng tuyển vào clipboard");

      setTimeout(() => {
        if (label) label.textContent = originalText;
      }, 1800);
    } catch {
      showError(
        "Trình duyệt không cho phép sao chép tự động. Hãy chọn nội dung thư và sao chép thủ công.",
      );
    }
  }

  return {
    copyCoverLetter,
    renderCoverLetterResult,
  };
}

function renderEvidence(title, items) {
  const evidenceItems = Array.isArray(items) ? items : [];

  return `
    <section class="cover-letter-evidence">
      <h3>${escapeHtml(title)}</h3>
      ${
        evidenceItems.length
          ? `<ul>
              ${evidenceItems
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}
            </ul>`
          : "<p>Chưa có dữ liệu.</p>"
      }
    </section>
  `;
}

function getLanguageLabel(language) {
  return language === "en" ? "English" : "Tiếng Việt";
}

function getToneLabel(tone) {
  const labels = {
    professional: "Chuyên nghiệp",
    confident: "Tự tin",
    enthusiastic: "Nhiệt huyết",
  };

  return labels[tone] ?? "Chuyên nghiệp";
}
