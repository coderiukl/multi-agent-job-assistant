import { getSalaryPeriodLabel } from "./labels.js";

export function formatScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "0%";
  }

  const normalized = Math.max(
    0,
    Math.min(1, number),
  );

  return `${Math.round(normalized * 100)}%`;
}

export function clampMatchingScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return 0;
  }

  return Math.max(0, Math.min(100, number));
}

export function formatSalary(job) {
  const minimum = toFiniteNumber(job.salary_min);
  const maximum = toFiniteNumber(job.salary_max);

  if (minimum === null && maximum === null) {
    return "";
  }

  const currency = job.salary_currency ?? "";
  const period = getSalaryPeriodLabel(
    job.salary_period,
  );

  if (minimum !== null && maximum !== null) {
    return (
      `${formatMoney(minimum)} – ` +
      `${formatMoney(maximum)} ${currency}${period}`
    );
  }

  if (minimum !== null) {
    return (
      `Từ ${formatMoney(minimum)} ` +
      `${currency}${period}`
    );
  }

  return (
    `Đến ${formatMoney(maximum)} ` +
    `${currency}${period}`
  );
}

export function formatMoney(value) {
  return new Intl.NumberFormat("vi-VN", {
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(value) {
  if (!value) {
    return "Không xác định";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Không xác định";
  }

  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function toFiniteNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  const number = Number(value);

  return Number.isFinite(number)
    ? number
    : null;
}