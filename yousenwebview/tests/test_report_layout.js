// test_report_layout.js — regression checks for the hosted report page layout
// Run: node yousenwebview/tests/test_report_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxml"),
  "utf8",
);
var reportWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxss"),
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
  reportWxml.indexOf('wx:for="{{dimList}}"') >= 0,
  "host report page should render every diagnosis dimension below the radar summary",
);
assert(
  reportWxml.indexOf('class="metric-chip metric-chip-progress" bindtap="goPractice"') >= 0,
  "host report today's progress metric should open the practice page",
);
assert(
    reportWxml.indexOf("当前可信结论") >= 0 &&
    reportWxml.indexOf("证据流") >= 0 &&
    reportWxml.indexOf("训练闭环") >= 0 &&
    reportWxml.indexOf("下一步训练") >= 0,
  "host report page should expose the Learning Brain three-part visible chain",
);
assert(
  reportWxss.indexOf(".level-L1_repeated") >= 0 &&
    reportWxss.indexOf(".level-L2_confirmed") >= 0 &&
    reportWxss.indexOf(".chain-not-improved") >= 0,
  "host report styles should distinguish L1/L2 Learning Brain evidence levels and training outcomes",
);
assert(
  reportWxss.indexOf(".dim-list") >= 0 && reportWxss.indexOf(".dim-bar") >= 0,
  "host report page should include styles for the diagnosis dimension list",
);
assert(
  reportWxss.indexOf("width: 280px") < 0 && reportWxss.indexOf("height: 280px") < 0,
  "host report radar should not use a fixed px size that can clip on small screens",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
