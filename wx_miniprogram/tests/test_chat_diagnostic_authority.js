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

function loadChatPage(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var modalCalls = [];
  var storage = Object.assign({}, (overrides && overrides.storage) || {});
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        return raw;
      },
      getAssessmentProfile: function () {
        return Promise.resolve({ score: 0, level: "", chapter_mastery: {} });
      },
    },
    (overrides && overrides.api) || {},
  );
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    getApp: function () {
      return {
        globalData: {},
      };
    },
    require: function (request) {
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/surface-telemetry") return {};
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
      navigateTo: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/pages/chat/chat.js",
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
    storage: storage,
    modalCalls: modalCalls,
  };
}

(async function main() {
  await run("wx chat diagnostic should not show modal when backend assessment already exists", async function () {
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

    assert(loaded.modalCalls.length === 0, "wx diagnostic modal should be suppressed by backend assessment signal");
    assert(loaded.storage.diagnostic_completed === true, "wx backend assessment signal should warm local completed cache");
  });

  await run("wx chat diagnostic should still show modal when backend assessment is empty", async function () {
    var loaded = loadChatPage();

    await Promise.resolve(loaded.page._checkDiagnostic());
    await flushPromises();

    assert(loaded.modalCalls.length === 1, "wx diagnostic modal should still show for truly new users");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_chat_diagnostic_authority.js (" + pass + " assertions)");
})();
