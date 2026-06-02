// test_citation_format.js — citation display regression tests
// Run: node wx_miniprogram/tests/test_citation_format.js

var wxCitationFormat = require("../utils/citation-format");
var packageCitationFormat = require("../../yousenwebview/packageDeeptutor/utils/citation-format");

var pass = 0;
var fail = 0;
var errors = [];

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function assertCitationFormatter(citationFormat, label) {
  var formatted = citationFormat.formatCitation({
    marker: "〔1〕",
    source_type: "textbook",
    title: "2026 建筑实务教材：屋面防水等级",
    locator: "第 3 章 第 3.5.1 节 p.122",
    public_quote: "屋面防水等级应根据工程重要性确定。",
  });

  assertEqual(formatted.key, "1", label + " marker should become numeric key");
  assertEqual(
    formatted.title,
    "2026 建筑实务教材：屋面防水等级",
    label + " title should stay separate from locator",
  );
  assertEqual(formatted.locator, "第 3 章 第 3.5.1 节 p.122", label + " locator should render as a separate reference line");
  assertEqual(formatted.quote, "屋面防水等级应根据工程重要性确定。", label + " quote should render as separate reference excerpt");
  assertEqual(formatted.sourceType, "教材", label + " source type should render as a compact label");
}

assertCitationFormatter(wxCitationFormat, "wx_miniprogram");
assertCitationFormatter(packageCitationFormat, "packageDeeptutor");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_citation_format.js (" + pass + " assertions)");
process.exit(0);
