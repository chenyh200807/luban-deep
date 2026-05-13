// test_markdown_regression_fixtures.js — devtools markdown regression samples
// Run: node wx_miniprogram/tests/test_markdown_regression_fixtures.js

var fixtures = require("../utils/devtools-markdown-fixtures");
var normalize = require("../utils/markdown-normalize");
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
assert(samples.length >= 4, "should expose at least 4 markdown regression samples");

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

var constructionSample = fixtures.getMarkdownRegressionSample("construction_case_numbered_sections");
var constructionNormalized = normalize.normalizeMarkdownForWechat(
  constructionSample && constructionSample.content,
);
assert(
  constructionNormalized.indexOf("1. 进度管理") >= 0 &&
    constructionNormalized.indexOf("- 双代号网络计划") >= 0,
  "construction fixture should normalize compact numbered and bullet markers before parsing",
);
var constructionBlocks = deriveBlocks("construction_case_numbered_sections");
var orderedIndexes = [];
var bulletCount = 0;
for (var i = 0; i < constructionBlocks.length; i++) {
  if (constructionBlocks[i].type === "ol") {
    for (var j = 0; j < constructionBlocks[i].items.length; j++) {
      orderedIndexes.push(constructionBlocks[i].items[j].index);
    }
  }
  if (constructionBlocks[i].type === "ul") {
    bulletCount += constructionBlocks[i].items.length;
  }
}
assert(
  JSON.stringify(orderedIndexes) === JSON.stringify([1, 2, 7, 8, 9, 10, 11]),
  "construction fixture should preserve explicit visible numbering across blank-separated OL blocks",
);
assert(bulletCount >= 5, "construction fixture should split compact dash bullets into bullet blocks");

var chineseMarkerBlocks = deriveBlocks("chinese_ordered_markers");
var chineseOrderedIndexes = [];
var chineseBulletTexts = [];
var chineseCalloutLabels = [];
for (var k = 0; k < chineseMarkerBlocks.length; k++) {
  if (chineseMarkerBlocks[k].type === "ol") {
    for (var l = 0; l < chineseMarkerBlocks[k].items.length; l++) {
      chineseOrderedIndexes.push(chineseMarkerBlocks[k].items[l].index);
    }
  }
  if (chineseMarkerBlocks[k].type === "ul") {
    for (var m = 0; m < chineseMarkerBlocks[k].items.length; m++) {
      chineseBulletTexts.push(chineseMarkerBlocks[k].items[m].raw);
    }
  }
  if (chineseMarkerBlocks[k].type === "callout") {
    chineseCalloutLabels.push(chineseMarkerBlocks[k].label);
  }
}
assert(
  JSON.stringify(chineseOrderedIndexes) === JSON.stringify([1, 2, 3]),
  "Chinese marker fixture should normalize 1）/2、/（3） into ordered items",
);
assert(
  chineseBulletTexts.length === 3,
  "Chinese marker fixture should split punctuation-separated inline bullets",
);
assert(
  chineseCalloutLabels.indexOf("踩分点-案例题") >= 0,
  "Chinese marker fixture should keep qualified callout labels styled as callouts",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_markdown_regression_fixtures.js (" + pass + " assertions)");
