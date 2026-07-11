// node contract 测试:Task C 入口收权落地翻转(护栏1=默认关 host 不变;护栏2=仅翻 chat→learn)。
// 运行: node yousenwebview/tests/test_double_wheel_landing.js
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0, fail = 0, errors = [];
function assert(cond, msg) { if (cond) { pass++; return; } fail++; errors.push("FAIL: " + msg); }

// 以指定 host 运行时 flags 加载 flags.js(其余依赖最小 mock)。
function loadFlags(runtimeFlags) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/flags.js"), "utf8");
  var sandbox = {
    console: console,
    require: function (req) {
      if (req === "./route") {
        return { chat: function () { return "/pages/chat/chat"; },
                 learn: function () { return "/pages/learn/learn"; },
                 history: function () { return "/pages/history/history"; },
                 report: function () { return "/pages/report/report"; },
                 profile: function () { return "/pages/profile/profile"; },
                 assessment: function () { return "/pages/assessment/assessment"; },
                 resolve: function (p) { return "/" + p; } };
      }
      if (req === "./host-runtime") {
        return { getWorkspaceFlags: function () { return runtimeFlags; } };
      }
      if (req === "./runtime") {
        return { clearWorkspaceBackIfMatches: function () {} };
      }
      throw new Error("unexpected require: " + req);
    },
    module: { exports: {} },
    exports: {},
  };
  vm.runInNewContext(source, sandbox, { filename: "flags.js" });
  return sandbox.module.exports;
}

var CHAT = "/packageDeeptutor/pages/chat/chat?entry_source=scan";
var LEARN = "/packageDeeptutor/pages/learn/learn";
var REPORT_DEEP = "/packageDeeptutor/pages/report/report?id=7";

// 护栏1:默认关(runtime 无此 flag)→ 落地目标原样返回,host 逐字节不变。
(function () {
  var flags = loadFlags(null);
  assert(flags.shouldLandOnDoubleWheel() === false, "默认必须关");
  assert(flags.resolvePostAuthLanding(CHAT, LEARN) === CHAT, "默认关:chat 目标原样返回(host 不变)");
  assert(flags.resolvePostAuthLanding(REPORT_DEEP, LEARN) === REPORT_DEEP, "默认关:深链原样");
})();

// flag 开(host 运行时下发)→ 仅 chat 目标翻到 learn;其它显式深链不动(护栏2)。
(function () {
  var flags = loadFlags({ doubleWheelLandingEnabled: true });
  assert(flags.shouldLandOnDoubleWheel() === true, "flag 开");
  assert(flags.resolvePostAuthLanding(CHAT, LEARN) === LEARN, "flag 开:chat→learn 翻转");
  assert(flags.resolvePostAuthLanding(REPORT_DEEP, LEARN) === REPORT_DEEP, "flag 开:非 chat 深链不动(不 strand)");
  assert(flags.resolvePostAuthLanding("", LEARN) === "", "flag 开:空目标不误翻");
})();

// 非布尔真值不误开(严格 === true)。
(function () {
  var flags = loadFlags({ doubleWheelLandingEnabled: "true" });
  assert(flags.shouldLandOnDoubleWheel() === false, "字符串 'true' 不算开(严格 === true 防误开)");
})();

if (fail > 0) {
  console.error(errors.join("\n"));
  console.error("\ndouble-wheel-landing: " + pass + " passed, " + fail + " FAILED");
  process.exit(1);
}
console.log("double-wheel-landing: " + pass + " passed");
