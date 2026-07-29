// test_chat_loading_animation_contract.js
// Run: node yousenwebview/tests/test_chat_loading_animation_contract.js

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var wxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
var wxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxss"),
  "utf8",
);

function ruleBody(styles, selector) {
  var start = styles.indexOf(selector + " {");
  assert(start >= 0, "missing style rule: " + selector);
  var open = styles.indexOf("{", start);
  var close = styles.indexOf("}", open);
  assert(open >= 0 && close > open, "malformed style rule: " + selector);
  return styles.slice(open + 1, close);
}

function declarationsForSelector(styles, selector) {
  var escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  var matches = styles.match(new RegExp(escaped + "\\s*\\{[^}]*\\}", "g")) || [];
  return matches.join("\n");
}

function verifyLoadingAnimation(markup, styles) {
  assert(
    /class="thinking-rail"/.test(markup) &&
      /class="dots-bounce"/.test(markup) &&
      /class="thinking-scan /.test(markup),
    "loading panel must render the rail, bouncing dots, and scan line",
  );
  assert(
    /animation:\s*railFlow 2\.2s ease-in-out infinite;/.test(
      ruleBody(styles, ".thinking-rail::after"),
    ),
    "loading rail must keep moving while a turn is active",
  );
  assert(
    /animation:\s*dotBounce 1\.2s ease-in-out infinite;/.test(
      ruleBody(styles, ".dots-bounce .dot"),
    ),
    "loading dots must keep bouncing while a turn is active",
  );
  assert(
    /animation:\s*scanPulse 1\.8s ease-in-out infinite;/.test(
      ruleBody(styles, ".thinking-scan"),
    ),
    "loading scan line must keep pulsing while a turn is active",
  );
  assert(
    /width:\s*10rpx;/.test(ruleBody(styles, ".page.paper .dots-bounce .dot")) &&
      /height:\s*4rpx;/.test(ruleBody(styles, ".page.paper .thinking-scan")),
    "paper theme must enlarge the moving indicators so work remains perceptible",
  );
  assert(
    !/background\s*:|color\s*:/.test(
      declarationsForSelector(styles, ".page.paper .dots-bounce .dot") +
        declarationsForSelector(styles, ".page.paper .thinking-scan") +
        declarationsForSelector(styles, ".page.paper .thinking-rail") +
        declarationsForSelector(styles, ".page.paper .thinking-badge"),
    ),
    "paper theme must inherit the existing light/dark and workflow-tone colors instead of flattening them",
  );
  assert(
    /245,158,11/.test(ruleBody(styles, ".thinking-scan-calc")) &&
      /34,197,94/.test(ruleBody(styles, ".thinking-scan-compose")) &&
      /248,113,113/.test(ruleBody(styles, ".thinking-scan-retry")),
    "calculation, composition, and retry must retain distinct scan colors",
  );
  assert(
    /#2f5fda/.test(ruleBody(styles, ".page.paper.light .dots-bounce .dot")) &&
      /#2f5fda/.test(ruleBody(styles, ".page.paper.light .thinking-scan")) &&
      /#a45a00/.test(ruleBody(styles, ".page.paper.light .thinking-scan-calc")) &&
      /#18794e/.test(ruleBody(styles, ".page.paper.light .thinking-scan-compose")) &&
      /#b42318/.test(ruleBody(styles, ".page.paper.light .thinking-scan-retry")),
    "light paper must use dark, tone-specific colors for visible motion",
  );
  assert(
    !/animation\s*:\s*none/.test(
      declarationsForSelector(styles, ".thinking-rail::after") +
        declarationsForSelector(styles, ".dots-bounce .dot") +
        declarationsForSelector(styles, ".thinking-scan"),
    ),
    "no later theme rule may disable a loading animation",
  );
}

verifyLoadingAnimation(wxml, wxss);

assert.throws(
  function () {
    verifyLoadingAnimation(
      wxml,
      wxss.replace(
        "animation: dotBounce 1.2s ease-in-out infinite;",
        "animation: none;",
      ),
    );
  },
  /loading dots must keep bouncing/,
  "counterexample: the contract must fail if the animation is flattened again",
);

console.log("PASS test_chat_loading_animation_contract.js (loading motion remains perceptible)");
