import test from "node:test";
import assert from "node:assert/strict";

import { validateCvFiles } from "../src/features/cv/cv-validator.js";

function image(name, size = 1024) {
  return { name, size, type: "image/png" };
}

test("accepts up to five CV images", () => {
  const files = Array.from(
    { length: 5 },
    (_, index) => image(`page-${index + 1}.png`),
  );

  assert.equal(validateCvFiles(files), null);
});

test("rejects more than five CV images", () => {
  const files = Array.from(
    { length: 6 },
    (_, index) => image(`page-${index + 1}.png`),
  );

  assert.match(validateCvFiles(files), /tối đa 5 ảnh/);
});

test("rejects PDF mixed with images", () => {
  const files = [
    { name: "resume.pdf", size: 1024, type: "application/pdf" },
    image("page-2.png"),
  ];

  assert.match(validateCvFiles(files), /không trộn lẫn/);
});
