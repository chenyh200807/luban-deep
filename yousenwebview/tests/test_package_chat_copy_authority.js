// test_package_chat_copy_authority.js — packageDeeptutor copy button should use visible content
// Run: node yousenwebview/tests/test_package_chat_copy_authority.js

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

function loadChatPage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var clipboard = [];
  var toasts = [];
  var helpersMock = {
    getAnimConfig: function () {
      return {
        flushThrottleMs: 16,
        mdParseInterval: 3,
        enableBreathingOrbs: false,
        enableMarquee: false,
        enableMsgAnimation: false,
        enableFocusPulse: false,
      };
    },
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
        windowWidth: 375,
        screenWidth: 375,
        windowHeight: 812,
        screenHeight: 812,
        safeArea: { bottom: 778 },
      };
    },
    isDark: function () {
      return true;
    },
    getTimeGreeting: function () {
      return "上午好";
    },
    syncTabBar: function () {},
    vibrate: function () {},
  };
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/api") {
        return { unwrapResponse: function (raw) { return raw; } };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") return { track: function () {}, trackOnce: function () {} };
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      removeStorageSync: function () {},
      setClipboardData: function (payload) {
        clipboard.push(payload.data);
      },
      showToast: function (payload) {
        toasts.push(payload);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "yousenwebview/packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });
  return { page: page, clipboard: clipboard, toasts: toasts };
}

var loaded = loadChatPage();
loaded.page.setData({
  messages: [
    {
      id: "a1",
      role: "ai",
      content: "",
      renderableContent: "",
      blocks: [
        {
          type: "table",
          caption: "防火门考点",
          headers: [
            { content: [{ type: "text", text: "考点" }] },
            { nodes: [{ type: "text", text: "分值" }] },
          ],
          rows: [
            [
              { content: [{ type: "text", text: "防火门" }] },
              {
                nodes: [
                  {
                    name: "span",
                    children: [{ type: "text", text: "2" }],
                  },
                ],
              },
            ],
          ],
        },
        {
          type: "formula_block",
          displayText: "A = πr²",
          copyText: "A = \\pi r^2",
        },
      ],
      mcqCards: null,
    },
    {
      id: "a2",
      role: "ai",
      content: "raw fallback should not win",
      renderableContent: "",
      blocks: [],
      mcqCards: [
        {
          index: 1,
          stem: "防火门构造的基本要求有（ ）。",
          options: [
            { key: "A", text: "耐火极限符合要求" },
            { key: "B", text: "可以任意开启" },
          ],
        },
      ],
    },
    {
      id: "a3",
      role: "ai",
      content: "",
      renderableContent: "",
      blocks: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "后台处理已经完成，" },
            { type: "strong", children: [{ type: "text", text: "可复制可见文本" }] },
          ],
        },
        {
          type: "ul",
          items: [
            {
              nodes: [
                { type: "text", text: "不要复制 " },
                { type: "code", children: [{ type: "text", text: "[object Object]" }] },
              ],
            },
          ],
        },
      ],
      mcqCards: null,
    },
  ],
});

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a1" } } });
assert(
  loaded.clipboard[0].indexOf("防火门考点") >= 0 &&
    loaded.clipboard[0].indexOf("考点 | 分值") >= 0 &&
    loaded.clipboard[0].indexOf("A = \\pi r^2") >= 0,
  "copy should serialize visible structured blocks when raw content is empty",
);

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a2" } } });
assert(
  loaded.clipboard[1].indexOf("防火门构造的基本要求") >= 0 &&
    loaded.clipboard[1].indexOf("A. 耐火极限符合要求") >= 0 &&
    loaded.clipboard[1].indexOf("raw fallback should not win") < 0,
  "copy should prefer visible MCQ cards over raw fallback text",
);

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a3" } } });
assert(
  loaded.clipboard[2].indexOf("后台处理已经完成，可复制可见文本") >= 0 &&
    loaded.clipboard[2].indexOf("- 不要复制 [object Object]") >= 0 &&
    loaded.clipboard[2] !== "[object Object],[object Object]",
  "copy should serialize markdown rich-text node arrays instead of object placeholders",
);

assertEqual(loaded.toasts.length, 0, "copying visible content should not show an empty toast");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_copy_authority.js (" + pass + " assertions)");
