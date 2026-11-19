import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import { getScoreTone } from "./score-tones.js";

/**
 * Shared HTML builders for result views (matching, CV analysis, advice).
 * All values are escaped; scores are shown exactly as returned (0–100).
 */

export function renderScoreOverview({
  score,
  scoreLabel,
  badgeLabel,
  badgeTone,
  title,
  summary,
  confidence,
}) {
  const value = clampMatchingScore(score);
  const display = Number.isInteger(value) ? String(value) : value.toFixed(1);

  return `
    <header class="insight-overview">
      <div class="score-block">
        <div class="score-display">
          <span class="score-value">${display}</span>
          <span class="score-max">/100</span>
        </div>
        <div
          class="score-meter ${getScoreTone(value)}"
          role="meter"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow="${value}"
          aria-label="${escapeHtml(scoreLabel)}: ${display} trên 100"
        >
          <span style="--value: ${value}"></span>
        </div>
        <div class="score-scale" aria-hidden="true"><span>0</span><span>50</span><span>100</span></div>
      </div>

      <div class="insight-summary">
        <span class="badge ${escapeHtml(badgeTone)}">${escapeHtml(badgeLabel)}</span>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(summary || "Chưa có nhận xét tổng quan.")}</p>
        ${renderConfidence(confidence)}
      </div>
    </header>
  `;
}

export function renderConfidence(confidence) {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) {
    return "";
  }

  return `
    <p class="insight-confidence">
      Độ tin cậy của đánh giá: ${Math.round(confidence * 100)}%
    </p>
  `;
}

export function renderBreakdownItem(label, value) {
  const score = clampMatchingScore(value);

  return `
    <div class="breakdown-item">
      <span>${escapeHtml(label)}</span>
      <div class="score-track ${getScoreTone(score)}" aria-hidden="true">
        <span style="width: ${score}%"></span>
      </div>
      <strong aria-label="${escapeHtml(label)}: ${score.toFixed(0)} trên 100">${score.toFixed(0)}</strong>
    </div>
  `;
}

export function renderBreakdownSection(title, items) {
  return `
    <section class="insight-section">
      <div class="insight-section-header">
        <h3>${escapeHtml(title)}</h3>
        <p>Thang điểm 0–100</p>
      </div>
      <div class="breakdown-list">
        ${items.map(([label, value]) => renderBreakdownItem(label, value)).join("")}
      </div>
    </section>
  `;
}

/**
 * @param items  array of strings, or objects rendered by `renderItem`
 * @param variant "is-strength" | "is-gap"
 */
export function renderFindingSection({
  title,
  items,
  variant,
  emptyMessage,
  renderItem = (item) => `<span>${escapeHtml(item)}</span>`,
}) {
  const marker = variant === "is-strength" ? icon("check") : icon("minus");

  return `
    <section class="insight-section">
      <div class="insight-section-header">
        <h3>${escapeHtml(title)}</h3>
        ${items.length ? `<p>${items.length} mục</p>` : ""}
      </div>
      ${
        items.length
          ? `<ul class="finding-list ${variant}">
              ${items
                .map(
                  (item) => `
                    <li>
                      <span class="finding-marker">${marker}</span>
                      ${renderItem(item)}
                    </li>
                  `,
                )
                .join("")}
            </ul>`
          : `<p class="insight-empty">${escapeHtml(emptyMessage)}</p>`
      }
    </section>
  `;
}
