// test_assessment_testset_view_model.js — P0A TestSet page contract
// Run: node yousenwebview/tests/test_assessment_testset_view_model.js

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

function loadPage(apiOverrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/assessment/assessment.js"),
    "utf8",
  );
  var pageDef = null;
  var modalCalls = [];
  var createPayloads = [];
  var apiMock = Object.assign(
    {
      createAssessment: function (payload) {
        createPayloads.push(payload);
        return Promise.resolve({
          quiz_id: "quiz_p0a",
          assessment_type: "topic_diagnostic",
          topic_label: "防水专题测评",
          blueprint_version: "topic_waterproof_v1",
          requested_count: 12,
          delivered_count: 2,
          scored_count: 2,
          profile_count: 0,
          lease_holder_other_device: false,
          questions: [
            {
              question_id: "q1",
              question_stem: "地下防水卷材搭接做法正确的是？",
              question_type: "single_choice",
              options: [
                { key: "A", text: "按规范搭接并处理节点" },
                { key: "B", text: "随意搭接" },
              ],
            },
            {
              question_id: "q2",
              question_stem: "防水混凝土施工缝处理正确的是？",
              question_type: "single_choice",
              options: [
                { key: "A", text: "先凿毛清理再处理" },
                { key: "B", text: "直接浇筑" },
              ],
            },
          ],
        });
      },
      getAssessmentTopics: function () {
        return Promise.resolve({
          topics: [
            {
              topic_id: "waterproof",
              label: "防水工程",
              status: "stable",
              enabled: true,
              form_count: 5,
            },
            {
              topic_id: "decoration",
              label: "装饰装修",
              status: "authoring_needed",
              enabled: false,
              form_count: 0,
            },
          ],
        });
      },
      submitAssessment: function () {
        return Promise.resolve({
          schema_version: "p0a-v1",
          quiz_id: "quiz_p0a",
          score_title: "本次专题测评得分",
          topic_label: "防水专题测评",
          score_summary: {
            score_pct: 50,
            correct_count: 1,
            answered_count: 2,
            scored_count: 2,
            blank_count: 0,
          },
          measurement_confidence: { level: "medium", reasons: [] },
          knowledge_map: [
            { knowledge_point: "地下防水", attempted: 2, correct: 1, score_pct: 50 },
          ],
          wrong_items: [
            {
              question_id: "q2",
              question_stem: "防水混凝土施工缝处理正确的是？",
              learner_answer: "B",
              correct_answer: "A",
              simple_explanation: "施工缝需要先处理基层和节点。",
              knowledge_points: ["地下防水"],
              error_codes: ["M01"],
            },
          ],
          attempt_refs: [{ question_id: "q2", attempt_ref: "attempt_signed" }],
          session_local_next_action: {
            authority: "session_local_deterministic",
            copy: "建议先复盘地下防水相关错题，再做 3 道同类专项练习。",
          },
          deep_explanation: { available: false, copy: "详细解析下个版本上线" },
          writeback_status: { status: "degraded", reason: "writeback_failed" },
          degraded_reason: "writeback_failed",
        });
      },
    },
    apiOverrides || {},
  );
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/route") {
        return { chat: function () { return "/packageDeeptutor/pages/chat/chat"; } };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () { return { statusBarHeight: 20 }; },
          isDark: function () { return true; },
          getAnimConfig: function () { return { enableBreathingOrbs: false }; },
          vibrate: function () {},
        };
      }
      if (request === "../../utils/taxonomy") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/taxonomy"));
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function () {},
      showModal: function (options) { modalCalls.push(options || {}); },
      setStorageSync: function () {},
      reLaunch: function () {},
      navigateBack: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/assessment/assessment.js",
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
  return { page: page, modalCalls: modalCalls, createPayloads: createPayloads };
}

function stringify(value) {
  return JSON.stringify(value || {});
}

(async function main() {
  await run("welcome copy communicates multi-form rotation", async function () {
    var wxml = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/assessment/assessment.wxml"),
      "utf8",
    );
    assert(wxml.indexOf(">5<") >= 0, "welcome stats should show five-form target");
    assert(wxml.indexOf("套轮换") >= 0, "welcome stats should explain paper rotation");
  });

  await run("welcome renders topic catalog and create uses selected topic", async function () {
    var loaded = loadPage();
    loaded.page.onLoad();
    await flushPromises();
    assert(loaded.page.data.topicCatalog.length === 2, "welcome should load topic catalog");
    assert(loaded.page.data.topicCatalog[0].topicId === "waterproof", "waterproof should be first catalog topic");
    assert(loaded.page.data.topicCatalog[1].enabled === false, "authoring_needed topic should be disabled");

    loaded.page.onSelectTopic({ currentTarget: { dataset: { topicId: "decoration" } } });
    assert(loaded.page.data.selectedTopicId === "waterproof", "disabled topic should not become selected");
    loaded.page.onStart();
    await flushPromises();
    assert(loaded.createPayloads[0].topic_ids[0] === "waterproof", "create should use selected enabled topic");
  });

  await run("P0A start uses topic diagnostic request and redacted pre-submit payload", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();

    var createPayload = loaded.createPayloads[0] || {};
    assert(createPayload.assessment_type === "topic_diagnostic", "create should request topic_diagnostic");
    assert(createPayload.subject_id === "construction_exam", "create should include subject_id");
    assert(createPayload.topic_ids[0] === "waterproof", "create should request waterproof topic");
    assert(createPayload.count === 12, "create should request signed P0A count");
    assert(stringify(loaded.page.data.questions).indexOf("correct_answer") < 0, "pre-submit payload should not expose correct_answer");
    assert(stringify(loaded.page.data.questions).indexOf('"answer"') < 0, "pre-submit payload should not expose answer");
  });

  await run("P0A submit renders backend report as display authority", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();

    loaded.page.setData({
      selectedKeys: { q1: "A", q2: "B" },
      answeredCount: 2,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    assert(loaded.page.data.serverReportMode === true, "result should use P0A server report mode");
    assert(loaded.page.data.scoreTitle.indexOf("本次") === 0, "score title must be scoped to this test");
    assert(loaded.page.data.resultScore === 50, "score should come from backend report");
    assert(loaded.page.data.knowledgeMap[0].name === "地下防水", "knowledge map should come from report");
    assert(loaded.page.data.wrongItems[0].correctAnswer === "A", "wrong item should show post-submit answer");
    assert(loaded.page.data.attemptRefs[0].attempt_ref === "attempt_signed", "attempt refs should be preserved");
    assert(loaded.page.data.archetypeName === "", "P0A report must not derive learner profile locally");
    assert(loaded.page.data.responseLabel === "", "P0A report must not derive response profile locally");
  });

  await run("P0A copy invariants and degraded/deep explanation behavior hold", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();
    loaded.page.setData({
      selectedKeys: { q1: "A", q2: "B" },
      answeredCount: 2,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    var dataText = stringify(loaded.page.data);
    ["全科能力分", "长期学习计划已更新", "系统已为你更新", "已掌握"].forEach(function (forbidden) {
      assert(dataText.indexOf(forbidden) < 0, "P0A result copy must not contain " + forbidden);
    });
    assert(loaded.page.data.deepExplanationAvailable === false, "deep explanation should not be available in P0A");
    assert(loaded.page.data.deepExplanationCopy === "详细解析下个版本上线", "deep explanation disabled copy should be fixed");
    assert(loaded.page.data.degradedCopy.indexOf("writeback_failed") < 0, "raw degraded reason should not leak to learner copy");
    assert(loaded.page.data.degradedCopy.length > 0, "degraded result should render learner-safe copy");
  });

  await run("second-device lease banner is user-facing", async function () {
    var loaded = loadPage({
      createAssessment: function (payload) {
        loadedCreatePayload = payload;
        return Promise.resolve({
          quiz_id: "quiz_p0a",
          assessment_type: "topic_diagnostic",
          topic_label: "防水专题测评",
          blueprint_version: "topic_waterproof_v1",
          requested_count: 12,
          delivered_count: 1,
          scored_count: 1,
          profile_count: 0,
          lease_holder_other_device: true,
          questions: [
            {
              question_id: "q1",
              question_stem: "防水题",
              question_type: "single_choice",
              options: [{ key: "A", text: "正确" }],
            },
          ],
        });
      },
    });
    var loadedCreatePayload = null;
    loaded.page.onStart();
    await flushPromises();
    assert(loadedCreatePayload.assessment_type === "topic_diagnostic", "override should still receive P0A payload");
    assert(loaded.page.data.readOnlyBanner.indexOf("另一台设备") >= 0, "other-device lease should show read-only banner");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_assessment_testset_view_model.js (" + pass + " assertions)");
})();
