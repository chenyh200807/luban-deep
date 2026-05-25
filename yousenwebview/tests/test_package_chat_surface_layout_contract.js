// test_package_chat_surface_layout_contract.js — package chat surface should keep inputs and nav controls reachable
// Run: node yousenwebview/tests/test_package_chat_surface_layout_contract.js

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

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", rel), "utf8");
}

var chatWxml = read("pages/chat/chat.wxml");
var chatWxss = read("pages/chat/chat.wxss");
var chatJs = read("pages/chat/chat.js");
var historyWxml = read("pages/history/history.wxml");
var historyWxss = read("pages/history/history.wxss");
var historyJs = read("pages/history/history.js");
var profileWxss = read("pages/profile/profile.wxss");
var practiceWxss = read("pages/practice/practice.wxss");
var reportWxml = read("pages/report/report.wxml");
var reportWxss = read("pages/report/report.wxss");

assert(
  (chatWxml.match(/bindfocus="onKeyboardFocus"/g) || []).length >= 2,
  "both hero and bottom textareas should report keyboard focus",
);
assert(
  (chatWxml.match(/bindblur="onKeyboardBlur"/g) || []).length >= 2,
  "both hero and bottom textareas should report keyboard blur",
);
assert(
  (chatWxml.match(/cursor-spacing="\{\{inputCursorSpacing\}\}"/g) || []).length >= 2,
  "textareas should use a stable cursor spacing authority",
);
assert(
  /onKeyboardFocus:\s*function/.test(chatJs) && /onKeyboardBlur:\s*function/.test(chatJs),
  "chat page should expose keyboard layout handlers",
);
assert(
  /keyboardHeight/.test(chatJs) && /bottomBarStyle/.test(chatWxml),
  "fixed bottom input should be positioned from keyboard height",
);
assert(
  /\.page\.light \.nav-compose-icon[\s\S]*stroke='%23334155'/.test(chatWxss) &&
    /\.page\.light \.nav-more-icon\s*\{\s*color:\s*#334155;/.test(chatWxss),
  "package light chat nav action glyphs should be dark enough on white buttons",
);
assert(
  /padding-right:\s*\{\{navRightInset\}\}px/.test(historyWxml) &&
    /navRightInset/.test(historyJs),
  "history nav actions should reserve system capsule width",
);
assert(
  /class="nav-action-row"/.test(historyWxml) &&
    /\.nav-action-row/.test(historyWxss) &&
    /navActionRowHeight/.test(historyJs),
  "history management actions should sit below the system capsule row",
);
assert(
  /\.history-page\.light \.conv-action-btn\s*\{\s*opacity:\s*1;[\s\S]*background:\s*#eef4ff;/.test(historyWxss) &&
    /\.history-page\.light \.archive-lid\s*\{\s*background:\s*#475569;/.test(historyWxss) &&
    /\.history-page\.light \.conv-del-icon\s*\{\s*color:\s*#475569;/.test(historyWxss),
  "package light history row archive/delete glyphs should remain visible on white cards",
);
assert(
  /\.profile-page\.light \.user-name-edit\s*\{\s*color:\s*#64748b;/.test(profileWxss) &&
    /\.practice-page\.light \.link-arrow\s*\{\s*color:\s*#64748b;/.test(practiceWxss) &&
    /\.report-page\.light \.assess-entry-arrow\s*\{\s*color:\s*#64748b;/.test(reportWxss),
  "package light secondary action arrows should keep enough contrast on white cards",
);
assert(
  reportWxml.indexOf("overallMastery || diagnosticScore") === -1,
  "package report mastery metric should not hide a real zero mastery value behind a truthy fallback",
);
assert(
  chatWxml.indexOf("workflow-step-raw") === -1 &&
    chatWxml.indexOf("后台过程") === -1 &&
    chatWxml.indexOf("完整后台") === -1,
  "package chat workflow summary should not render raw backend trace containers or wording",
);
assert(
  chatWxml.indexOf("真题讲评") >= 0 &&
    chatWxml.indexOf("正确答案") >= 0 &&
    chatWxml.indexOf("解析要点") >= 0 &&
    chatWxml.indexOf("已讲评") >= 0 &&
    chatWxss.indexOf(".mcq-review-notes") >= 0,
  "package question-review MCQ cards should expose learner-facing answer and explanation notes",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_surface_layout_contract.js (" + pass + " assertions)");
