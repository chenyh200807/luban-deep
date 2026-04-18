// test_markdown_regression_fixtures.js — devtools markdown regression samples
// Run: node wx_miniprogram/tests/test_markdown_regression_fixtures.js

var fixtures = require("../utils/devtools-markdown-fixtures");
var aiMessageState = require("../utils/ai-message-state");

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

function deriveBlocks(name) {
  var sample = fixtures.getMarkdownRegressionSample(name);
  assert(!!sample, "fixture should exist: " + name);
  var state = aiMessageState.deriveAiMessageRenderState({
    content: sample ? sample.content : "",
    parseBlocks: true,
  });
  assert(Array.isArray(state.blocks), "state.blocks should be an array for " + name);
  assert(state.blocks.length > 0, "state.blocks should not be empty for " + name);
  return state.blocks;
}

function findBlock(blocks, predicate) {
  for (var i = 0; i < blocks.length; i++) {
    if (predicate(blocks[i])) return blocks[i];
  }
  return null;
}

var samples = fixtures.listMarkdownRegressionSamples();
assert(samples.length >= 3, "should expose at least 3 markdown regression samples");

var boltBlocks = deriveBlocks("bolt_points_colon_wrap");
var boltList = findBlock(boltBlocks, function (block) {
  return block && block.type === "ol";
});
assert(!!boltList, "bolt fixture should keep ordered list block");
assert(
  boltList &&
    boltList.items[0] &&
    boltList.items[0].nodes[0] &&
    boltList.items[0].nodes[0].children[0].text === "时间限制：",
  "bolt fixture should normalize list labels into bold label-with-colon form",
);
assert(
  boltList &&
    boltList.items[0] &&
    boltList.items[0].nodes[1] &&
    boltList.items[0].nodes[1].text.indexOf(" 必须记住") === 0,
  "bolt fixture should keep trailing sentence in the same rich-text sequence after label normalization",
);

var waterproofBlocks = deriveBlocks("waterproof_layers_mixed_inline");
assert(
  waterproofBlocks[2].type === "ul" && waterproofBlocks[2].items.length >= 3,
  "waterproof fixture should keep list structure",
);
var waterproofList = waterproofBlocks[2];
assert(
  waterproofList &&
    waterproofList.items[3] &&
    waterproofList.items[3].nodes[1] &&
    waterproofList.items[3].nodes[1].name === "span",
  "waterproof fixture should render flattened example answers as rich-text spans inside the same list block",
);

var expertBlocks = deriveBlocks("expert_argument_full_answer");
assert(expertBlocks[0].type === "paragraph", "expert fixture should preserve leading paragraph");
assert(
  expertBlocks[0].nodes[0].text.indexOf("第一题的答案：") === 0,
  "expert fixture should keep the leading answer label visible",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_markdown_regression_fixtures.js (" + pass + " assertions)");
