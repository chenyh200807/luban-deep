// test_package_chat_longpress_selectable.js — package AI answer nodes must support native long-press selection
// Run: node yousenwebview/tests/test_package_chat_longpress_selectable.js

var fs = require("fs");
var path = require("path");

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

function read(relPath) {
  return fs.readFileSync(path.join(__dirname, "..", relPath), "utf8");
}

var wxml = read("packageDeeptutor/pages/chat/chat.wxml");
var wxss = read("packageDeeptutor/pages/chat/chat.wxss");

var richTextTags = wxml.match(/<rich-text\b[^>]*>/g) || [];
assert(richTextTags.length > 0, "package chat should render markdown with rich-text nodes");
richTextTags.forEach(function (tag) {
  assert(
    /\buser-select\b/.test(tag),
    "rich-text answer node should be selectable: " + tag,
  );
});

[
  "md-table-card-title",
  "md-table-card-key",
  "md-table-card-val",
  "md-steps-title",
  "md-step-name",
  "md-step-detail",
  "md-recap-title",
  "md-chart-title",
  "md-chart-axis",
  "mcq-stem",
  "mcq-val",
].forEach(function (className) {
  var pattern = new RegExp('<text[^>]*class="' + className + '[^"]*"[^>]*\\buser-select\\b');
  assert(pattern.test(wxml), className + " should opt into long-press selection");
});

assert(
  /\.bubble-ai[\s\S]*user-select:\s*text/.test(wxss) &&
    /\.bubble-ai text[\s\S]*user-select:\s*text/.test(wxss) &&
    /\.bubble-ai rich-text[\s\S]*user-select:\s*text/.test(wxss),
  "package AI bubble stylesheet should allow native text selection",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_longpress_selectable.js (" + pass + " assertions)");
