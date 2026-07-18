// test_history_archived_swr.js — 全部/已归档切换必须走 SWR 缓存，不得无条件 loading+全量网络
// Run: node yousenwebview/tests/test_history_archived_swr.js
//
// 契约（history.js switchTab → _loadWithCache）：
//   1. 切到已归档且缓存新鲜（<TTL）→ 秒渲染缓存，零网络请求，loading 保持 false。
//   2. 切到已归档且缓存过期（>TTL）→ 先渲染缓存（loading false），后台 silent fetch(archived=true) 刷新并回写缓存。
//   3. 切到已归档且无缓存 → loading:true + fetch(archived=true)，resolve 后渲染服务端数据。
//   4. 切回全部且缓存新鲜 → 零新增网络请求。
//   5. 串台竞态守卫：归档静默刷新在途时切回全部，归档响应到达后不得覆盖
//      「全部」tab 的 UI（conversations/groups/totalCount），但归档缓存照常回写。
//   6. 失败分支同守卫：在途归档请求失败不得把 error 态贴到「全部」tab。

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

// deferred=true 时 getConversations 返回手动 resolve 的 promise，便于断言 pending 期间的 loading 态。
function loadHistoryPage(serverConversationsByTab, initialStorage, deferred) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/history/history.js"),
    "utf8",
  );
  var pageDef = null;
  var storage = Object.assign({}, initialStorage || {});
  var fetchCalls = [];
  var pendingResolvers = [];
  var sandbox = {
    console: console,
    Date: Date,
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getConversations: function (archived) {
            fetchCalls.push(archived);
            var list =
              archived === true
                ? serverConversationsByTab.archived || []
                : serverConversationsByTab.active || [];
            if (deferred) {
              return new Promise(function (resolve, reject) {
                pendingResolvers.push({
                  resolve: function () {
                    resolve({ conversations: list });
                  },
                  reject: function () {
                    reject(new Error("network down"));
                  },
                });
              });
            }
            return Promise.resolve({ conversations: list });
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
            return false;
          },
          isDarkOr: function () {
            return false;
          },
          vibrate: function () {},
          syncTabBar: function () {},
        };
      }
      if (request === "../../utils/history-tombstone") {
        return {
          readDeletedConversationIds: function () {
            return {};
          },
          rememberDeletedConversationIds: function () {},
          filterDeletedConversations: function (convs) {
            return convs || [];
          },
        };
      }
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return true;
          },
          getUserId: function () {
            return "student-a";
          },
          readOwnerStorage: function (key) {
            var envelope = storage[key + ":student-a"];
            if (!envelope || envelope.ownerId !== "student-a") return null;
            return envelope.value;
          },
          writeOwnerStorage: function (key, value) {
            storage[key + ":student-a"] = {
              ownerId: "student-a",
              value: value,
            };
            return true;
          },
          removeOwnerStorage: function (key) {
            delete storage[key + ":student-a"];
            return true;
          },
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
      if (request === "../../utils/surface-telemetry") {
        return {
          trackModuleView: function () {},
          trackModuleExit: function () {},
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
  page._fetchCalls = fetchCalls;
  page._resolvePending = function () {
    var resolvers = pendingResolvers.splice(0);
    resolvers.forEach(function (entry) {
      entry.resolve();
    });
  };
  page._rejectPending = function () {
    var resolvers = pendingResolvers.splice(0);
    resolvers.forEach(function (entry) {
      entry.reject();
    });
  };
  return page;
}

function tapTab(page, tab) {
  page.switchTab({ currentTarget: { dataset: { tab: tab } } });
}

function cacheEnvelope(id, ts) {
  return {
    ownerId: "student-a",
    value: {
      ts: ts,
      conversations: [
        {
          id: id,
          title: "cached " + id,
          preview: "cached preview",
          capabilityLabel: "智能对话",
          rawTime: Math.floor(Date.now() / 1000),
        },
      ],
      groups: [{ label: "今天", items: [] }],
    },
  };
}

function serverConv(id) {
  return {
    id: id,
    title: "server " + id,
    capability: "chat",
    source: "wx_miniprogram",
    status: "completed",
    message_count: 1,
    updated_at_ms: Date.now(),
    last_message: "server message",
  };
}

(async function () {
  var now = Date.now();

  // ── 场景 1：归档缓存新鲜（<60s TTL）→ 秒渲染，零网络 ──
  var freshPage = loadHistoryPage(
    { active: [serverConv("srv_active")], archived: [serverConv("srv_arch")] },
    {
      "history_cache:student-a": cacheEnvelope("cached_active", now),
      "history_cache_archived:student-a": cacheEnvelope("cached_arch", now),
    },
  );
  freshPage.setData({ loading: false, tab: "active" });
  tapTab(freshPage, "archived");
  assert(
    freshPage._fetchCalls.length === 0,
    "fresh archived cache: switching tab must not issue any network request",
  );
  assert(
    freshPage.data.loading === false,
    "fresh archived cache: switching tab must not flip loading to true",
  );
  assert(
    freshPage.data.tab === "archived",
    "fresh archived cache: tab state should switch to archived",
  );
  assert(
    freshPage.data.conversations.length === 1 &&
      freshPage.data.conversations[0].id === "cached_arch",
    "fresh archived cache: cached archived conversations should render instantly",
  );

  // ── 场景 4：切回全部（缓存也新鲜）→ 仍零网络 ──
  tapTab(freshPage, "active");
  assert(
    freshPage._fetchCalls.length === 0,
    "fresh active cache: switching back must not issue any network request",
  );
  assert(
    freshPage.data.conversations.length === 1 &&
      freshPage.data.conversations[0].id === "cached_active",
    "fresh active cache: cached active conversations should render instantly",
  );

  // ── 场景 2：归档缓存过期（>60s TTL）→ 先渲染缓存，后台 silent 刷新 ──
  var stalePage = loadHistoryPage(
    { active: [], archived: [serverConv("srv_arch_new")] },
    {
      "history_cache_archived:student-a": cacheEnvelope(
        "cached_arch_stale",
        now - 120 * 1000,
      ),
    },
  );
  stalePage.setData({ loading: false, tab: "active" });
  tapTab(stalePage, "archived");
  assert(
    stalePage.data.loading === false,
    "stale archived cache: cached data should render without loading skeleton",
  );
  assert(
    stalePage.data.conversations.length === 1 &&
      stalePage.data.conversations[0].id === "cached_arch_stale",
    "stale archived cache: stale cache should still render instantly",
  );
  assert(
    stalePage._fetchCalls.length === 1 && stalePage._fetchCalls[0] === true,
    "stale archived cache: a single background refresh with archived=true should fire",
  );
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert(
    stalePage.data.conversations.length === 1 &&
      stalePage.data.conversations[0].id === "srv_arch_new",
    "stale archived cache: background refresh should replace stale data with server data",
  );
  var rewritten =
    stalePage._testStorage["history_cache_archived:student-a"].value;
  assert(
    rewritten.ts > now - 1000 &&
      rewritten.conversations[0].id === "srv_arch_new",
    "stale archived cache: refreshed data should be written back to the archived cache key",
  );

  // ── 场景 3：无归档缓存 → loading + fetch(archived=true) ──
  var coldPage = loadHistoryPage(
    { active: [], archived: [serverConv("srv_arch_cold")] },
    {},
    true, // deferred promise so we can observe the pending state
  );
  coldPage.setData({ loading: false, tab: "active" });
  tapTab(coldPage, "archived");
  assert(
    coldPage.data.loading === true,
    "no archived cache: switching tab should show loading while fetching",
  );
  assert(
    coldPage._fetchCalls.length === 1 && coldPage._fetchCalls[0] === true,
    "no archived cache: exactly one fetch with archived=true should fire",
  );
  coldPage._resolvePending();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert(
    coldPage.data.loading === false &&
      coldPage.data.conversations.length === 1 &&
      coldPage.data.conversations[0].id === "srv_arch_cold",
    "no archived cache: fetched archived conversations should render after resolve",
  );

  // ── 场景 5：串台竞态——归档静默刷新在途时切回全部，响应不得盖 UI ──
  // 陈旧归档缓存 + 新鲜全部缓存；deferred 挂住归档静默刷新。
  var racePage = loadHistoryPage(
    { active: [serverConv("srv_active_race")], archived: [serverConv("srv_arch_race")] },
    {
      "history_cache:student-a": cacheEnvelope("cached_active", now),
      "history_cache_archived:student-a": cacheEnvelope(
        "cached_arch_stale",
        now - 120 * 1000,
      ),
    },
    true, // deferred：挂住归档静默刷新，模拟慢响应
  );
  racePage.setData({ loading: false, tab: "active" });
  tapTab(racePage, "archived");
  assert(
    racePage._fetchCalls.length === 1 && racePage._fetchCalls[0] === true,
    "race: switching to archived with stale cache should fire one silent archived fetch",
  );
  assert(
    racePage.data.conversations.length === 1 &&
      racePage.data.conversations[0].id === "cached_arch_stale",
    "race: stale archived cache should render instantly while fetch is in flight",
  );
  tapTab(racePage, "active");
  assert(
    racePage._fetchCalls.length === 1,
    "race: switching back to active with fresh cache must not issue a new request",
  );
  assert(
    racePage.data.conversations[0].id === "cached_active",
    "race: active tab should render fresh active cache",
  );
  var activeGroupsBefore = racePage.data.groups;
  racePage._resolvePending(); // 归档响应此刻才到达
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert(
    racePage.data.tab === "active",
    "race: tab must still be active after late archived response",
  );
  assert(
    racePage.data.conversations.length === 1 &&
      racePage.data.conversations[0].id === "cached_active",
    "race: late archived response must NOT overwrite active tab conversations",
  );
  assert(
    racePage.data.totalCount === 1 &&
      racePage.data.groups === activeGroupsBefore,
    "race: late archived response must NOT overwrite active tab groups/totalCount",
  );
  var raceRewritten =
    racePage._testStorage["history_cache_archived:student-a"].value;
  assert(
    raceRewritten.ts > now - 1000 &&
      raceRewritten.conversations.length === 1 &&
      raceRewritten.conversations[0].id === "srv_arch_race",
    "race: archived cache must still be rewritten with the server snapshot",
  );

  // ── 场景 6：失败分支守卫——在途归档请求失败不得把 error 贴到全部 tab ──
  var raceErrPage = loadHistoryPage(
    { active: [], archived: [] },
    {
      "history_cache:student-a": cacheEnvelope("cached_active", now),
      "history_cache_archived:student-a": cacheEnvelope(
        "cached_arch_stale",
        now - 120 * 1000,
      ),
    },
    true,
  );
  raceErrPage.setData({ loading: false, tab: "active" });
  tapTab(raceErrPage, "archived");
  tapTab(raceErrPage, "active");
  raceErrPage._rejectPending(); // 归档静默刷新此刻失败
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert(
    raceErrPage.data.error === false,
    "race error: failed in-flight archived fetch must not paint error onto active tab",
  );
  assert(
    raceErrPage.data.conversations.length === 1 &&
      raceErrPage.data.conversations[0].id === "cached_active",
    "race error: active tab data must survive a failed archived fetch",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_history_archived_swr.js (" + pass + " assertions)");
})();
