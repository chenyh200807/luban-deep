import test from "node:test";
import assert from "node:assert/strict";
import {
  parseSafeChartConfig,
  sanitizeSvgMarkup,
} from "../lib/visualize-safe-renderer.ts";

test("parseSafeChartConfig accepts strict JSON Chart.js config", () => {
  const result = parseSafeChartConfig(JSON.stringify({
    type: "bar",
    data: {
      labels: ["A", "B"],
      datasets: [{ label: "Score", data: [1, 2] }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true },
      },
    },
  }));

  assert.equal(result.error, null);
  assert.equal(result.config?.type, "bar");
});

test("parseSafeChartConfig rejects malicious Chart.js IIFE without executing it", () => {
  globalThis.__visualizePwned = false;

  const result = parseSafeChartConfig(`(() => {
    globalThis.__visualizePwned = true;
    return {
      type: "bar",
      data: { labels: ["A"], datasets: [{ data: [1] }] },
      options: {}
    };
  })()`);

  assert.match(result.error ?? "", /strict JSON/);
  assert.equal(globalThis.__visualizePwned, false);
});

test("parseSafeChartConfig rejects executable Chart.js option slots", () => {
  const result = parseSafeChartConfig(JSON.stringify({
    type: "line",
    data: { labels: ["A"], datasets: [{ data: [1] }] },
    options: {
      onClick: "alert(1)",
      plugins: {
        tooltip: {
          callbacks: {
            label: "alert(1)",
          },
        },
      },
    },
  }));

  assert.match(result.error ?? "", /Executable Chart\.js option/);
});

test("sanitizeSvgMarkup removes script, foreignObject, event handlers, and dangerous hrefs", () => {
  const result = sanitizeSvgMarkup(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" onload="alert(1)">
      <script>alert(1)</script>
      <foreignObject width="10" height="10"><body>unsafe</body></foreignObject>
      <a href="javascript:alert(1)"><text>bad</text></a>
      <image href="data:image/svg+xml;base64,PHN2Zy8+" />
      <rect width="20" height="20" fill="url(javascript:alert(1))" />
      <text x="10" y="20">safe</text>
    </svg>
  `);

  assert.equal(result.error, null);
  assert.doesNotMatch(result.sanitizedSvg, /onload/i);
  assert.doesNotMatch(result.sanitizedSvg, /<\s*script/i);
  assert.doesNotMatch(result.sanitizedSvg, /foreignObject/i);
  assert.doesNotMatch(result.sanitizedSvg, /javascript:/i);
  assert.doesNotMatch(result.sanitizedSvg, /data:image/i);
  assert.match(result.sanitizedSvg, /safe/);
});

test("sanitizeSvgMarkup removes style elements with external imports", () => {
  const result = sanitizeSvgMarkup(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80">
      <style>@import url("https://example.com/unsafe.css"); text { fill: red; }</style>
      <text x="10" y="20">safe</text>
    </svg>
  `);

  assert.equal(result.error, null);
  assert.doesNotMatch(result.sanitizedSvg, /<\s*style/i);
  assert.doesNotMatch(result.sanitizedSvg, /@import/i);
  assert.match(result.sanitizedSvg, /safe/);
});

test("sanitizeSvgMarkup rejects non-SVG roots", () => {
  const result = sanitizeSvgMarkup(`<div onload="alert(1)">not svg</div>`);

  assert.equal(result.sanitizedSvg, "");
  assert.match(result.error ?? "", /root element/);
});
