import { escapeHtml } from "../../shared/html.js";

const DESCRIPTION_HEADINGS = {
  "about us": "Giới thiệu công ty",
  "about the company": "Giới thiệu công ty",
  "about the role": "Tổng quan vai trò",
  "the role": "Tổng quan vai trò",
  "job description": "Mô tả công việc",
  "what you will do": "Công việc sẽ làm",
  "your responsibilities": "Trách nhiệm chính",
  responsibilities: "Trách nhiệm chính",
  requirements: "Yêu cầu công việc",
  qualifications: "Yêu cầu công việc",
  "your profile": "Yêu cầu ứng viên",
  "what you bring": "Yêu cầu ứng viên",
  "must have": "Yêu cầu bắt buộc",
  "nice to have": "Điểm cộng",
  "preferred qualifications": "Điểm cộng",
  "tech stack": "Công nghệ sử dụng",
  skills: "Kỹ năng yêu cầu",
  benefits: "Quyền lợi",
  "what we offer": "Quyền lợi",
  "we offer": "Quyền lợi",
  perks: "Quyền lợi",
  "why us?": "Vì sao nên ứng tuyển?",
  "why us": "Vì sao nên ứng tuyển?",
  "why join us?": "Vì sao nên ứng tuyển?",
  "why join us": "Vì sao nên ứng tuyển?",
  "mô tả công việc": "Mô tả công việc",
  "trách nhiệm": "Trách nhiệm chính",
  "yêu cầu": "Yêu cầu công việc",
  "yêu cầu công việc": "Yêu cầu công việc",
  "yêu cầu ứng viên": "Yêu cầu ứng viên",
  "quyền lợi": "Quyền lợi",
  "phúc lợi": "Quyền lợi",
};

export function renderJobDescription(description) {
  const sections = parseJobDescriptionSections(description);

  if (!sections.length) {
    return `
      <p class="job-description-empty">
        Công việc chưa có mô tả chi tiết.
      </p>
    `;
  }

  return `
    <div class="job-description">
      ${sections
        .map(
          (section) => `
            <section class="jd-block">
              <h4>${escapeHtml(section.title)}</h4>
              <ul class="jd-list">
                ${section.items
                  .map((item) => `<li>${escapeHtml(item)}</li>`)
                  .join("")}
              </ul>
            </section>
          `,
        )
        .join("")}
    </div>
  `;
}

export function parseJobDescriptionSections(description) {
  const lines = String(description ?? "")
    .split(/\r?\n/)
    .map(normalizeDescriptionLine)
    .filter(Boolean);

  if (!lines.length) {
    return [];
  }

  const sections = [];
  let currentSection = createDescriptionSection("Thông tin công việc");

  for (const line of lines) {
    const heading = normalizeDescriptionHeading(line);

    if (heading) {
      if (currentSection.items.length) {
        sections.push(currentSection);
      }

      currentSection = createDescriptionSection(heading);
      continue;
    }

    currentSection.items.push(line);
  }

  if (currentSection.items.length) {
    sections.push(currentSection);
  }

  return sections;
}

function createDescriptionSection(title) {
  return { title, items: [] };
}

function normalizeDescriptionLine(line) {
  return String(line ?? "")
    .replace(/^[\s•*+-]+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .trim();
}

function normalizeDescriptionHeading(line) {
  const text = line.replace(/:$/, "").trim();
  const key = text.toLowerCase();

  if (DESCRIPTION_HEADINGS[key]) {
    return DESCRIPTION_HEADINGS[key];
  }

  if (
    line.endsWith(":") &&
    text.length <= 80 &&
    text.split(/\s+/).length <= 10
  ) {
    return text;
  }

  return null;
}
