import type { ChartConfiguration } from "chart.js";

export type SafeChartConfig = ChartConfiguration;

type SafeChartParseResult =
  | { config: SafeChartConfig; error: null }
  | { config: null; error: string };

type SafeSvgResult =
  | { sanitizedSvg: string; error: null }
  | { sanitizedSvg: ""; error: string };

const ALLOWED_CHART_TYPES = new Set([
  "bar",
  "line",
  "pie",
  "doughnut",
  "radar",
  "polarArea",
  "bubble",
  "scatter",
]);

const ROOT_CHART_KEYS = new Set(["type", "data", "options"]);
const BLOCKED_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);

const DANGEROUS_SVG_ELEMENTS = [
  "script",
  "foreignObject",
  "iframe",
  "object",
  "embed",
  "link",
  "meta",
  "base",
];

const DANGEROUS_ELEMENT_PATTERN = DANGEROUS_SVG_ELEMENTS.join("|");
const DANGEROUS_ELEMENT_BLOCK_RE = new RegExp(
  `<\\s*(?:[\\w-]+:)?(?:${DANGEROUS_ELEMENT_PATTERN})\\b[\\s\\S]*?<\\s*\\/\\s*(?:[\\w-]+:)?(?:${DANGEROUS_ELEMENT_PATTERN})\\s*>`,
  "gi",
);
const DANGEROUS_ELEMENT_TAG_RE = new RegExp(
  `<\\s*\\/?\\s*(?:[\\w-]+:)?(?:${DANGEROUS_ELEMENT_PATTERN})\\b[^>]*\\/?>`,
  "gi",
);
const SVG_ATTR_RE =
  /\s+([:\w.-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/g;

export function parseSafeChartConfig(configText: string): SafeChartParseResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(configText);
  } catch {
    return {
      config: null,
      error: "Chart.js config must be strict JSON.",
    };
  }

  const error = validateChartConfig(parsed);
  if (error) {
    return { config: null, error };
  }

  return { config: parsed as SafeChartConfig, error: null };
}

export function sanitizeSvgMarkup(svgText: string): SafeSvgResult {
  const trimmed = svgText.trim();
  if (!/^<svg(?:\s|>)/i.test(trimmed)) {
    return {
      sanitizedSvg: "",
      error: "Invalid SVG: root element must be <svg>.",
    };
  }

  const browserSanitized = sanitizeSvgWithDomParser(trimmed);
  if (browserSanitized) {
    return browserSanitized;
  }

  return sanitizeSvgString(trimmed);
}

function validateChartConfig(value: unknown): string | null {
  if (!isPlainObject(value)) {
    return "Chart.js config must be a JSON object.";
  }

  for (const key of Object.keys(value)) {
    if (!ROOT_CHART_KEYS.has(key)) {
      return `Unsupported Chart.js config key: ${key}`;
    }
  }

  if (typeof value.type !== "string" || !ALLOWED_CHART_TYPES.has(value.type)) {
    return "Chart.js config type is not allowed.";
  }

  if (!isPlainObject(value.data)) {
    return "Chart.js config data must be an object.";
  }

  if (!Array.isArray(value.data.datasets)) {
    return "Chart.js config data.datasets must be an array.";
  }

  if ("labels" in value.data && !Array.isArray(value.data.labels)) {
    return "Chart.js config data.labels must be an array when present.";
  }

  if ("options" in value && value.options !== undefined && !isPlainObject(value.options)) {
    return "Chart.js config options must be an object when present.";
  }

  return validateSafeJsonShape(value, "config");
}

function validateSafeJsonShape(value: unknown, path: string): string | null {
  if (value === null) return null;

  const valueType = typeof value;
  if (valueType === "string" || valueType === "number" || valueType === "boolean") {
    return null;
  }
  if (valueType !== "object") {
    return `Unsupported executable or non-JSON value at ${path}.`;
  }

  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) {
      const childError = validateSafeJsonShape(value[i], `${path}[${i}]`);
      if (childError) return childError;
    }
    return null;
  }

  if (!isPlainObject(value)) {
    return `Unsupported object shape at ${path}.`;
  }

  for (const [key, child] of Object.entries(value)) {
    const normalizedKey = key.toLowerCase();
    if (BLOCKED_OBJECT_KEYS.has(key)) {
      return `Unsafe object key at ${path}.${key}.`;
    }
    if (normalizedKey.includes("callback") || /^on[A-Z]/.test(key)) {
      return `Executable Chart.js option is not allowed at ${path}.${key}.`;
    }
    const childError = validateSafeJsonShape(child, `${path}.${key}`);
    if (childError) return childError;
  }

  return null;
}

function sanitizeSvgWithDomParser(svgText: string): SafeSvgResult | null {
  if (typeof DOMParser === "undefined" || typeof XMLSerializer === "undefined") {
    return null;
  }

  const document = new DOMParser().parseFromString(svgText, "image/svg+xml");
  if (document.querySelector("parsererror")) {
    return {
      sanitizedSvg: "",
      error: "Invalid SVG: XML parsing failed.",
    };
  }

  const root = document.documentElement;
  if (!root || root.tagName.toLowerCase() !== "svg") {
    return {
      sanitizedSvg: "",
      error: "Invalid SVG: root element must be <svg>.",
    };
  }

  sanitizeSvgElement(root);

  const sanitizedSvg = new XMLSerializer().serializeToString(root);
  return { sanitizedSvg, error: null };
}

function sanitizeSvgElement(element: Element): void {
  for (const child of Array.from(element.children)) {
    const tagName = child.tagName.toLowerCase();
    const localName = tagName.includes(":") ? tagName.split(":").pop() ?? tagName : tagName;
    if (DANGEROUS_SVG_ELEMENTS.some((tag) => tag.toLowerCase() === localName)) {
      child.remove();
      continue;
    }
    sanitizeSvgElement(child);
  }

  for (const attr of Array.from(element.attributes)) {
    if (isDangerousSvgAttribute(attr.name, attr.value)) {
      element.removeAttribute(attr.name);
    }
  }
}

function sanitizeSvgString(svgText: string): SafeSvgResult {
  const sanitizedSvg = svgText
    .replace(DANGEROUS_ELEMENT_BLOCK_RE, "")
    .replace(DANGEROUS_ELEMENT_TAG_RE, "")
    .replace(SVG_ATTR_RE, (fullMatch, attrName: string, _rawValue: string, doubleValue?: string, singleValue?: string, bareValue?: string) => {
      const attrValue = doubleValue ?? singleValue ?? bareValue ?? "";
      return isDangerousSvgAttribute(attrName, attrValue) ? "" : fullMatch;
    });

  if (!/^<svg(?:\s|>)/i.test(sanitizedSvg.trim())) {
    return {
      sanitizedSvg: "",
      error: "Invalid SVG: root element must be <svg>.",
    };
  }

  return { sanitizedSvg, error: null };
}

function isDangerousSvgAttribute(name: string, value: string): boolean {
  const normalizedName = name.toLowerCase();
  if (normalizedName.startsWith("on")) {
    return true;
  }

  const normalizedValue = normalizeSvgUrlValue(value);
  if (
    normalizedName === "href" ||
    normalizedName === "xlink:href" ||
    normalizedName === "src" ||
    normalizedName === "action" ||
    normalizedName === "formaction"
  ) {
    return normalizedValue.startsWith("javascript:") || normalizedValue.startsWith("data:");
  }

  return (
    normalizedValue.includes("url(javascript:") ||
    normalizedValue.includes("url(data:") ||
    normalizedValue.includes("expression(") ||
    normalizedValue.includes("@import")
  );
}

function normalizeSvgUrlValue(value: string): string {
  return decodeBasicEntities(value)
    .replace(/[\u0000-\u001f\u007f\s]+/g, "")
    .toLowerCase();
}

function decodeBasicEntities(value: string): string {
  return value
    .replace(/&colon;/gi, ":")
    .replace(/&lpar;/gi, "(")
    .replace(/&rpar;/gi, ")")
    .replace(/&#x([0-9a-f]+);?/gi, (_match, hex: string) =>
      String.fromCodePoint(Number.parseInt(hex, 16)),
    )
    .replace(/&#([0-9]+);?/g, (_match, decimal: string) =>
      String.fromCodePoint(Number.parseInt(decimal, 10)),
    );
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (Object.prototype.toString.call(value) !== "[object Object]") return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}
