// node contract 测试:getLubanRetestItems 的 mode 参数与向后兼容。
// 断言:forward/review 归一进 URL query;旧 3 参调用(opts 放第 3 位)不被误当 mode。
// 运行: node yousenwebview/tests/test_api_luban_retest_mode.js
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];
function assert(cond, msg) {
  if (cond) { pass++; return; }
  fail++;
  errors.push("FAIL: " + msg);
}

function loadApiModule() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
    "utf8",
  );
  var pendingRequests = [];
  var sandbox = {
    console: { warn: function () {}, log: function () {}, error: function () {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
    require: function (request) {
      if (request === "./auth") {
        return { getToken: function () { return "token"; }, clearToken: function () {} };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () { return "https://api.example.com"; },
          getBaseUrlCandidates: function () { return ["https://api.example.com"]; },
          rememberWorkingBaseUrl: function () {},
        };
      }
      if (request === "./runtime") {
        return { redirectToLogin: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: { request: function (options) { pendingRequests.push(options); } },
    module: { exports: {} },
    exports: {},
  };
  vm.runInNewContext(source, sandbox, { filename: "packageDeeptutor/utils/api.js" });
  return { api: sandbox.module.exports, pendingRequests: pendingRequests };
}

function urlOf(loaded) {
  return (loaded.pendingRequests[0] && loaded.pendingRequests[0].url) || "";
}

// forward 模式进 query
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5, "forward");
  var url = urlOf(loaded);
  assert(url.indexOf("/luban/lessons/S05/retest-items") >= 0, "路径应为 retest-items 复用端点, got " + url);
  assert(url.indexOf("mode=forward") >= 0, "forward 模式应进 query, got " + url);
  assert(url.indexOf("limit=5") >= 0, "limit 应保留, got " + url);
})();

// 默认 review
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5);
  var url = urlOf(loaded);
  assert(url.indexOf("mode=review") >= 0, "缺省应为 review, got " + url);
})();

// 未识别模式归一 review(builder 侧也归一,双保险)
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5, "banana");
  assert(urlOf(loaded).indexOf("mode=review") >= 0, "未识别模式归一 review");
})();

// 向后兼容:历史调用把 opts 放第 3 位,不得被当成 mode
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 1, { silent: true });
  var url = urlOf(loaded);
  assert(url.indexOf("mode=review") >= 0, "第 3 位对象=opts 时 mode 应归 review, got " + url);
  assert(url.indexOf("limit=1") >= 0, "limit=1 应保留, got " + url);
})();

// 同 pack 的第二集必须进 detail query；练习/进度仍由 pack_id 归属。
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanLessonDetail("D14", { episode: 2, silent: true });
  var url = urlOf(loaded);
  assert(url.indexOf("/luban/lessons/D14?episode=2") >= 0, "第二集必须直达 lesson detail, got " + url);
  assert(loaded.pendingRequests[0].data.episode === undefined, "episode 应在 URL，不应成为 GET body");
})();

// 错后当场确认: forward 场 confirmFacts 进 query(去空/去重限 5, 逗号连接)。
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5, "forward", {
    confirmFacts: ["fact-a", " ", "fact-b"],
  });
  var url = urlOf(loaded);
  assert(
    url.indexOf("confirm_facts=fact-a%2Cfact-b") >= 0,
    "forward 场 confirmFacts 应编码进 query, got " + url,
  );
})();

// review 场绝不传 confirm_facts(消费点1 仅 forward)。
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5, "review", {
    probeId: "probe-1",
    confirmFacts: ["fact-a"],
  });
  var url = urlOf(loaded);
  assert(url.indexOf("confirm_facts=") === -1, "review 场不得带 confirm_facts, got " + url);
})();

// 空 confirmFacts 不产生 query 参数(现行为)。
(function () {
  var loaded = loadApiModule();
  loaded.api.getLubanRetestItems("S05", 5, "forward", { confirmFacts: [] });
  assert(urlOf(loaded).indexOf("confirm_facts=") === -1, "空 confirmFacts 不得进 query");
})();

if (fail > 0) {
  console.error(errors.join("\n"));
  console.error("\napi-luban-retest-mode: " + pass + " passed, " + fail + " FAILED");
  process.exit(1);
}
console.log("api-luban-retest-mode: " + pass + " passed");
