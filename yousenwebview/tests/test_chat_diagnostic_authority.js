// 摸底测评「欢迎新同学」拦截弹窗的权威测试。
//
// 契约在 2026-07-28 的新手单一漏斗改版里翻转了：
//   改版前 = 新用户进「问鲁班」必被弹一次 8 分钟摸底；
//   改版后 = 新手引导单一权威 = first_run（注册后直接进），chat 页不再主动拦人。
// 所以本文件的主体断言从「必须弹」翻成「必须不弹、且连探测请求都不发」，
// 同时保留一组「把 DIAGNOSTIC_ENTRY_MODAL_ENABLED 置回 true 就整套恢复」的可逆性断言，
// 免得下线被误读成「实现被删了」。那组断言顺带守住 W3 修的两个 bug。

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
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

var MODAL_FLAG_OFF = "var DIAGNOSTIC_ENTRY_MODAL_ENABLED = false;";

function loadChatPage(overrides) {
  overrides = overrides || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );

  // 生产源码里这个常量必须是 false —— 它就是「弹窗已下线」的单一权威。
  assert(
    source.indexOf(MODAL_FLAG_OFF) !== -1,
    "chat.js must keep DIAGNOSTIC_ENTRY_MODAL_ENABLED = false (the single authority for 弹窗下线)",
  );

  if (overrides.forceModalEnabled) {
    var patched = source.replace(
      MODAL_FLAG_OFF,
      "var DIAGNOSTIC_ENTRY_MODAL_ENABLED = true;",
    );
    assert(
      patched !== source,
      "reversibility probe could not flip DIAGNOSTIC_ENTRY_MODAL_ENABLED (constant renamed?)",
    );
    source = patched;
  }

  var pageDef = null;
  var modalCalls = [];
  var navigateCalls = [];
  var profileCalls = 0;
  var storage = Object.assign({}, overrides.storage || {});
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        return raw;
      },
    },
    overrides.api || {},
  );
  var innerGetProfile =
    apiMock.getAssessmentProfile ||
    function () {
      return Promise.resolve({ score: 0, level: "", chapter_mastery: {} });
    };
  apiMock.getAssessmentProfile = function () {
    profileCalls += 1;
    return innerGetProfile.apply(null, arguments);
  };

  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") {
        return { getUserId: function () { return "user-1"; } };
      }
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") {
        return {
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
          getTimeGreeting: function () {
            return "晚上好";
          },
        };
      }
      if (request === "../../utils/logger") return { warn: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") {
        return { track: function () {}, trackOnce: function () {} };
      }
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") {
        return {
          assessment: function () {
            return "/packageDeeptutor/pages/assessment/assessment";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          isFeatureEnabled: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/analytics") return {};
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") return require(path.join(__dirname, "../packageDeeptutor/utils/learning-home-view-model.js"));
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      showModal: function (options) {
        modalCalls.push(options);
      },
      navigateTo: function (options) {
        navigateCalls.push(options);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}, {
      hasMessages: false,
    }),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    wx: sandbox.wx,
    storage: storage,
    modalCalls: modalCalls,
    navigateCalls: navigateCalls,
    profileCalls: function () {
      return profileCalls;
    },
  };
}

(async function main() {
  // ── 现行契约：弹窗已下线 ──────────────────────────────
  await run("diagnostic modal is retired for brand new users", async function () {
    var loaded = loadChatPage();

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();

    assert(loaded.modalCalls.length === 0, "retired diagnostic modal must not intercept new users");
    assert(
      loaded.profileCalls() === 0,
      "retired modal must not even probe getAssessmentProfile on every onShow",
    );
    assert(
      loaded.storage["diagnostic_skipped:user-1"] === undefined,
      "retired modal must not write suppression keys it no longer needs",
    );
  });

  await run("backend assessment signal still results in no modal", async function () {
    var loaded = loadChatPage({
      api: {
        getAssessmentProfile: function () {
          return Promise.resolve({
            level: "beginner",
            chapter_mastery: {
              "建筑构造": { name: "建筑构造", mastery: 32 },
            },
          });
        },
      },
    });

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();

    assert(loaded.modalCalls.length === 0, "diagnostic modal should be suppressed by backend assessment signal");
  });

  await run("first-run learner-state completion still results in no modal", async function () {
    var loaded = loadChatPage({
      api: {
        getAssessmentProfile: function () {
          return Promise.resolve({
            level: "",
            chapter_mastery: {},
            diagnostic_sources: {
              first_run: {
                completed: true,
                source: "learner_state.learning_preferences.first_run",
              },
            },
          });
        },
      },
    });

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();

    assert(loaded.modalCalls.length === 0, "canonical first-run completion should prevent a second onboarding prompt");
  });

  // ── 可逆性 + W3 的两个 bug 修复（把常量置回 true 时才生效）────────
  await run("flipping the constant back restores the whole modal path", async function () {
    var loaded = loadChatPage({ forceModalEnabled: true });

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();

    assert(loaded.modalCalls.length === 1, "one flipped constant must restore the modal end to end");
    assert(loaded.profileCalls() === 1, "restored path still probes the backend assessment profile once");
  });

  await run("[FIX-DIAG-1] confirm branch writes the suppression key too", async function () {
    var loaded = loadChatPage({ forceModalEnabled: true });

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();
    assert(loaded.modalCalls.length === 1, "precondition: modal shown once");

    loaded.modalCalls[0].success({ confirm: true });

    assert(
      loaded.storage["diagnostic_skipped:user-1"] === true,
      "confirm branch must write the suppression key too (弹过就算数)",
    );
    assert(loaded.navigateCalls.length === 1, "confirm branch still navigates to assessment");
  });

  await run("[FIX-DIAG-2] same-visit re-entry does not double-show the modal", async function () {
    var loaded = loadChatPage({ forceModalEnabled: true });

    // 抑制键写在网络回调里，同一 visit 内第二次 onShow 会在它落盘前再进来一次。
    var first = Promise.resolve(loaded.page._checkDiagnostic());
    var second = Promise.resolve(loaded.page._checkDiagnostic());
    await first;
    await second;
    await flushPromises();

    assert(loaded.modalCalls.length === 1, "in-flight guard must collapse concurrent checks into one modal");
    assert(loaded.profileCalls() === 1, "in-flight guard must also collapse the duplicate probe");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_chat_diagnostic_authority.js (" + pass + " assertions)");
})();
