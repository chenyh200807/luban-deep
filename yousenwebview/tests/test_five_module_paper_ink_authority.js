// Run: node yousenwebview/tests/test_five_module_paper_ink_authority.js
// 五模块页面的 palette 只能由 styles/paper-ink.wxss 提供；页面文件只保留布局/语义状态。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var root = path.join(__dirname, "../packageDeeptutor");
var styleAuthority = fs.readFileSync(path.join(root, "styles/paper-ink.wxss"), "utf8");
var legacyBluePattern = /#(?:1d4ed8|2563eb|3b82f6|60a5fa|67e8f9|77b7ff|818cf8|93c5fd|a5f3fc)|rgba\((?:37,\s*99,\s*235|59,\s*130,\s*246|96,\s*165,\s*250|103,\s*232,\s*249)/i;
var surfaces = [
  "pages/learn/learn",
  "pages/chat/chat",
  "pages/report/report",
  "pages/profile/profile",
  "pages/history/history",
  "pages/mistake-book/mistake-book",
  "pages/attempt-detail/attempt-detail",
  "pages/practice/practice",
  "pages/assessment/assessment",
  "pages/billing/billing",
  "pages/feedback/feedback",
  "pages/legal/terms",
  "pages/first-run/first-run",
  "pages/luban/stations/stations",
  "pages/luban/teaching-points/teaching-points",
  "pages/luban/review/review",
  "pages/luban/station/station",
  "pages/luban/handoff/handoff",
  "pages/luban/retest/retest",
  "pages/luban/concept-cards/concept-cards",
  "pages/luban/errorbank/errorbank",
  "pages/luban/gauntlet/gauntlet",
  "pages/luban/seethrough/seethrough",
];

assert.ok(styleAuthority.indexOf("--pk-paper:") >= 0, "paper-ink must own the paper palette");
assert.ok(styleAuthority.indexOf("--bg-primary: var(--pk-paper)") >= 0, "legacy theme tokens must resolve through paper-ink");
assert.ok(styleAuthority.indexOf("--text-primary: var(--pk-t1)") >= 0, "legacy text tokens must resolve through paper-ink");

function cssBlock(source, selector) {
  var start = source.indexOf(selector + " {");
  assert.ok(start >= 0, selector + " must exist");
  var end = source.indexOf("}", start);
  assert.ok(end > start, selector + " must have a closing brace");
  return source.slice(start, end + 1);
}

function assertNoLegacyBlue(source, selectors, surface) {
  selectors.forEach(function (selector) {
    assert.ok(!legacyBluePattern.test(cssBlock(source, selector)), surface + " " + selector + " must use paper semantic tokens");
  });
}

function relativeLuminance(hex) {
  return hex.slice(1).match(/../g).map(function (part) {
    var value = parseInt(part, 16) / 255;
    return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
  }).reduce(function (sum, value, index) {
    return sum + value * [0.2126, 0.7152, 0.0722][index];
  }, 0);
}

function contrastRatio(foreground, background) {
  var foregroundLuminance = relativeLuminance(foreground);
  var backgroundLuminance = relativeLuminance(background);
  return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
    (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
}

function lightThemeVariable(name) {
  var lightTheme = cssBlock(styleAuthority, ".paper.light");
  var match = lightTheme.match(new RegExp(name + ":\\s*(#[0-9a-f]{6})", "i"));
  assert.ok(match, name + " must be a six-digit color in the light theme");
  return match[1];
}

var lightPaper = lightThemeVariable("--pk-paper");
assert.ok(contrastRatio(lightThemeVariable("--pk-t3"), lightPaper) >= 4.5, "light weak text must meet WCAG AA contrast");
assert.ok(contrastRatio(lightThemeVariable("--pk-grn"), lightPaper) >= 4.5, "light green text must meet WCAG AA contrast");
assert.ok(contrastRatio(lightThemeVariable("--pk-warn"), lightPaper) >= 4.5, "light warning text must meet WCAG AA contrast");

surfaces.forEach(function (surface) {
  var wxml = fs.readFileSync(path.join(root, surface + ".wxml"), "utf8");
  var wxss = fs.readFileSync(path.join(root, surface + ".wxss"), "utf8");
  assert.ok(/class="[^"]*\bpaper\b/.test(wxml), surface + " must mount the paper theme on its page root");
  assert.ok(wxss.indexOf('/packageDeeptutor/styles/paper-ink.wxss') >= 0, surface + " must import the shared palette authority");
  assert.strictEqual((wxss.match(/{/g) || []).length, (wxss.match(/}/g) || []).length, surface + " wxss braces must balance");
});

var profileStyle = fs.readFileSync(path.join(root, "pages/profile/profile.wxss"), "utf8");
assert.ok(profileStyle.indexOf("--pk-card:") < 0, "profile must not keep a second copy of the canonical palette");
assert.ok(profileStyle.indexOf("--pk-red:") < 0, "profile must not keep a second copy of the canonical palette");

var reportStyle = fs.readFileSync(path.join(root, "pages/report/report.wxss"), "utf8");
var reportMarkup = fs.readFileSync(path.join(root, "pages/report/report.wxml"), "utf8");
assert.ok(reportStyle.indexOf("学情二/三级详情统一壳") >= 0, "report detail views must share the paper shell");
assert.ok(reportMarkup.indexOf("report-detail-active") >= 0, "report markup must mark non-home detail views explicitly");
assert.ok(reportStyle.indexOf(".report-page.paper.report-detail-active .report-detail-hero") >= 0, "report detail hero must be scoped away from home");
assert.ok(reportStyle.indexOf(".report-page.paper .glass-card") < 0, "report home must not inherit the detail shell");
assert.ok(reportStyle.indexOf("详情可读性 contract") >= 0, "report detail views must own a readable detail contract");
assert.ok(reportStyle.indexOf("padding-bottom: calc(188rpx + env(safe-area-inset-bottom))") >= 0, "report detail content must clear the fixed tab bar");
[
  ".attempt-card",
  ".scoring-point-empty",
  ".learning-brain-state",
  ".mistake-history-card",
].forEach(function (selector) {
  assert.ok(reportStyle.indexOf(".report-page.paper.report-detail-active " + selector) >= 0,
    "report detail readability contract must cover " + selector);
});
assertNoLegacyBlue(reportStyle, [
  ".learning-engine-panel",
  ".engine-panel-rail",
  ".engine-summary",
  ".engine-source-card.source-active",
  ".source-active .engine-source-status",
  ".learning-state-section-rail",
  ".battle-plan-action",
  ".battle-plan-action text:first-child",
  ".battle-plan-action text:last-child",
  ".detail-metric-row > view",
  ".detail-metric-num",
  ".learning-state-step-text",
  ".learning-state-layer-label",
  ".learning-state-row-action",
], "report");

var assessmentStyle = fs.readFileSync(path.join(root, "pages/assessment/assessment.wxss"), "utf8");
var assessmentMarkup = fs.readFileSync(path.join(root, "pages/assessment/assessment.wxml"), "utf8");
var assessmentLogic = fs.readFileSync(path.join(root, "pages/assessment/assessment.js"), "utf8");
assert.ok(assessmentStyle.indexOf(".assess-page.paper .aurora-layer") >= 0, "assessment must remove the legacy blue aurora inside five modules");
assertNoLegacyBlue(assessmentStyle, [
  ".recommend-badge",
  ".recommend-reason",
  ".feature-dot",
  ".q-type",
  ".archetype-card",
  ".dr-hero",
  ".dr-hero::before",
  ".dr-hero::after",
  ".dr-kicker",
  ".dr-score-ring",
  ".dr-score-ring::before",
  ".dr-score-inner",
  ".dr-conclusion-cell",
  ".dr-metric",
  ".dr-metric::before",
  ".dr-step-num",
  ".dr-step-time",
], "assessment");
assert.ok(assessmentMarkup.indexOf("archetypeColor") < 0, "assessment markup must not inject a second palette inline");
assert.ok(assessmentLogic.indexOf("ARCHETYPE_COLORS") < 0, "assessment logic must not own presentation colors");

console.log("PASS test_five_module_paper_ink_authority.js");
