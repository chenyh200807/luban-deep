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

var compactNormalized = normalize([
  "3.地基与基础工程",
  "-基坑支护、降水方法",
  "4.主体结构工程",
].join("\n"));

assert(
  compactNormalized.indexOf("3. 地基与基础工程") >= 0,
  "compact ordered markers should gain a stable marker space",
);
assert(
  compactNormalized.indexOf("- 基坑支护、降水方法") >= 0,
  "compact dash bullets should gain a stable marker space",
);

var compactHeadingNormalized = normalize(
  "---#一建建筑实务高频考点梳理##一、技术篇###1.结构设计与荷载\n-极限状态设计\n###3.地基与基础工程\n-基坑支护",
);

assert(
  compactHeadingNormalized.indexOf("---\n# 一建建筑实务高频考点梳理\n## 一、技术篇\n### 1. 结构设计与荷载") >= 0,
  "adjacent compact headings should split into stable heading blocks",
);
assert(
  compactHeadingNormalized.indexOf("### 3. 地基与基础工程") >= 0,
  "compact numbered headings should keep their visible section number",
);
assert(
  compactHeadingNormalized.indexOf("- 极限状态设计") >= 0 &&
    compactHeadingNormalized.indexOf("- 基坑支护") >= 0,
  "compact bullets after compact headings should remain bullet blocks",
);

var adjacentOrderedNormalized = normalize(
  "专业融合题 -- 拉分关键1.技术+进度：给定工序时间，判定工期是否满足合同要求。3.技术+安全：描述现场工况，判定危险源等级。4.技术+合同：某工序返工，判定索赔是否成立。",
);

assert(
  adjacentOrderedNormalized.indexOf("专业融合题 -- 拉分关键\n1. 技术+进度") >= 0,
  "ordered marker stuck to prose should split into a list item",
);
assert(
  adjacentOrderedNormalized.indexOf("\n3. 技术+安全") >= 0 &&
    adjacentOrderedNormalized.indexOf("\n4. 技术+合同") >= 0,
  "later adjacent ordered markers should also split and keep source indexes",
);

var adjacentAltOrderedNormalized = normalize(
  "拉分关键1）技术+进度：先画网络图。2、技术+质量：写验收程序。（3）技术+安全：补充安全措施。",
);

assert(
  adjacentAltOrderedNormalized.indexOf("拉分关键\n1. 技术+进度") >= 0 &&
    adjacentAltOrderedNormalized.indexOf("\n2. 技术+质量") >= 0 &&
    adjacentAltOrderedNormalized.indexOf("\n3. 技术+安全") >= 0,
  "Chinese ordered markers should normalize into the same ordered-list authority",
);
assert(
  normalize("按（1）条处理，不要误拆正文。").indexOf("\n1. 条处理") < 0,
  "inline legal/article references should not be mistaken for list markers",
);
assert(
  normalize("按第1.条处理，不要误拆正文。").indexOf("\n1. 条处理") < 0,
  "inline dotted article references should not be mistaken for list markers",
);
assert(
  normalize("施工按第1.条处理，质量按第2.条处理。").indexOf("\n1. 条处理") < 0 &&
    normalize("施工按第1.条处理，质量按第2.条处理。").indexOf("\n2. 条处理") < 0,
  "multiple dotted article references in prose should not become ordered lists",
);
assert(
  normalize("本文包括（1）施工部署和（2）质量验收。").indexOf("\n1. 施工部署") < 0,
  "inline parenthesized prose enumeration should not become an ordered list without a list boundary",
);
assert(
  normalize("这很关键1.条处理，不要误拆。").indexOf("\n1. 条处理") < 0,
  "generic prose ending with key words should not become an ordered list",
);

var adjacentBulletNormalized = normalize(
  "易错点：- 先写判断；- 再写依据；- 最后写措施",
);

assert(
  adjacentBulletNormalized.indexOf("易错点：\n- 先写判断；\n- 再写依据；\n- 最后写措施") >= 0,
  "punctuation-separated inline bullets should split into stable bullet items",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_markdown_normalize.js (" + pass + " assertions)");
