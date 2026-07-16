// test_package_five_tab_shell_contract.js — 五 tab 纸墨壳契约
// 单一壳权威:学习/历史/问鲁班(中央红章)/学情/我的;
// 复测归学习任务状态，历史只承载对话列表。
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
  { pagePath: ROUTES.history, text: "历史" },
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
  list.some(function (item) { return item.pagePath === ROUTES.history && item.text === "历史"; }),
  "history must occupy tab index 1",
);
assert(
  list.every(function (item) { return item.text !== "复习"; }),
  "review must not remain an independent shell module",
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

// ── 4. 页面 selected 归位:学习0/历史1/问鲁班2/学情3/我的4 ──
var pins = [
  { file: "packageDeeptutor/pages/learn/learn.js", needle: "syncTabBar(this, 0", label: "learn selected=0" },
  { file: "packageDeeptutor/pages/history/history.js", needle: "syncTabBar(this, 1", label: "history selected=1" },
  { file: "packageDeeptutor/pages/chat/chat.js", needle: "syncTabBar(this, 2", label: "chat selected=2" },
  { file: "packageDeeptutor/pages/report/report.js", needle: "syncTabBar(this, 3", label: "report selected=3" },
  { file: "packageDeeptutor/pages/profile/profile.js", needle: "syncTabBar(this, 4", label: "profile selected=4" },
];
pins.forEach(function (pin) {
  assert(read(pin.file).indexOf(pin.needle) >= 0, pin.label + " should sync via helpers.syncTabBar");
});
// ── 5. 学习/历史页:共享组件挂载 + 禁内联 tabbar 残留 ────────
["packageDeeptutor/pages/learn/learn.json", "packageDeeptutor/pages/history/history.json"].forEach(
  function (file) {
    var json = JSON.parse(read(file));
    var components = json.usingComponents || {};
    assert(
      String(components["workspace-shell"] || "").indexOf("custom-tab-bar/index") >= 0,
      file + " should register the shared workspace shell",
    );
  },
);
["packageDeeptutor/pages/learn/learn.wxml", "packageDeeptutor/pages/history/history.wxml"].forEach(
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

// 旧复习 URL 只为历史深链兼容，不得继续伪装成 index=1 的壳内模块。
var legacyReviewJs = read("packageDeeptutor/pages/luban/review/review.js");
var legacyReviewWxml = read("packageDeeptutor/pages/luban/review/review.wxml");
var legacyReviewJson = JSON.parse(read("packageDeeptutor/pages/luban/review/review.json"));
assert(
  legacyReviewJs.indexOf("syncTabBar") === -1,
  "legacy review deep-link page must not select the history shell slot",
);
assert(
  legacyReviewWxml.indexOf("<workspace-shell") === -1,
  "legacy review deep-link page must not mount the five-module shell",
);
assert(
  !((legacyReviewJson.usingComponents || {})["workspace-shell"]),
  "legacy review deep-link page must not register the five-module shell",
);

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
