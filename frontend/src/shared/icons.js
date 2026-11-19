/**
 * Inline reference to a symbol in the icon sprite declared in index.html.
 * Icons are decorative; pair them with visible text or an aria-label.
 */
export function icon(name, className = "") {
  const classes = ["icon", className].filter(Boolean).join(" ");

  return `<svg class="${classes}" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
}

export function createIcon(name, className = "") {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  const use = document.createElementNS(namespace, "use");

  svg.setAttribute("class", ["icon", className].filter(Boolean).join(" "));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);

  return svg;
}

export function createBrandMark(className = "") {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  const use = document.createElementNS(namespace, "use");

  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  use.setAttribute("href", "#brand-mark");
  svg.append(use);

  return svg;
}
