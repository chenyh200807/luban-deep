// Run: node yousenwebview/tests/test_learn_core_surface_contract.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
}

var learnJs = read("packageDeeptutor/pages/learn/learn.js");
var learnWxml = read("packageDeeptutor/pages/learn/learn.wxml");
var learnVm = read("packageDeeptutor/utils/learn-view-model.js");

assert(learnWxml.indexOf('bindtap="goTodayTask"') >= 0, "today task must own the primary action");
assert(
  learnWxml.indexOf("firstRunState === 'hidden' && !supplyError && vm.todayTask") >= 0,
  "first-run and canonical today task must be mutually exclusive",
);
assert(
  learnWxml.indexOf("!supplyError && firstRunState !== 'hidden'") >= 0 &&
    (learnWxml.match(/bindtap="openFirstRun"/g) || []).length === 1,
  "first-run state must expose exactly one primary journey CTA",
);
assert.strictEqual(
  (learnWxml.match(/bindtap="goTodayTask"/g) || []).length,
  1,
  "normal state must expose exactly one canonical task CTA",
);
assert.strictEqual(learnWxml.indexOf("goSwitchPractice"), -1, "learning home must not expose a secondary practice CTA");
assert.strictEqual(learnWxml.indexOf("goReview"), -1, "learning home must not expose an independent review card");
assert.strictEqual(learnWxml.indexOf("vm.dueCount"), -1, "due state must be folded into todayTask");
assert.strictEqual(learnWxml.indexOf("mastery_score"), -1, "learning home must not render pseudo-precise mastery");
assert(
  learnWxml.indexOf("近 3 天有效作答") >= 0 &&
    learnWxml.indexOf("{{vm.stats.recent_practice || 0}} 道") >= 0,
  "recent_three_done must be labeled as answer count rather than practice sessions",
);

["goReview", "goSwitchPractice", "goSeethrough", "route.lubanReview", "getLubanSeethroughLibrary", "F16"].forEach(function (needle) {
  assert.strictEqual(learnJs.indexOf(needle), -1, "learn.js must not retain first-class legacy surface: " + needle);
});
["secondaryCta", "mastery_score", "_seethroughSet", '"seethrough"'].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "view model must not retain legacy decision: " + needle);
});

var pageDef = null;
var navigations = [];
vm.runInNewContext(learnJs, {
  console: console,
  Promise: Promise,
  require: function (request) {
    if (request === "../../utils/route") {
      return {
        lubanStation: function (packId) { return "/station?pack_id=" + packId; },
      };
    }
    if (request === "../../utils/learn-view-model") return { buildLearnViewModel: function () { return {}; } };
    return {};
  },
  wx: { navigateTo: function (payload) { navigations.push(payload.url); } },
  Page: function (definition) { pageDef = definition; },
}, { filename: "packageDeeptutor/pages/learn/learn.js" });

function navigate(task) {
  var page = {
    data: { vm: { todayTask: task } },
    _navTo: pageDef._navTo,
  };
  pageDef.goTodayTask.call(page);
  return navigations.pop();
}

assert.strictEqual(
  navigate({ action_kind: "lesson", pack_id: "N01" }),
  "/station?pack_id=N01",
  "recommended learning task should enter the generic station route",
);
assert.strictEqual(
  navigate({ action_kind: "retest", practice_kind: "retest", pack_id: "N01", mode: "review", probe_id: "probe-1" }),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=N01&mode=review&training_intent_id=&probe_id=probe-1",
  "due task should enter the shared retest route in review mode",
);
assert.strictEqual(
  navigate({ action_kind: "retest", practice_kind: "retest", pack_id: "S05", mode: "forward", training_intent_id: "intent-1" }),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=S05&mode=forward&training_intent_id=intent-1&probe_id=",
  "post-lesson task should enter the same retest route in forward mode",
);

console.log("PASS test_learn_core_surface_contract.js");
