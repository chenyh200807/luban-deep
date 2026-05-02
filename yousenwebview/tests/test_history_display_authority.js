// test_history_display_authority.js — package history list should show user-facing labels and clean previews
// Run: node yousenwebview/tests/test_history_display_authority.js

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
    path.join(__dirname, "../packageDeeptutor/pages/history/history.js"),
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
          formatTime: function (value) {
            return "fmt:" + value;
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
      if (request === "../../utils/runtime") {
        return {
          setWorkspaceBack: function () {},
          setPendingConversationId: function () {},
        };
      }
      if (request === "../../utils/route") {
        return {
          history: function () {
            return "/packageDeeptutor/pages/history/history";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          ensureFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return false;
          },
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
    filename: "yousenwebview/packageDeeptutor/pages/history/history.js",
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
  page._testStorage = storage;
  return page;
}

(async function () {
  var nowMs = Date.now();
  var legacySeconds = Math.floor((nowMs - 2 * 86400000) / 1000);
  var page = loadHistoryPage([
    {
      id: "tb_history_1",
      title: "New conversation",
      capability: "tutorbot",
      source: "wx_miniprogram",
      status: "completed",
      message_count: 4,
      preferences: {
        chat_mode: "deep",
        interaction_hints: {
          requested_response_mode: "deep",
          selected_mode: "deep",
        },
      },
      updated_at: "2026-04-24T10:00:00.000Z",
      created_at: "2026-04-24T09:59:00.000Z",
      last_message:
        "| 考点 | 分值 |\n| ------ | ------ |\n| 安装牢固、启闭灵活 | 0.5 |",
    },
    {
      id: "today_ms_authority",
      title: "今天提问",
      capability: "chat",
      source: "wx_miniprogram",
      status: "completed",
      message_count: 2,
      preferences: {
        chat_mode: "smart",
        interaction_hints: {
          requested_response_mode: "smart",
        },
      },
      updated_at: "not-parseable-by-client",
      updated_at_ms: nowMs,
      created_at_ms: nowMs - 1000,
      last_message: "今天刚问的问题",
    },
    {
      id: "legacy_seconds_authority",
      title: "秒级时间戳",
      capability: "chat",
      source: "wx_miniprogram",
      status: "completed",
      message_count: 2,
      updated_at: legacySeconds,
      created_at: Math.floor((nowMs - 2 * 86400000 - 1000) / 1000),
      last_message: "两天前的问题",
    },
  ]);

  await page._fetchFromServer(false);
  await Promise.resolve();

  var item = page.data.conversations.filter(function (conv) {
    return conv.id === "tb_history_1";
  })[0];
  assert(item.modeLabel === "深度", "history card should display response mode instead of TutorBot runtime identity");
  assert(item.modeLabel !== "智能", "history mode label should never display smart/auto as a final mode");
  assert(item.capabilityLabel === "智能对话", "capability identity may remain internal but should not drive the visible tag");
  assert(item.preview.indexOf("------") < 0, "history preview should remove markdown table separator rows");
  assert(item.preview.indexOf("安装牢固、启闭灵活") >= 0, "history preview should keep visible table content");
  var smartFallbackItem = page.data.conversations.filter(function (conv) {
    return conv.id === "today_ms_authority";
  })[0];
  assert(smartFallbackItem.modeLabel === "快速", "smart/auto history without selected mode should fall back to a fast/deep label");
  assert(page.data.stats.weekCount >= 2, "history stats should count today and recent conversations from canonical timestamps");
  var legacySecondsItem = page.data.conversations.filter(function (conv) {
    return conv.id === "legacy_seconds_authority";
  })[0];
  assert(
    legacySecondsItem.time === "fmt:" + legacySeconds * 1000,
    "legacy seconds timestamps should be converted before formatting card time",
  );
  assert(
    page.data.groups.some(function (group) {
      return group.label === "今天" && group.items.some(function (conv) {
        return conv.id === "today_ms_authority";
      });
    }),
    "today conversation should be grouped under 今天 when updated_at_ms is present",
  );

  var cachedPage = loadHistoryPage([], {
    history_cache: {
      ts: Date.now(),
      conversations: [
        {
          id: "cached_tb_history_1",
          title: "New conversation",
          preview: "考点 分值 ------ ------ 安装牢固、启闭灵活 0.5",
          capabilityLabel: "TutorBot",
          time: "1/21 21:36",
          preferences: {
            interaction_hints: {
              effective_response_mode: "fast",
            },
          },
          rawTime: Math.floor(nowMs / 1000),
        },
      ],
      groups: [{ label: "今天", items: [] }],
    },
  });

  cachedPage._loadWithCache();

  var cachedItem = cachedPage.data.conversations[0];
  assert(cachedItem.modeLabel === "快速", "cached TutorBot label should be replaced by response mode before display");
  assert(cachedItem.capabilityLabel === "智能对话", "cached TutorBot identity should be migrated away from visible labels");
  assert(cachedItem.preview.indexOf("------") < 0, "cached preview should be cleaned before display");
  assert(cachedPage.data.stats.weekCount === 1, "cached rawTime should be migrated into the week count");
  assert(cachedItem.time !== "1/21 21:36", "cached stale card time should be recomputed from canonical rawTime");
  assert(cachedItem.time === "fmt:" + Math.floor(nowMs / 1000) * 1000, "cached seconds rawTime should be formatted as milliseconds");

  var deletedPage = loadHistoryPage(
    [
      {
        id: "deleted_after_ack",
        title: "已删除但服务端旧列表仍返回",
        capability: "chat",
        source: "wx_miniprogram",
        status: "completed",
        message_count: 1,
        updated_at_ms: nowMs,
        last_message: "这条不应重新出现",
      },
      {
        id: "visible_after_refresh",
        title: "保留对话",
        capability: "chat",
        source: "wx_miniprogram",
        status: "completed",
        message_count: 1,
        updated_at_ms: nowMs,
        last_message: "这条应该保留",
      },
    ],
    {
      history_deleted_conversation_ids: {
        deleted_after_ack: nowMs,
      },
    },
  );

  await deletedPage._fetchFromServer(false);
  await Promise.resolve();

  assert(
    deletedPage.data.conversations.length === 1 &&
      deletedPage.data.conversations[0].id === "visible_after_refresh",
    "history refresh should not resurrect a conversation after delete was acknowledged",
  );
  assert(
    deletedPage._testStorage.history_cache.conversations.length === 1 &&
      deletedPage._testStorage.history_cache.conversations[0].id === "visible_after_refresh",
    "history cache should also exclude deleted tombstone conversations",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_history_display_authority.js (" + pass + " assertions)");
})();
