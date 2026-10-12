const PERSONAL_FIELDS = [
  ["full_name", "Họ và tên"],
  ["email", "Email"],
  ["phone", "Số điện thoại"],
  ["location", "Địa điểm"],
  ["linkedin_url", "LinkedIn"],
  ["github_url", "GitHub"],
  ["portfolio_url", "Website / Portfolio"],
];

const COLLECTIONS = [
  {
    key: "work_experiences",
    title: "Kinh nghiệm làm việc",
    itemLabel: "Kinh nghiệm",
    fields: [
      ["job_title", "Vị trí"],
      ["company", "Công ty"],
      ["location", "Địa điểm"],
      ["start_date", "Thời gian bắt đầu"],
      ["end_date", "Thời gian kết thúc"],
      ["is_current", "Hiện đang làm việc", "boolean"],
      ["responsibilities", "Trách nhiệm (mỗi dòng một ý)", "list"],
      ["achievements", "Thành tích (mỗi dòng một ý)", "list"],
    ],
  },
  {
    key: "educations",
    title: "Học vấn",
    itemLabel: "Học vấn",
    fields: [
      ["institution", "Trường / Cơ sở đào tạo"],
      ["degree", "Bằng cấp"],
      ["field_of_study", "Chuyên ngành"],
      ["start_date", "Thời gian bắt đầu"],
      ["end_date", "Thời gian kết thúc"],
      ["description", "Mô tả", "multiline"],
    ],
  },
  {
    key: "projects",
    title: "Dự án",
    itemLabel: "Dự án",
    fields: [
      ["name", "Tên dự án"],
      ["url", "Liên kết"],
      ["description", "Mô tả", "multiline"],
      ["technologies", "Công nghệ (mỗi dòng một mục)", "list"],
    ],
  },
  {
    key: "certifications",
    title: "Chứng chỉ",
    itemLabel: "Chứng chỉ",
    fields: [
      ["name", "Tên chứng chỉ"],
      ["issuer", "Đơn vị cấp"],
      ["issue_date", "Ngày cấp"],
      ["credential_url", "Liên kết xác thực"],
    ],
  },
  {
    key: "languages",
    title: "Ngoại ngữ",
    itemLabel: "Ngôn ngữ",
    fields: [
      ["name", "Ngôn ngữ"],
      ["proficiency", "Trình độ"],
    ],
  },
];

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function createField({ label, value, path, collection, index, key, kind }) {
  if (kind === "boolean") {
    const wrapper = createElement("label", "cv-profile-checkbox");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    wrapper.append(input, document.createTextNode(label));
    setBinding(input, { path, collection, index, key, kind });
    return wrapper;
  }

  const wrapper = createElement(
    "label",
    `cv-profile-field${kind === "list" || kind === "multiline" ? " is-wide" : ""}`,
  );
  wrapper.append(createElement("span", "", label));
  const input = kind === "list" || kind === "multiline"
    ? document.createElement("textarea")
    : document.createElement("input");
  if (input instanceof HTMLInputElement) input.type = "text";
  input.value = kind === "list"
    ? (Array.isArray(value) ? value.join("\n") : "")
    : (value ?? "");
  setBinding(input, { path, collection, index, key, kind });
  wrapper.append(input);
  return wrapper;
}

function setBinding(input, { path, collection, index, key, kind }) {
  if (path) input.dataset.cvPath = path;
  if (collection) input.dataset.cvCollection = collection;
  if (index !== undefined) input.dataset.cvIndex = String(index);
  if (key) input.dataset.cvKey = key;
  if (kind) input.dataset.cvKind = kind;
}

function createSection(title) {
  const section = createElement("section", "cv-profile-section");
  section.append(createElement("h3", "", title));
  return section;
}

export function renderCvProfileEditor(container, profile) {
  container.replaceChildren();

  const personalSection = createSection("Thông tin cá nhân");
  const personalGrid = createElement("div", "cv-profile-grid");
  const personal = profile.personal_information ?? {};
  for (const [key, label] of PERSONAL_FIELDS) {
    personalGrid.append(createField({
      label,
      value: personal[key],
      path: `personal_information.${key}`,
    }));
  }
  personalSection.append(personalGrid);
  container.append(personalSection);

  const overviewSection = createSection("Giới thiệu và kỹ năng");
  const overviewGrid = createElement("div", "cv-profile-grid");
  overviewGrid.append(
    createField({
      label: "Giới thiệu bản thân",
      value: profile.professional_summary,
      path: "professional_summary",
      kind: "multiline",
    }),
    createField({
      label: "Kỹ năng (mỗi dòng một kỹ năng)",
      value: profile.skills,
      path: "skills",
      kind: "list",
    }),
  );
  overviewSection.append(overviewGrid);
  container.append(overviewSection);

  for (const definition of COLLECTIONS) {
    const section = createSection(definition.title);
    const items = Array.isArray(profile[definition.key])
      ? profile[definition.key]
      : [];
    if (!items.length) {
      section.append(createElement("p", "cv-profile-empty", "Chưa tìm thấy thông tin trong CV."));
    }
    items.forEach((item, index) => {
      const card = createElement("div", "cv-profile-item");
      card.append(createElement(
        "p",
        "cv-profile-item-title",
        `${definition.itemLabel} ${index + 1}`,
      ));
      const grid = createElement("div", "cv-profile-grid");
      for (const [key, label, kind] of definition.fields) {
        grid.append(createField({
          label,
          value: item?.[key],
          collection: definition.key,
          index,
          key,
          kind,
        }));
      }
      card.append(grid);
      section.append(card);
    });
    container.append(section);
  }
}

function readValue(input) {
  const kind = input.dataset.cvKind;
  if (kind === "boolean") return input.checked;
  if (kind === "list") {
    return input.value
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
  }
  const value = input.value.trim();
  return value || null;
}

function setPath(target, path, value) {
  const parts = path.split(".");
  const key = parts.pop();
  let current = target;
  for (const part of parts) {
    current[part] ??= {};
    current = current[part];
  }
  current[key] = value;
}

export function readCvProfileEditor(container, originalProfile) {
  const profile = structuredClone(originalProfile);
  for (const input of container.querySelectorAll("[data-cv-path]")) {
    setPath(profile, input.dataset.cvPath, readValue(input));
  }
  for (const input of container.querySelectorAll("[data-cv-collection]")) {
    const collection = input.dataset.cvCollection;
    const index = Number(input.dataset.cvIndex);
    const key = input.dataset.cvKey;
    profile[collection][index][key] = readValue(input);
  }
  profile.languages = profile.languages.filter((language) => language.name);
  profile.needs_review = false;
  return profile;
}
