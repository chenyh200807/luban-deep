var fs = require("fs");
var path = require("path");
var vm = require("vm");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function source(relative) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", relative), "utf8");
}

var sensitiveConsumers = [
  "pages/history/history.js",
  "pages/luban/gauntlet/gauntlet.js",
  "pages/luban/seethrough/seethrough.js",
  "pages/attempt-detail/attempt-detail.js",
  "pages/mistake-book/mistake-book.js",
  "pages/luban/errorbank/errorbank.js",
  "utils/first-run-entry.js",
];

sensitiveConsumers.forEach(function (relative) {
  assert(
    !/wx\.(?:get|set|remove)StorageSync/.test(source(relative)),
    relative + " must not bypass the owner-scoped storage authority",
  );
});

assert(
  source("pages/report/report.js").indexOf(
    "auth.readOwnerStorage(ASSESSMENT_PENDING_TRAINING_ACTION_KEY)",
  ) >= 0 &&
    source("pages/report/report.js").indexOf(
      "auth.writeOwnerStorage(cacheKey",
    ) >= 0,
  "report training intent and attempt preview must be owner-scoped",
);
assert(
  source("pages/assessment/assessment.js").indexOf(
    'auth.writeOwnerStorage("deeptutor.report.pendingTrainingAction", intent)',
  ) >= 0 &&
    source("pages/assessment/assessment.js").indexOf(
      'setStorageSync("diagnostic_completed"',
    ) < 0,
  "assessment must hand off learner intent through owner storage and keep no global done mirror",
);
assert(
  source("pages/profile/profile.js").indexOf(
    'auth.readOwnerStorage("local_avatar_path")',
  ) >= 0 &&
    source("pages/profile/profile.js").indexOf(
      'auth.writeOwnerStorage("local_avatar_path"',
    ) >= 0,
  "local avatar paths must not cross account boundaries",
);

var gauntletSource = source("pages/luban/gauntlet/gauntlet.js");
var gauntletViewModel = require("../packageDeeptutor/utils/gauntlet-view-model");
var storage = {};
var currentUser = "student-a";
var pageDefinition = null;
var auth = {
  readOwnerStorage: function (key) {
    var envelope = storage[key + ":" + currentUser];
    return envelope && envelope.ownerId === currentUser ? envelope.value : null;
  },
  writeOwnerStorage: function (key, value) {
    storage[key + ":" + currentUser] = { ownerId: currentUser, value: value };
    return true;
  },
};

vm.runInNewContext(gauntletSource, {
  console: console,
  Date: Date,
  require: function (request) {
    if (request === "../../../utils/auth") return auth;
    if (request === "../../../utils/api") return {};
    if (request === "../../../utils/surface-telemetry") {
      return { trackProductBehavior: function () {} };
    }
    if (request === "../../../utils/helpers") {
      return { isDark: function () { return false; } };
    }
    if (request === "../../../utils/gauntlet-view-model") return gauntletViewModel;
    throw new Error("unexpected require: " + request);
  },
  wx: { getSystemInfoSync: function () { return {}; } },
  Page: function (definition) { pageDefinition = definition; },
}, { filename: "gauntlet.js" });

function newGauntletPage() {
  var page = Object.assign({}, pageDefinition);
  page.data = Object.assign({}, pageDefinition.data);
  page.setData = function (patch) { this.data = Object.assign({}, this.data, patch); };
  page._loadItems = function () {};
  return page;
}

var pageA = newGauntletPage();
pageA.onLoad({ pack_id: "F16", title: "防水" });
pageA.setData({ draftText: "A的屋面防水作答", step: 2 });
pageA._saveDraft();

currentUser = "student-b";
var pageB = newGauntletPage();
pageB.onLoad({ pack_id: "F16", title: "防水" });
assert(pageB.data.draftText === "", "student B must not restore student A's gauntlet draft");

currentUser = "student-a";
var pageAReturn = newGauntletPage();
pageAReturn.onLoad({ pack_id: "F16", title: "防水" });
assert(
  pageAReturn.data.draftText === "A的屋面防水作答" && pageAReturn.data.step === 2,
  "student A should still recover their own gauntlet draft",
);

console.log("PASS test_owner_scoped_learning_storage.js");
