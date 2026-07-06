// test_package_five_tab_shell_contract.js — 五 tab 纸墨壳契约
// 单一壳权威:学习/复习/问鲁班(中央红章)/学情/我的;历史不在壳中;
// 学习/复习页禁内联第二套 tabbar。
// Run: node yousenwebview/tests/test_package_five_tab_shell_contract.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

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
  return fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
}

// ── 1. 共享壳组件:五 tab 顺序 / 路由 / 中央红章 ─────────────
var ROUTES = {
  learn: "/packageDeeptutor/pages/learn/learn",
  lubanReview: "/packageDeeptutor/pages/luban/review/review",
  chat: "/packageDeeptutor/pages/chat/chat",
  report: "/packageDeeptutor/pages/report/report",
  profile: "/packageDeeptutor/pages/profile/profile",
  history: "/packageDeeptutor/pages/history/history",
};

function loadShellDef() {
  var source = read("packageDeeptutor/custom-tab-bar/index.js");
  var componentDef = null;
  var sandbox = {
    console: console,
    require: function (request) {
      if (request === "../utils/route") {
        return {
          learn: function () { return ROUTES.learn; },
          lubanReview: function () { return ROUTES.lubanReview; },
          chat: function () { return ROUTES.chat; },
          report: function () { return ROUTES.report; },
          profile: function () { return ROUTES.profile; },
          history: function () { return ROUTES.history; },
        };
      }
      if (request === "../utils/runtime") {
        return { setWorkspaceBack: function () {}, clearWorkspaceBack: function () {} };
      }
      if (request === "../utils/flags") {
        return {
          resolveShellList: function (list) { return list; },
          shouldShowWorkspaceShell: function () { return true; },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: { redirectTo: function () {}, reLaunch: function () {} },
    Component: function (def) { componentDef = def; },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/custom-tab-bar/index.js",
  });
  return componentDef;
}

var def = loadShellDef();
var list = (def && def.data && def.data.list) || [];

assert(list.length === 5, "shell should expose exactly five tabs");
var expected = [
  { pagePath: ROUTES.learn, text: "学习" },
  { pagePath: ROUTES.lubanReview, text: "复习" },
  { pagePath: ROUTES.chat, text: "问鲁班" },
  { pagePath: ROUTES.report, text: "学情" },
  { pagePath: ROUTES.profile, text: "我的" },
];
expected.forEach(function (want, idx) {
  var item = list[idx] || {};
  assert(
    item.pagePath === want.pagePath && item.text === want.text,
    "tab " + idx + " should be " + want.text + " -> " + want.pagePath +
      " (got " + item.text + " -> " + item.pagePath + ")",
  );
});
assert(list[2] && list[2].seal === true, "问鲁班 tab (index 2) should carry the central seal marker");
assert(
  list.every(function (item) { return item.pagePath !== ROUTES.history; }),
  "history must not appear in the five-tab shell (entry lives in chat top-bar clock)",
);

// ── 2. 壳 wxml:中央红章视觉(pk-seal + logo) ─────────────────
var shellWxml = read("packageDeeptutor/custom-tab-bar/index.wxml");
assert(shellWxml.indexOf("pk-seal") >= 0, "shell wxml should render the pk-seal central stamp");
assert(
  shellWxml.indexOf("/packageDeeptutor/images/logo-mark-white.png") >= 0,
  "central seal should use the white logo mark",
);
assert(shellWxml.indexOf("item.seal") >= 0, "seal rendering should be driven by the list item marker");

// ── 3. 壳 wxss:纸墨 --pk-* 双态 token(单一 token 权威) ─────
var shellWxss = read("packageDeeptutor/custom-tab-bar/index.wxss");
assert(
  shellWxss.indexOf('@import "/packageDeeptutor/styles/paper-ink.wxss"') >= 0,
  "shell wxss should import paper-ink tokens instead of duplicating them",
);
assert(
  shellWxml.indexOf("paper {{isDark?'':'light'}}") >= 0,
  "shell root should carry paper/.light dual-theme classes",
);

// ── 4. 页面 selected 归位:学习0/复习1/问鲁班2/学情3/我的4;历史=-1 ──
var pins = [
  { file: "packageDeeptutor/pages/learn/learn.js", needle: "syncTabBar(this, 0", label: "learn selected=0" },
  { file: "packageDeeptutor/pages/luban/review/review.js", needle: "syncTabBar(this, 1", label: "review selected=1" },
  { file: "packageDeeptutor/pages/chat/chat.js", needle: "syncTabBar(this, 2", label: "chat selected=2" },
  { file: "packageDeeptutor/pages/report/report.js", needle: "syncTabBar(this, 3", label: "report selected=3" },
  { file: "packageDeeptutor/pages/profile/profile.js", needle: "syncTabBar(this, 4", label: "profile selected=4" },
];
pins.forEach(function (pin) {
  assert(read(pin.file).indexOf(pin.needle) >= 0, pin.label + " should sync via helpers.syncTabBar");
});
var historyJs = read("packageDeeptutor/pages/history/history.js");
assert(
  historyJs.indexOf("syncTabBar(this, -1") >= 0 &&
    !/syncTabBar\(this,\s*[0-4]\b/.test(historyJs),
  "history keeps the shell mounted but with no selected tab (selected=-1)",
);

// ── 5. 学习/复习页:共享组件挂载 + 禁内联 tabbar 残留 ────────
["packageDeeptutor/pages/learn/learn.json", "packageDeeptutor/pages/luban/review/review.json"].forEach(
  function (file) {
    var json = JSON.parse(read(file));
    var components = json.usingComponents || {};
    assert(
      String(components["workspace-shell"] || "").indexOf("custom-tab-bar/index") >= 0,
      file + " should register the shared workspace shell",
    );
  },
);
["packageDeeptutor/pages/learn/learn.wxml", "packageDeeptutor/pages/luban/review/review.wxml"].forEach(
  function (file) {
    var wxml = read(file);
    assert(wxml.indexOf("<workspace-shell") >= 0, file + " should mount the shared shell");
    assert(wxml.indexOf("lr-tabbar") === -1, file + " must not keep an inline tabbar");
  },
);
var learnJs = read("packageDeeptutor/pages/learn/learn.js");
["tabAsk", "tabReview", "tabReport", "tabProfile"].forEach(function (handler) {
  assert(learnJs.indexOf(handler) === -1, "learn.js must drop inline tab handler " + handler);
});
var learnWxss = read("packageDeeptutor/pages/learn/learn.wxss");
["lr-tabbar", "lr-tab-ico", "lr-tab-seal", "lr-ico-learn", "lr-tab--center"].forEach(function (cls) {
  assert(learnWxss.indexOf(cls) === -1, "learn.wxss must drop orphan inline tabbar style " + cls);
});

// ── 6. 文案铁律:壳面禁审视揭短词 ───────────────────────────
var FORBIDDEN = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
[
  "packageDeeptutor/custom-tab-bar/index.js",
  "packageDeeptutor/custom-tab-bar/index.wxml",
  "packageDeeptutor/custom-tab-bar/index.wxss",
].forEach(function (file) {
  var text = read(file);
  FORBIDDEN.forEach(function (word) {
    assert(text.indexOf(word) === -1, file + " must not contain forbidden word " + word);
  });
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_five_tab_shell_contract.js (" + pass + " assertions)");
