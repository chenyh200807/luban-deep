// test_profile_route_card_cache.js — 我的页路线卡必须复用学情统一快照缓存
//
// 契约（缓存秒渲染 + 始终静默刷新；对抗 review 证伪了 fresh-skip 门后修订）：
// (a) 缓存命中（<= SNAPSHOT_MAX_AGE_MS）→ 先同步渲出缓存 routeCard（秒渲染），
//     同时**仍然**发起 getLearningReport + getLubanLessons 静默刷新，网络回来
//     覆盖缓存卡——不存在"新鲜即免网络"分支（FRESH_MAX_AGE_MS 已从基座删除）；
// (b) 无缓存 → 照旧走网络路径拉 learning-report + lessons；
// (c) 静默刷新失败不把已渲出的缓存卡抹回 null（保守降级）；
// (d) 异步返回时用户已切换 → 不 setData（守卫，跟随 report 页惯例）；
//     profile 只读缓存、绝不写（三元组不全，写入会污染 learn/report 快照消费）。

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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push(
      "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
    );
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

var SNAPSHOT_MAX_AGE_MS = 30 * 60 * 1000;

// 与 report-cache envelope 契约一致：snapshot.report / snapshot.lessons
// 是 raw unwrapped payload（learn/report 页网络成功后写入）。
function makeSnapshot(litPackIds) {
  var packs = {};
  (litPackIds || []).forEach(function (id) {
    packs[id] = { lifecycle_state: "practiced" };
  });
  return {
    report: { user_id: "user-1", pack_lifecycle: { packs: packs } },
    lessons: { lessons: [], pack_universe: 40 },
  };
}

function loadProfilePage(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = {
    getLearningReport: 0,
    getLubanLessons: 0,
    cacheReads: [],
    cacheWrites: 0,
  };
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        if (
          raw &&
          typeof raw === "object" &&
          raw.data &&
          typeof raw.data === "object"
        ) {
          return raw.data;
        }
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({ username: "chenyh2008", points: 0 });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 88 });
      },
      getUsage: function () {
        return Promise.resolve({ windows: [] });
      },
      getLedger: function () {
        return Promise.resolve({ entries: [] });
      },
      getLearningReport: function () {
        return Promise.reject(new Error("silent refresh failed"));
      },
      getLubanLessons: function () {
        return Promise.reject(new Error("silent refresh failed"));
      },
      updateSettings: function () {
        return Promise.resolve({});
      },
    },
    (overrides && overrides.api) || {},
  );
  // 计数放在 override 合并之后统一包一层，场景自带的 api override 也被计入。
  ["getLearningReport", "getLubanLessons"].forEach(function (name) {
    var inner = apiMock[name];
    apiMock[name] = function () {
      calls[name] += 1;
      return inner.apply(this, arguments);
    };
  });
  var authState = { userId: "user-1", loggedIn: true };
  // 镜像基座 report-cache 现行导出面：read/readWithMeta/write/writeIfFresher/
  // clear/SNAPSHOT_MAX_AGE_MS——刻意不含 FRESH_MAX_AGE_MS（已删）。
  var reportCacheMock = {
    read: function (userId, maxAgeMs) {
      calls.cacheReads.push({ userId: userId, maxAgeMs: maxAgeMs });
      var hit = overrides && overrides.cacheHit;
      return hit ? hit.snapshot : null;
    },
    readWithMeta: function (userId, maxAgeMs) {
      calls.cacheReads.push({ userId: userId, maxAgeMs: maxAgeMs });
      var hit = overrides && overrides.cacheHit;
      return hit ? { snapshot: hit.snapshot, ageMs: hit.ageMs } : null;
    },
    // profile 是只读消费者；任何 write/writeIfFresher/clear 调用都是 envelope 污染。
    write: function () {
      calls.cacheWrites += 1;
      return true;
    },
    writeIfFresher: function () {
      calls.cacheWrites += 1;
      return true;
    },
    clear: function () {
      calls.cacheWrites += 1;
      return true;
    },
    SNAPSHOT_MAX_AGE_MS: SNAPSHOT_MAX_AGE_MS,
  };
  var helpersMock = {
    getWindowInfo: function () {
      return { statusBarHeight: 20 };
    },
    isDark: function () {
      return false;
    },
    isDarkOr: function () {
      return false;
    },
    syncTabBar: function () {},
    vibrate: function () {},
  };
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return authState.loggedIn;
          },
          getUserId: function () {
            return authState.userId;
          },
        };
      }
      if (request === "../../utils/report-cache") return reportCacheMock;
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/runtime") {
        return {
          getWorkspaceBack: function () {
            return null;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          profile: function () {
            return "/packageDeeptutor/pages/profile/profile";
          },
          learn: function () {
            return "/packageDeeptutor/pages/learn/learn";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          getWorkspaceFlags: function () {
            return {};
          },
          ensureFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return false;
          },
        };
      }
      if (request === "../../utils/learn-view-model") {
        // 纯函数视图模型（点亮判定单一权威），直接用真模块
        return require("../packageDeeptutor/utils/learn-view-model");
      }
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
      showToast: function () {},
      showModal: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/profile/profile.js",
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

  return { page: page, calls: calls, authState: authState };
}

(async function main() {
  await run(
    "(a) cache hit renders instantly AND still silently refreshes over network",
    async function () {
      var loaded = loadProfilePage({
        cacheHit: { snapshot: makeSnapshot(["F16"]), ageMs: 5 * 1000 },
        api: {
          getLearningReport: function () {
            return Promise.resolve({
              data: makeSnapshot(["F16", "N01"]).report,
            });
          },
          getLubanLessons: function () {
            return Promise.resolve({ data: { lessons: [], pack_universe: 40 } });
          },
        },
      });

      loaded.page.onLoad();
      loaded.page.onShow();

      // 缓存命中是同步渲染，不需要等网络
      assert(
        loaded.page.data.routeCard &&
          loaded.page.data.routeCard.label === "路线 1 / 40 站已点亮",
        "cache hit should render routeCard synchronously from snapshot",
      );

      await flushPromises();
      await flushPromises();

      // 秒渲染之外必须仍发起静默刷新——60s 内其他 tab 的学习动作
      // 没有后台纠正通道，"新鲜即免网络"会吞掉它（对抗 review 结论）。
      assert(
        loaded.calls.getLearningReport === 1,
        "cache hit must STILL call getLearningReport once (got " +
          loaded.calls.getLearningReport +
          ")",
      );
      assert(
        loaded.calls.getLubanLessons === 1,
        "cache hit must STILL call getLubanLessons once",
      );
      assert(
        loaded.page.data.routeCard &&
          loaded.page.data.routeCard.label === "路线 2 / 40 站已点亮",
        "network refresh result must override the cached routeCard",
      );
      assert(
        loaded.calls.cacheReads.length === 1 &&
          loaded.calls.cacheReads[0].userId === "user-1" &&
          loaded.calls.cacheReads[0].maxAgeMs === SNAPSHOT_MAX_AGE_MS,
        "cache read must use current userId with SNAPSHOT_MAX_AGE_MS window",
      );
      assert(
        loaded.calls.cacheWrites === 0,
        "profile must never write the report cache (envelope integrity)",
      );
    },
  );

  await run(
    "(a2) profile.js no longer references the deleted FRESH_MAX_AGE_MS gate",
    async function () {
      var source = fs.readFileSync(
        path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
        "utf8",
      );
      assert(
        source.indexOf("FRESH_MAX_AGE_MS") === -1,
        "profile.js must not reference FRESH_MAX_AGE_MS (deleted from report-cache)",
      );
    },
  );

  await run("(b) cache miss falls back to network path", async function () {
    var loaded = loadProfilePage({
      cacheHit: null,
      api: {
        getLearningReport: function () {
          return Promise.resolve({ data: makeSnapshot(["F16", "N01"]).report });
        },
        getLubanLessons: function () {
          return Promise.resolve({ data: { lessons: [], pack_universe: 40 } });
        },
      },
    });

    loaded.page.onLoad();
    loaded.page.onShow();
    assert(
      loaded.page.data.routeCard === null,
      "no cache means no synchronous routeCard",
    );

    await flushPromises();
    await flushPromises();

    assert(
      loaded.page.data.routeCard &&
        loaded.page.data.routeCard.label === "路线 2 / 40 站已点亮",
      "cache miss should hydrate routeCard from network payloads",
    );
    assert(
      loaded.calls.cacheWrites === 0,
      "network success on profile must not write the report cache",
    );
  });

  await run(
    "(c) stale cache renders immediately then network refresh overrides",
    async function () {
      var loaded = loadProfilePage({
        cacheHit: { snapshot: makeSnapshot(["F16"]), ageMs: 5 * 60 * 1000 },
        api: {
          getLearningReport: function () {
            return Promise.resolve({
              data: makeSnapshot(["F16", "N01", "C01"]).report,
            });
          },
          getLubanLessons: function () {
            return Promise.resolve({ data: { lessons: [], pack_universe: 40 } });
          },
        },
      });

      loaded.page.onLoad();
      loaded.page.onShow();

      assert(
        loaded.page.data.routeCard &&
          loaded.page.data.routeCard.label === "路线 1 / 40 站已点亮",
        "stale cache should render cached routeCard synchronously first",
      );

      await flushPromises();
      await flushPromises();

      assert(
        loaded.page.data.routeCard &&
          loaded.page.data.routeCard.label === "路线 3 / 40 站已点亮",
        "stale cache should be refreshed by silent network fetch",
      );
    },
  );

  await run(
    "(c2) stale cache survives silent refresh failure (no wipe to null)",
    async function () {
      var loaded = loadProfilePage({
        cacheHit: { snapshot: makeSnapshot(["F16"]), ageMs: 5 * 60 * 1000 },
        // 默认 api mock：getLearningReport/getLubanLessons 均 reject
      });

      loaded.page.onLoad();
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        loaded.page.data.routeCard &&
          loaded.page.data.routeCard.label === "路线 1 / 40 站已点亮",
        "silent refresh failure must not wipe cached routeCard back to null",
      );
      assert(
        loaded.calls.getLearningReport === 1,
        "stale cache should still trigger one silent network refresh",
      );
    },
  );

  await run(
    "(d) network result is dropped when user switched mid-flight",
    async function () {
      var loaded = loadProfilePage({
        cacheHit: null,
        api: {
          getLearningReport: function () {
            return Promise.resolve({ data: makeSnapshot(["F16"]).report });
          },
          getLubanLessons: function () {
            return Promise.resolve({ data: { lessons: [], pack_universe: 40 } });
          },
        },
      });

      loaded.page.onLoad();
      loaded.page.onShow();
      // 异步返回前用户已切换
      loaded.authState.userId = "user-2";
      await flushPromises();
      await flushPromises();

      assert(
        loaded.page.data.routeCard === null,
        "stale-user network result must not setData routeCard",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_profile_route_card_cache.js (" + pass + " assertions)");
})();
