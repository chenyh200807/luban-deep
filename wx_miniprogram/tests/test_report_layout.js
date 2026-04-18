// test_report_layout.js — regression checks for report page duplicate hints
// Run: node wx_miniprogram/tests/test_report_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../pages/report/report.wxml"),
  "utf8",
);

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

assert(
  reportWxml.indexOf('<text class="overview-tip" wx:if="{{studyTip}}">{{studyTip}}</text>') >= 0,
  "report overview should still render learner studyTip",
);
assert(
  reportWxml.indexOf('wx:elif="{{focusHint}}"') < 0,
  "report overview should not render focusHint a second time above the dedicated insight strip",
);
assert(
  reportWxml.indexOf('<view class="insight-strip glass-card" wx:if="{{focusHint}}">') >= 0,
  "report page should keep the dedicated focusHint insight strip",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
