// test_renderer_authority.js — renderer should have one production authority
// Run: node wx_miniprogram/tests/test_renderer_authority.js

var fs = require("fs");
var path = require("path");

var repoRoot = path.resolve(__dirname, "../..");
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
  return fs.readFileSync(path.join(repoRoot, relPath), "utf8");
}

function walk(dir, out) {
  out = out || [];
  fs.readdirSync(dir).forEach(function (name) {
    var full = path.join(dir, name);
    var stat = fs.statSync(full);
    if (stat.isDirectory()) {
      walk(full, out);
      return;
    }
    out.push(full);
  });
  return out;
}

function rel(fullPath) {
  return path.relative(repoRoot, fullPath);
}

[
  "utils/markdown.js",
  "utils/markdown-normalize.js",
  "utils/devtools-markdown-fixtures.js",
  "utils/render-schema.js",
].forEach(function (suffix) {
  assert(
    read("wx_miniprogram/" + suffix) === read("yousenwebview/packageDeeptutor/" + suffix),
    suffix + " should stay byte-identical across wx_miniprogram and packageDeeptutor",
  );
});

[
  "wx_miniprogram/pages/chat/chat.js",
  "yousenwebview/packageDeeptutor/pages/chat/chat.js",
].forEach(function (file) {
  var source = read(file);
  assert(
    source.indexOf('require("../../utils/ai-message-state")') >= 0,
    file + " should derive AI render state through ai-message-state",
  );
  assert(
    source.indexOf("deriveAiMessageRenderState") >= 0,
    file + " should call the canonical render-state derivation",
  );
  assert(
    source.indexOf('require("../../utils/markdown")') < 0 &&
      source.indexOf('require("../../utils/markdown-normalize")') < 0,
    file + " should not bypass ai-message-state with direct markdown parsing",
  );
});

[
  "wx_miniprogram/pages/chat/chat.wxml",
  "yousenwebview/packageDeeptutor/pages/chat/chat.wxml",
].forEach(function (file) {
  var source = read(file);
  assert(
    source.indexOf("{{li.index}}.") >= 0,
    file + " should render ordered-list labels from canonical item.index",
  );
  assert(
    source.indexOf("{{liIndex + 1}}") < 0 && source.indexOf("{{index + 1}}.") < 0,
    file + " should not synthesize ordered-list labels in the template",
  );
});

var productionFiles = [
  path.join(repoRoot, "wx_miniprogram/pages"),
  path.join(repoRoot, "wx_miniprogram/utils"),
  path.join(repoRoot, "yousenwebview/packageDeeptutor/pages"),
  path.join(repoRoot, "yousenwebview/packageDeeptutor/utils"),
].reduce(function (acc, dir) {
  return acc.concat(walk(dir).filter(function (file) {
    return /\.js$/.test(file);
  }));
}, []);

var parseCallers = productionFiles.filter(function (file) {
  return read(rel(file)).indexOf("parseWithIds") >= 0;
}).map(rel).sort();

assert(
  JSON.stringify(parseCallers) ===
    JSON.stringify([
      "wx_miniprogram/utils/ai-message-state.js",
      "wx_miniprogram/utils/markdown.js",
      "yousenwebview/packageDeeptutor/utils/ai-message-state.js",
      "yousenwebview/packageDeeptutor/utils/markdown.js",
    ]),
  "parseWithIds should only live in markdown.js and be consumed by ai-message-state",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_renderer_authority.js (" + pass + " assertions)");
