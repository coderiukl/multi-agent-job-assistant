import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { escapeHtml } from "../../shared/html.js";

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
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    const confidence =
      result.confidence === null
        ? "Chưa xác định"
        : `${Math.round(result.confidence * 100)}%`;

    elements.jobResults.innerHTML = `
      <section
        class="cover-letter-result"
        aria-label="Thư ứng tuyển"
      >
        <header class="cover-letter-header">
          <div>
            <span class="cover-letter-badge">
              ${escapeHtml(getLanguageLabel(result.language))}
            </span>

            <span class="cover-letter-badge secondary">
              ${escapeHtml(getToneLabel(result.tone))}
            </span>
          </div>

          <button
            type="button"
            class="primary-button"
            data-action="copy-cover-letter"
          >
            Sao chép thư
          </button>
        </header>

        <article class="cover-letter-paper">
          <pre>${escapeHtml(result.fullText)}</pre>
        </article>

        <div class="cover-letter-meta">
          <span>${escapeHtml(result.wordCount)} từ</span>
          <span>Độ tin cậy: ${escapeHtml(confidence)}</span>
          <span>
            ${
              result.isPersonalized
                ? "Cá nhân hóa theo CV"
                : "Bản tổng quát"
            }
          </span>
        </div>

        <div class="cover-letter-evidence-grid">
          ${renderEvidence(
            "Bằng chứng CV đã sử dụng",
            result.cvEvidenceUsed,
          )}
          ${renderEvidence(
            "Yêu cầu công việc đã đề cập",
            result.jobRequirementsAddressed,
          )}
        </div>
      </section>
    `;

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

      const originalText = button.textContent;
      button.textContent = "Đã sao chép";

      setTimeout(() => {
        button.textContent = originalText;
      }, 1800);
    } catch {
      showError(
        "Trình duyệt không cho phép sao chép tự động.",
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
          ? `
            <ul>
              ${evidenceItems
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}
            </ul>
          `
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
