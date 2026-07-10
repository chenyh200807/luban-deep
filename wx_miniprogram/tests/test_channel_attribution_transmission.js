// 渠道归因接缝测试（客户端半边）：
// 加载真实 utils/api.js，storage 中放 reg_attribution={ch,scene}，
// 断言 wxLoginWithPhone / bindPhone 通过 wx.request 发出的 body 字段名与值。
// 输出 SERIALIZED_LOGIN_BODY= 原文——后端接缝测试
// tests/api/test_mobile_router.py::test_wechat_login_client_wire_body_persists_channel_attribution
// 用这份原文打真实 FastAPI app，闭合“客户端序列化 ↔ router 请求模型字段名”接缝。
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

function loadApiModule(storageState, capture) {
  var source = fs.readFileSync(path.join(__dirname, "../utils/api.js"), "utf8");
  var sandbox = {
    console: {
      warn: function () {},
      log: function () {},
      error: console.error,
    },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
    getApp: function () {
      return { globalData: {} };
    },
    require: function (request) {
      if (request === "./auth") {
        return {
          getToken: function () {
            return "";
          },
          clearToken: function () {},
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "https://api.example.com";
          },
          getBaseUrlCandidates: function () {
            return ["https://api.example.com"];
          },
          rememberWorkingBaseUrl: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storageState[key];
      },
      setStorageSync: function (key, value) {
        storageState[key] = value;
      },
      request: function (options) {
        capture.options = options;
      },
      reLaunch: function () {},
    },
    module: { exports: {} },
    exports: {},
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "utils/api.js" });
  return sandbox.module.exports;
}

// ── case 1: storage 有推广归因 → wxLoginWithPhone body 带 channel/scene ──
(function () {
  var storage = { reg_attribution: { ch: "test1", scene: "1047" } };
  var capture = {};
  var api = loadApiModule(storage, capture);

  api.wxLoginWithPhone("wx-code", "phone-code-123");

  var data = capture.options && capture.options.data;
  assert(!!data, "wxLoginWithPhone issues a wx.request with data");
  assert(data.code === "wx-code", "body.code carries wx login code");
  assert(data.phone_code === "phone-code-123", "body.phone_code carries phone code");
  assert(data.channel === "test1", "body.channel carries stored ch value");
  assert(data.scene === "1047", "body.scene carries stored scene value");
  assert(
    capture.options.url === "https://api.example.com/api/v1/wechat/mp/login",
    "request targets /api/v1/wechat/mp/login",
  );
  // 后端接缝测试消费的序列化原文（wx.request 以 JSON 发送 data）
  console.log("SERIALIZED_LOGIN_BODY=" + JSON.stringify(data));
})();

// ── case 2: bindPhone body 同样带 channel/scene ──
(function () {
  var storage = { reg_attribution: { ch: "test1", scene: "1047" } };
  var capture = {};
  var api = loadApiModule(storage, capture);

  api.bindPhone("phone-code-456");

  var data = capture.options && capture.options.data;
  assert(!!data, "bindPhone issues a wx.request with data");
  assert(data.phone_code === "phone-code-456", "bind body.phone_code carries phone code");
  assert(data.channel === "test1", "bind body.channel carries stored ch value");
  assert(data.scene === "1047", "bind body.scene carries stored scene value");
  console.log("SERIALIZED_BIND_BODY=" + JSON.stringify(data));
})();

// ── case 3: 无归因（organic 冷启动）→ 字段仍在但为空串，不炸 ──
(function () {
  var storage = {};
  var capture = {};
  var api = loadApiModule(storage, capture);

  api.wxLoginWithPhone("wx-code", "phone-code-123");

  var data = capture.options && capture.options.data;
  assert(!!data, "organic login still issues request");
  assert(data.channel === "", "organic body.channel is empty string");
  assert(data.scene === "", "organic body.scene is empty string");
})();

// ── case 4: getStorageSync 抛异常 → regAttribution 兜底空值，不阻塞登录 ──
(function () {
  var capture = {};
  var api = loadApiModule(
    Object.create(null, {
      reg_attribution: {
        get: function () {
          throw new Error("storage broken");
        },
      },
    }),
    capture,
  );

  api.wxLoginWithPhone("wx-code", "phone-code-123");

  var data = capture.options && capture.options.data;
  assert(!!data, "login proceeds when storage read throws");
  assert(data.channel === "", "broken storage falls back to empty channel");
})();

if (fail > 0) {
  console.error(errors.join("\n"));
  console.error("FAIL test_channel_attribution_transmission.js");
  process.exit(1);
}
console.log(
  "PASS test_channel_attribution_transmission.js (" + pass + " assertions)",
);
