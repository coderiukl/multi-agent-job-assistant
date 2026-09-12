const STRATEGY_LABELS = {
  hybrid: "Tìm kiếm kết hợp PostgreSQL và Qdrant",
  semantic: "Tìm kiếm ngữ nghĩa bằng Qdrant",
  postgres: "Tìm kiếm bằng PostgreSQL",
};

const CV_QUALITY_LABELS = {
  excellent: "Rất tốt",
  good: "Tốt",
  needs_improvement: "Cần cải thiện",
  weak: "Còn yếu",
};

const RECOMMENDATION_LABELS = {
  strong_match: "Rất phù hợp",
  good_match: "Phù hợp",
  partial_match: "Phù hợp một phần",
  low_match: "Mức độ phù hợp thấp",
};

const CV_QUALITY_BADGE_CLASSES = {
  excellent: "strong_match",
  good: "good_match",
  needs_improvement: "partial_match",
  weak: "low_match",
};

const IMPROVEMENT_PRIORITY_LABELS = {
  high: "Ưu tiên cao",
  medium: "Ưu tiên vừa",
  low: "Ưu tiên thấp",
};

const CV_SECTION_LABELS = {
  personal_information: "Thông tin cá nhân",
  professional_summary: "Giới thiệu",
  skills: "Kỹ năng",
  work_experience: "Kinh nghiệm",
  education: "Học vấn",
  projects: "Dự án",
  certifications: "Chứng chỉ",
  languages: "Ngoại ngữ",
  general: "Tổng thể",
};

const EVIDENCE_STATUS_LABELS = {
  matched: "Đáp ứng",
  partial: "Một phần",
  missing: "Còn thiếu",
  not_applicable: "Không áp dụng",
};

const SENIORITY_LABELS = {
  intern: "Thực tập",
  fresher: "Fresher",
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  manager: "Quản lý",
  director: "Giám đốc",
  unknown: "Không xác định",
};

const WORK_MODE_LABELS = {
  onsite: "Tại văn phòng",
  remote: "Từ xa",
  hybrid: "Kết hợp",
  unknown: "Không xác định",
};

const EMPLOYMENT_TYPE_LABELS = {
  full_time: "Toàn thời gian",
  part_time: "Bán thời gian",
  contract: "Hợp đồng",
  internship: "Thực tập",
  freelance: "Freelance",
  temporary: "Tạm thời",
  other: "Khác",
};

const SALARY_PERIOD_LABELS = {
  hourly: "/giờ",
  weekly: "/tuần",
  fortnightly: "/2 tuần",
  monthly: "/tháng",
  annual: "/năm",
};

export function getStrategyLabel(value) {
  return STRATEGY_LABELS[value] ??
    "Tìm kiếm công việc";
}

export function getCvQualityLabel(value) {
  return CV_QUALITY_LABELS[value] ??
    "Chưa xác định";
}

export function getRecommendationLabel(value) {
  return RECOMMENDATION_LABELS[value] ??
    "Chưa xác định";
}

export function getSalaryPeriodLabel(value) {
  return SALARY_PERIOD_LABELS[value] ?? "";
}

export function getCvQualityBadgeClass(value) {
  return CV_QUALITY_BADGE_CLASSES[value] ?? "partial_match";
}

export function getImprovementPriorityLabel(value) {
  return IMPROVEMENT_PRIORITY_LABELS[value] ?? "Ưu tiên vừa";
}

export function getCvSectionLabel(value) {
  return CV_SECTION_LABELS[value] ?? "Tổng thể";
}

export function getEvidenceStatusLabel(value) {
  return EVIDENCE_STATUS_LABELS[value] ?? "Chưa xác định";
}

export function getSeniorityLabel(value) {
  return SENIORITY_LABELS[value] ?? "Không xác định";
}

export function getWorkModeLabel(value) {
  return WORK_MODE_LABELS[value] ?? "Không xác định";
}

export function getEmploymentTypeLabel(value) {
  return EMPLOYMENT_TYPE_LABELS[value] ?? "Không xác định";
}
