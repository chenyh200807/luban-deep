// test_markdown_golden_corpus.js — production-style markdown renderer corpus
// Run: node wx_miniprogram/tests/test_markdown_golden_corpus.js

var fs = require("fs");
var path = require("path");
var wxAiState = require("../utils/ai-message-state");
var webAiState = require("../../yousenwebview/packageDeeptutor/utils/ai-message-state");

var fixturePath = path.resolve(__dirname, "../../tests/fixtures/wechat_markdown_golden_cases.json");
var cases = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
var REQUIRED_COVERAGE = [
  "blankSeparatedOrdered",
  "compactOrdered",
  "compactHeading",
  "compactDashBullet",
  "nonSequentialIndexes",
  "mixedOrderedBullet",
];
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

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function collectOrderedIndexes(blocks) {
  var indexes = [];
  (blocks || []).forEach(function (block) {
    if (!block || block.type !== "ol" || !Array.isArray(block.items)) return;
    block.items.forEach(function (item) {
      indexes.push(item.index);
    });
  });
  return indexes;
}

function collectBulletTexts(blocks) {
  var texts = [];
  (blocks || []).forEach(function (block) {
    if (!block || block.type !== "ul" || !Array.isArray(block.items)) return;
    block.items.forEach(function (item) {
      texts.push(nodesToText(item.nodes).trim());
    });
  });
  return texts;
}

function nodesToText(nodes) {
  if (nodes == null) return "";
  if (typeof nodes === "string" || typeof nodes === "number") return String(nodes);
  if (!Array.isArray(nodes)) {
    if (typeof nodes === "object") {
      return nodesToText([nodes]);
    }
    return "";
  }
  var parts = [];
  nodes.forEach(function (node) {
    if (node == null) return;
    if (typeof node === "string" || typeof node === "number") {
      parts.push(String(node));
      return;
    }
    if (typeof node !== "object") return;
    if (node.text != null) parts.push(String(node.text));
    if (node.value != null) parts.push(String(node.value));
    if (Array.isArray(node.nodes)) parts.push(nodesToText(node.nodes));
    if (Array.isArray(node.children)) parts.push(nodesToText(node.children));
    if (Array.isArray(node.content)) parts.push(nodesToText(node.content));
  });
  return parts.join("");
}

function blockVisibleText(block) {
  if (!block) return "";
  if (block.type === "heading" || block.type === "paragraph" || block.type === "callout") {
    return nodesToText(block.nodes).trim();
  }
  if (block.type === "blockquote") {
    return (block.lineNodes || block.lines || [])
      .map(function (line) {
        return nodesToText(line).trim();
      })
      .join("\n");
  }
  if (block.type === "ol") {
    return (block.items || [])
      .map(function (item) {
        return String(item.index) + ". " + nodesToText(item.nodes).trim();
      })
      .join("\n");
  }
  if (block.type === "ul") {
    return (block.items || [])
      .map(function (item) {
        return "- " + nodesToText(item.nodes).trim();
      })
      .join("\n");
  }
  if (block.type === "table") {
    var rows = [];
    if (Array.isArray(block.headers)) {
      rows.push(block.headers.map(function (cell) { return nodesToText(cell.nodes || cell.content); }));
    }
    (block.rows || []).forEach(function (row) {
      rows.push((row || []).map(function (cell) { return nodesToText(cell.nodes || cell.content); }));
    });
    return rows.map(function (row) { return row.join(" | "); }).join("\n");
  }
  return "";
}

function stableBlock(block) {
  if (!block) return null;
  if (block.type === "blank" || block.type === "hr") return { type: block.type };
  if (block.type === "heading") {
    return { type: block.type, level: block.level, text: blockVisibleText(block) };
  }
  if (block.type === "ol") {
    return {
      type: block.type,
      items: (block.items || []).map(function (item) {
        return { index: item.index, text: nodesToText(item.nodes).trim() };
      }),
    };
  }
  if (block.type === "ul") {
    return {
      type: block.type,
      items: (block.items || []).map(function (item) {
        return { text: nodesToText(item.nodes).trim() };
      }),
    };
  }
  return { type: block.type, text: blockVisibleText(block) };
}

function toStableRenderContract(state) {
  return {
    renderableContent: state.renderableContent,
    hasStructuredContent: !!state.hasStructuredContent,
    mcqCards: state.mcqCards || null,
    blocks: (state.blocks || []).map(stableBlock),
  };
}

function serializeVisibleBlocks(blocks) {
  var lines = [];
  (blocks || []).forEach(function (block) {
    if (!block) return;
    var text = blockVisibleText(block);
    if (text) lines.push(text);
  });
  return lines.join("\n");
}

assert(cases.length >= 4, "golden corpus should include at least four renderer cases");

var coverage = {};
cases.forEach(function (item) {
  (item.covers || []).forEach(function (key) {
    coverage[key] = true;
  });
});
REQUIRED_COVERAGE.forEach(function (key) {
  assert(coverage[key], "golden corpus should cover " + key);
});

cases.forEach(function (item) {
  var wxState = wxAiState.deriveAiMessageRenderState({
    content: item.content,
    parseBlocks: true,
  });
  var webState = webAiState.deriveAiMessageRenderState({
    content: item.content,
    parseBlocks: true,
  });
  var label = item.name + ": ";

  assertEqual(
    toStableRenderContract(wxState),
    toStableRenderContract(webState),
    label + "wx and webview stable render contract should match",
  );
  assertEqual(
    collectOrderedIndexes(wxState.blocks),
    item.expectedOrderedIndexes,
    label + "ordered indexes should match source truth",
  );
  assertEqual(
    collectBulletTexts(wxState.blocks),
    item.expectedBulletTexts,
    label + "bullet texts should stay segmented",
  );

  var visible = serializeVisibleBlocks(wxState.blocks);
  (item.mustContain || []).forEach(function (needle) {
    assert(visible.indexOf(needle) >= 0, label + "visible blocks should contain " + needle);
  });
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_markdown_golden_corpus.js (" + pass + " assertions)");
