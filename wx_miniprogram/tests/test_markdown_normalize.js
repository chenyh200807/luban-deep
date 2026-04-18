// test_markdown_normalize.js — regression tests for markdown-normalize.js
// Run: node wx_miniprogram/tests/test_markdown_normalize.js

var normalize = require("../utils/markdown-normalize").normalizeMarkdownForWechat;

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

var normalized = normalize([
  "**拿分要点**：",
  "",
  "1. **时间限制**：必须记住24小时",
  "  - 屋面一级防水→**3道**",
  "  - 屋面二级防水  →  **2道**",
  "",
  "",
  "```markdown",
  "  - keep fenced indentation",
  "```",
].join("\n"));

assert(
  normalized.indexOf("**拿分要点：**") >= 0,
  "standalone labelled paragraph should move colon into bold label",
);
assert(
  normalized.indexOf("1. **时间限制：** 必须记住24小时") >= 0,
  "ordered labelled item should move colon into bold label",
);
assert(
  normalized.indexOf("- 屋面一级防水 → **3道**") >= 0,
  "indented bullets should flatten and normalize arrow spacing",
);
assert(
  normalized.indexOf("- 屋面二级防水 → **2道**") >= 0,
  "arrow spacing should be normalized consistently",
);
assert(
  normalized.indexOf("\n\n\n") < 0,
  "blank lines should collapse to a single separator",
);
assert(
  normalized.indexOf("  - keep fenced indentation") >= 0,
  "fenced block content should remain untouched",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_markdown_normalize.js (" + pass + " assertions)");
