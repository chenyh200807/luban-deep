// Run: node yousenwebview/tests/test_first_run_native_journey.js
var assert = require("assert");
var crypto = require("crypto");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flushPromises() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(function (key) {
      return JSON.stringify(key) + ":" + canonicalJson(value[key]);
    }).join(",") + "}";
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return crypto.createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function loadPage(options) {
  options = options || {};
  var pagePath = path.join(__dirname, "../packageDeeptutor/pages/first-run/first-run.js");
  var scriptData = require(path.join(__dirname, "../packageDeeptutor/pages/first-run/script-data.js"));
  var source = fs.readFileSync(pagePath, "utf8");
  var pageDef = null;
  var calls = {
    completeFirstRun: [],
    reLaunch: [],
    writeCheckpoint: [],
    pending: [],
    clearPending: 0,
    clearCheckpoint: 0,
    done: [],
  };
  var entryMock = {
    readCheckpoint: function () { return options.checkpoint || null; },
    writeCheckpoint: function (userId, payload) { calls.writeCheckpoint.push({ userId: userId, payload: payload }); },
    clearCheckpoint: function () { calls.clearCheckpoint++; },
    savePendingSync: function (userId, payload) { calls.pending.push({ userId: userId, payload: payload }); },
    clearPendingSync: function () { calls.clearPending++; },
    markDone: function (userId, payload) { calls.done.push({ userId: userId, payload: payload }); },
  };
  var apiMock = {
    completeFirstRun: function (payload) {
      calls.completeFirstRun.push(payload);
      if (options.rejectSync) return Promise.reject(options.rejectSync);
      return Promise.resolve({
        sync_status: "synced",
        score: { correct_count: 3, question_count: 4 },
        home_projection: { today_focus: { title: "今日焦点：屋面卷材起鼓" } },
      });
    },
  };
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "./script-data") return scriptData;
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/auth") return { getUserId: function () { return "user-1"; } };
      if (request === "../../utils/route") {
        return { resolve: function (value) { return "/packageDeeptutor/" + value; } };
      }
      if (request === "../../utils/helpers") {
        return { getWindowInfo: function () { return { statusBarHeight: 44 }; } };
      }
      if (request === "../../utils/first-run-entry") return entryMock;
      if (request === "../../utils/surface-telemetry") return { trackProductBehavior: function () {} };
      if (request === "../../utils/subscribe-message") {
        return { requestNextDayRetestAuthorization: function () { return Promise.resolve({ status: "accepted" }); } };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      pageScrollTo: function () {},
      reLaunch: function (payload) { calls.reLaunch.push(payload); },
      showModal: function (payload) { payload.success({ confirm: true }); },
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, { filename: "first-run.js" });
  var page = {
    data: JSON.parse(JSON.stringify(pageDef.data || {})),
    setData: function (next) { this.data = Object.assign({}, this.data, next || {}); },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls, data: scriptData };
}

(async function main() {
  var setup = loadPage();
  var manifest = JSON.parse(fs.readFileSync(
    path.join(__dirname, "../../deeptutor/services/first_run/script_manifest.v1.json"),
    "utf8",
  ));
  assert.strictEqual(
    setup.data.SCRIPT_VERSION,
    "first_run_script.v1@" + sha256(manifest),
    "frontend script version must mirror the backend authority",
  );
  assert.deepStrictEqual(
    setup.data.QUESTIONS.map(function (question) {
      return { questionId: question.questionId, contentSha256: question.contentSha256 };
    }),
    manifest.questions.map(function (question) {
      return { questionId: question.question_id, contentSha256: sha256(question.content) };
    }),
    "question ids and signed content hashes must not drift",
  );
  setup.data.QUESTIONS.forEach(function (question) {
    Object.keys(question.expl || {}).forEach(function (key) {
      assert(!/<[^>]+>/.test(question.expl[key]), "plain-text explanations must not leak HTML tags");
    });
  });
  setup.page.onLoad();
  setup.page._showQuestion(0);
  assert.strictEqual(setup.page.data.act, "question");
  assert.strictEqual(setup.page.data.qIndex, 0);
  assert.strictEqual(setup.page.data.q.questionId, "first_run.v1:qigu_gebu");
  assert.strictEqual(setup.page.data.questions, undefined, "page must expose only the current question");
  setup.page.onAnswer({ currentTarget: { dataset: { key: "B" } } });
  setup.page.onAnswer({ currentTarget: { dataset: { key: "B" } } });
  assert.strictEqual(setup.page.results.length, 1, "double tap must append one answer only");

  setup.page.war = "second";
  setup.page.mode = "nopoint";
  setup.page.profile = { material: "y2026", chan: "B", style: "B", slot: "C", drive: "B" };
  setup.page.completionId = "completion-test-0001";
  setup.page.results = setup.data.QUESTIONS.map(function (question, index) {
    return {
      questionId: question.questionId,
      name: question.name,
      familyShort: question.familyShort,
      picked: index === 0 ? "B" : "A",
      ok: index !== 0,
      mn: question.mn.big,
      durationMs: 8_000 + index,
    };
  });
  setup.page._buildReport();
  await flushPromises();
  await flushPromises();

  assert.strictEqual(setup.calls.completeFirstRun.length, 1, "report completion submits once");
  var payload = setup.calls.completeFirstRun[0];
  assert.deepStrictEqual(Object.keys(payload).sort(), [
    "answers", "completed_at", "completion_id", "declared_preferences", "script_version",
  ]);
  assert.strictEqual(payload.completion_id, "completion-test-0001");
  assert.strictEqual(payload.answers.length, 4);
  assert.strictEqual(payload.answers[0].selected_key, "B");
  assert.strictEqual(payload.answers[0].is_correct, undefined);
  assert.strictEqual(payload.score, undefined);
  assert.strictEqual(setup.page.data.syncStatus, "synced");
  assert.strictEqual(setup.page.data.report.rx, "今日焦点：屋面卷材起鼓");
  assert.strictEqual(setup.calls.done.length, 1);

  setup.page.onReportGo();
  assert.strictEqual(
    setup.calls.reLaunch[0].url,
    "/packageDeeptutor/pages/learn/learn",
    "completion returns to Learning home",
  );

  var offline = loadPage({ rejectSync: new Error("offline") });
  offline.page.onLoad();
  offline.page.war = "second";
  offline.page.mode = "nopoint";
  offline.page.profile = { material: "y2026", chan: "B", style: "B", slot: "C", drive: "B" };
  offline.page.completionId = "completion-offline-0001";
  offline.page.results = setup.page.results.slice();
  offline.page._buildReport();
  await flushPromises();
  await flushPromises();
  assert.strictEqual(offline.page.data.syncStatus, "pending");
  assert.strictEqual(offline.calls.pending.length, 1);
  assert.strictEqual(offline.calls.done.length, 0, "offline report must not become canonical done");

  var pageWxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/first-run/first-run.wxml"),
    "utf8",
  );
  assert(pageWxml.indexOf('wx:for="{{QUESTIONS}}"') < 0);
  assert(pageWxml.indexOf("fr-question-scroll") >= 0);
  assert(pageWxml.indexOf("fr-feedback-scroll") >= 0);
  assert(pageWxml.indexOf("{{qIndex + 1}} / {{qTotal}}") >= 0);

  console.log("PASS test_first_run_native_journey.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
