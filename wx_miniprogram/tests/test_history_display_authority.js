// test_history_display_authority.js — history list should show user-facing labels and clean previews
// Run: node wx_miniprogram/tests/test_history_display_authority.js

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

function loadHistoryPage(rawConversations, initialStorage) {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/history/history.js"),
    "utf8",
  );
  var pageDef = null;
  var storage = Object.assign({}, initialStorage || {});
  var sandbox = {
    console: console,
    Date: Date,
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getConversations: function () {
            return Promise.resolve({ conversations: rawConversations });
          },
          unwrapResponse: function (raw) {
            return raw;
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          formatTime: function () {
            return "刚刚";
          },
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
          vibrate: function () {},
          syncTabBar: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key] || "";
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/pages/history/history.js",
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
  return page;
}

(async function () {
  var page = loadHistoryPage([
    {
      id: "tb_history_1",
      title: "New conversation",
      capability: "tutorbot",
      source: "wx_miniprogram",
      status: "completed",
      message_count: 4,
      updated_at: "2026-04-24T10:00:00.000Z",
      created_at: "2026-04-24T09:59:00.000Z",
      last_message:
        "| 考点 | 分值 |\n| ------ | ------ |\n| 安装牢固、启闭灵活 | 0.5 |",
    },
  ]);

  await page._fetchFromServer(false);
  await Promise.resolve();

  var item = page.data.conversations[0];
  assert(item.capabilityLabel === "智能对话", "TutorBot runtime label should not leak into history UI");
  assert(item.preview.indexOf("------") < 0, "history preview should remove markdown table separator rows");
  assert(item.preview.indexOf("安装牢固、启闭灵活") >= 0, "history preview should keep visible table content");

  var cachedPage = loadHistoryPage([], {
    history_cache: {
      ts: Date.now(),
      conversations: [
        {
          id: "cached_tb_history_1",
          title: "New conversation",
          preview: "考点 分值 ------ ------ 安装牢固、启闭灵活 0.5",
          capabilityLabel: "TutorBot",
          ts: Date.now(),
        },
      ],
      groups: [{ label: "今天", items: [] }],
    },
  });

  cachedPage._loadWithCache();

  var cachedItem = cachedPage.data.conversations[0];
  assert(cachedItem.capabilityLabel === "智能对话", "cached TutorBot label should be migrated before display");
  assert(cachedItem.preview.indexOf("------") < 0, "cached preview should be cleaned before display");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_history_display_authority.js (" + pass + " assertions)");
})();
