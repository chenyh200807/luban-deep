// Run: node yousenwebview/tests/test_retest_completion_authority.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var retest = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf8",
);
var handoff = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/handoff/handoff.js"),
  "utf8",
);
var station = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.js"),
  "utf8",
);
var stationWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/station/station.wxml"),
  "utf8",
);
var review = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.js"),
  "utf8",
);
var stations = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/stations/stations.js"),
  "utf8",
);
var learn = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/learn/learn.js"),
  "utf8",
);
var chat = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var report = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
  "utf8",
);
var profile = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
  "utf8",
);
var gauntlet = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/gauntlet/gauntlet.js"),
  "utf8",
);
var errorbank = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/errorbank/errorbank.js"),
  "utf8",
);
var f16Lesson = fs.readFileSync(
  path.join(__dirname, "../../web/public/luban-preview/f16/lesson.html"),
  "utf8",
);
var f16Practice = fs.readFileSync(
  path.join(__dirname, "../../web/public/luban-preview/f16/practice.html"),
  "utf8",
);
var retestWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.wxml"),
  "utf8",
);

assert.ok(retest.indexOf("completeLubanRetest") >= 0, "retest must use canonical completion endpoint");
assert.strictEqual(retest.indexOf("postStationCompleted"), -1, "retest page must not be a second station writer");
assert.strictEqual(handoff.indexOf("postStationCompleted"), -1, "handoff must be presentation-only");
assert.strictEqual(station.indexOf("handoff/handoff"), -1, "ungraded station self-check must never open a completion handoff");
assert.strictEqual(station.indexOf("practiceUrl"), -1, "station shell must not be a second practice-navigation authority");
assert.strictEqual(station.indexOf("isF16"), -1, "compiled practice capability must not branch on F16");
assert.strictEqual(station.indexOf("TIER_PRACTICE"), -1, "lesson/practice navigation must stay inside the finished card");
assert.strictEqual(station.indexOf("postLessonProgress"), -1, "station shell must not duplicate the card evidence bridge");
assert.strictEqual(stationWxml.indexOf("st-footer"), -1, "native fallback must not intercept finished-card touches");
assert.ok(f16Lesson.indexOf('href="practice.html"') >= 0, "F16 lesson CTA must open the publisher-derived finished practice consumer");
assert.ok(f16Practice.indexOf("__dtRedirectEvidence") >= 0, "the fifth answer must bridge automatically into canonical learner evidence");
assert.strictEqual(f16Practice.indexOf("保存学习证据 · 查看正式收据"), -1, "the user must not choose whether a completed practice is recorded");
assert.ok(f16Practice.indexOf("patch.finished===true||patch.phase==='result'") >= 0, "the local result transition must be intercepted by the evidence bridge");
assert.strictEqual(f16Practice.indexOf("服务端正在重新判定并更新你的学习记录"), -1, "the bridge must not claim server work before redirect succeeds");
assert.ok(
  f16Practice.indexOf("presentation=receipt&pack_id=") >= 0 &&
    f16Practice.indexOf("&practice_surface=") >= 0 &&
    f16Practice.indexOf("&answer_indexes=") >= 0,
  "finished practice must enter retest in receipt-only mode after the same five answers",
);
assert.ok(retest.indexOf("bridgeAnswerIndexes") >= 0, "receipt-only bridge must map finished HTML answers to canonical option identities");
assert.ok(retest.indexOf("selected_option_id") >= 0, "compiled HTML MCQ must submit only selected option identity");
assert.ok(retest.indexOf("serverCorrectCount") >= 0, "forward score must come back from server rescore");
assert.strictEqual(handoff.indexOf("luban_retest_due_"), -1, "handoff local storage must not become due authority");
assert.ok(handoff.indexOf("route.lubanErrorbank()") >= 0, "handoff must use the canonical error-bank route");
assert.strictEqual(handoff.indexOf("terminal_event_id"), -1, "legacy handoff must not trust a forgeable terminal query");
assert.ok(retest.indexOf('syncStatus: "synced"') >= 0, "receipt must be gated by durable sync");
assert.ok(retest.indexOf("terminal_event_id") >= 0, "receipt rendering must require a canonical terminal event id");
assert.ok(retest.indexOf("learning_change") >= 0, "receipt must render the server-projected learning change");
assert.ok(retest.indexOf("已练过 · 待验证") >= 0, "forward receipt must explain that practice is not mastery");
assert.strictEqual(retestWxml.indexOf("你是真懂了"), -1, "an item result must not claim mastery before the canonical terminal");
assert.strictEqual(retestWxml.indexOf("'真懂'"), -1, "the item seal must describe this answer, not durable mastery");
assert.ok(retestWxml.indexOf("这是本轮作答结果") >= 0, "the item feedback must remain scoped to the current answer");
assert.strictEqual(retest.indexOf("handoff/handoff"), -1, "canonical receipt must not be re-projected through a forgeable handoff query");
assert.ok(retest.indexOf("probe_id: this.data.probeId") >= 0, "review must preserve canonical probe identity");
assert.ok(retest.indexOf("selection_id: this.data.selectionId") >= 0, "completion must preserve server-issued selection identity");
assert.ok(review.indexOf("entry.probeId") >= 0, "review due entry must forward probe identity");
assert.ok(review.indexOf("pack_review") >= 0, "review must consume the unified report pack-review slice");
assert.ok(stations.indexOf("onShow()") >= 0 && stations.indexOf("this._load()") >= 0, "stations must refresh the canonical report after returning from practice");
assert.ok(review.indexOf("this._hasShown && !this.data.loading") >= 0 && review.indexOf("this._loadAll()") >= 0, "review must refresh canonical due tasks after returning from a retest");
assert.ok(learn.indexOf("onShow()") >= 0 && learn.indexOf("this._load()") >= 0, "learning must refresh the unified report on return");
assert.ok(chat.indexOf("onShow: function") >= 0 && chat.indexOf("self._loadDashboard()") >= 0, "chat home must refresh the canonical dashboard");
assert.ok(chat.indexOf("readOwnerValue(HOME_DASHBOARD_CACHE_KEY)") >= 0 && chat.indexOf("currentOwnerId") >= 0, "chat dashboard cache must be isolated by canonical user");
assert.ok(report.indexOf("onShow()") >= 0 && report.indexOf("this._loadReportPage()") >= 0, "report must refresh the unified report on show");
assert.ok(profile.indexOf("onShow: function") >= 0 && profile.indexOf("this._loadRoute()") >= 0, "profile must refresh its route card from the unified report");
assert.ok(gauntlet.indexOf('"&mode=forward"') >= 0, "gauntlet repeat must be forward practice");
assert.ok(errorbank.indexOf("getLubanReviewDue") >= 0, "errorbank must consume canonical review due");
assert.strictEqual(errorbank.indexOf("getLubanRetestItems"), -1, "errorbank must not infer due from supply");
assert.ok(errorbank.indexOf('"&mode=review&probe_id="') >= 0, "errorbank must forward due probe");

console.log("PASS test_retest_completion_authority.js");
