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
  var toastCalls = [];
  var createPayloads = [];
  var submitPayloads = [];
  var reLaunchCalls = [];
  var pendingChatIntents = [];
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
          recommendation: {
            recommended_mode: "diagnostic",
            recommended_count: 20,
            reason: "先用综合摸底校准全科能力结构",
          },
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
      submitAssessment: function (quizId, answers, timeSpent, deviceId) {
        submitPayloads.push({
          quizId: quizId,
          answers: answers,
          timeSpent: timeSpent,
          deviceId: deviceId,
        });
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
      requestAssessmentDeepExplanation: function () {
        return Promise.resolve({
          workflow_status: "completed",
          billing: { status: "captured", captured_points: 20 },
          explanation: {
            summary: "本题考施工缝节点处理，B 错在没有先处理基层。",
            key_terms: ["施工缝", "基层处理"],
            why_wrong: "你选了直接浇筑，漏掉了凿毛清理这一前置条件。",
            cause_analysis: "题干问正确做法，应先确认施工缝处理顺序。",
            scoring_points: "识别施工缝处理的前置步骤。",
            option_reviews: [
              { key: "A", status: "correct", status_label: "正确", review: "A 符合先处理再浇筑。" },
              { key: "B", status: "extra", status_label: "错选", review: "B 跳过基层处理。" },
            ],
            pitfall: "不要把后续浇筑当成完整施工缝处理。",
            mnemonic: "先清理，再处理，后浇筑。",
            source_basis: "题库解析和知识卡。",
          },
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
        return {
          chat: function () { return "/packageDeeptutor/pages/chat/chat"; },
          report: function (query) {
            var url = "/packageDeeptutor/pages/report/report";
            var parts = [];
            Object.keys(query || {}).forEach(function (key) {
              parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(query[key]));
            });
            if (parts.length) url += "?" + parts.join("&");
            return url;
          },
        };
      }
      if (request === "../../utils/runtime") {
        return {
          setWorkspaceBack: function () {},
          setPendingChatIntent: function (query, mode, promptIntent) {
            pendingChatIntents.push({
              query: query,
              mode: mode,
              promptIntent: promptIntent || {},
            });
          },
        };
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
        showToast: function (options) { toastCalls.push(options || {}); },
        showModal: function (options) { modalCalls.push(options || {}); },
        getStorageSync: function (key) { return sandbox.__storage[key]; },
        setStorageSync: function (key, value) { sandbox.__storage[key] = value; },
        reLaunch: function (options) { reLaunchCalls.push(options || {}); },
        navigateBack: function () {},
    },
    __storage: {},
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
  return {
    page: page,
    modalCalls: modalCalls,
    toastCalls: toastCalls,
    createPayloads: createPayloads,
    submitPayloads: submitPayloads,
    reLaunchCalls: reLaunchCalls,
    pendingChatIntents: pendingChatIntents,
    storage: sandbox.__storage,
  };
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
    assert(wxml.indexOf("综合摸底") >= 0, "welcome should expose comprehensive diagnostic mode");
    assert(wxml.indexOf("专题测评") >= 0, "welcome should expose topic testset mode");
    assert(wxml.indexOf("welcomeFormCount") >= 0, "welcome stats should bind five-form target");
    assert(wxml.indexOf("套轮换") >= 0, "welcome stats should explain paper rotation");
  });

  await run("default start uses durable comprehensive 20-question form", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();

    var createPayload = loaded.createPayloads[0] || {};
    assert(loaded.page.data.assessmentMode === "diagnostic", "default mode should be comprehensive diagnostic");
    assert(createPayload.assessment_type === "real_exam_simulation", "default create should request durable comprehensive form");
    assert(createPayload.count === 20, "comprehensive mode should request the 20-question form");
    assert(!createPayload.topic_ids, "diagnostic mode should not send topic_ids");
    assert(createPayload.device_id === loaded.storage["deeptutor.assessment.deviceId"], "create should bind to local assessment device id");
    assert(loaded.page.data.welcomeTitle === "综合摸底", "default title should name the 20-question diagnostic");
  });

  await run("diagnostic response without topic label keeps comprehensive label", async function () {
    var loaded = loadPage({
      createAssessment: function (payload) {
        loaded.createPayloads.push(payload);
        return Promise.resolve({
          quiz_id: "quiz_diag",
          assessment_type: "diagnostic",
          blueprint_version: "diagnostic_v1",
          requested_count: 20,
          delivered_count: 1,
          scored_count: 1,
          profile_count: 0,
          questions: [
            {
              question_id: "q1",
              question_stem: "综合摸底题",
              question_type: "single_choice",
              options: [{ key: "A", text: "A" }],
            },
          ],
        });
      },
    });
    loaded.page.onStart();
    await flushPromises();
    assert(loaded.page.data.topicLabel === "综合摸底", "diagnostic fallback label should not say waterproof");
  });

  await run("successful create skips invalid question rows instead of reporting load failure", async function () {
    var loaded = loadPage({
      createAssessment: function (payload) {
        loaded.createPayloads.push(payload);
        return Promise.resolve({
          quiz_id: "quiz_diag_sparse",
          assessment_type: "real_exam_simulation",
          blueprint_version: "real_exam_simulation_mini_v1",
          requested_count: 20,
          delivered_count: 2,
          scored_count: 1,
          profile_count: 0,
          questions: [
            null,
            {
              question_id: "q_good",
              question_stem: "综合摸底可用题",
              question_type: "single_choice",
              options: [{ key: "A", text: "A" }],
            },
          ],
        });
      },
    });
    loaded.page.onStart();
    await flushPromises();

    var toastText = loaded.toastCalls.map(function (item) { return item.title || ""; }).join("|");
    assert(toastText.indexOf("加载题目失败") < 0, "successful create must not be reported as load failure for sparse rows");
    assert(loaded.page.data.stage === "quiz", "successful create should enter quiz when usable questions remain");
    assert(loaded.page.data.questions.length === 1, "invalid question rows should be skipped");
    assert(loaded.page.data.currentQ.id === "q_good", "first usable question should become current question");
  });

  await run("personalized recommendation preselects enabled topic", async function () {
    var loaded = loadPage({
      getAssessmentTopics: function () {
        return Promise.resolve({
          recommendation: {
            recommended_mode: "topic",
            recommended_topic_id: "main_structure",
            recommended_count: 12,
            reason: "近期主体结构错题集中，建议先做专题测评。",
          },
          topics: [
            {
              topic_id: "waterproof",
              label: "防水工程",
              status: "stable",
              enabled: true,
              form_count: 5,
            },
            {
              topic_id: "main_structure",
              label: "主体结构",
              status: "stable",
              enabled: true,
              form_count: 5,
            },
          ],
        });
      },
    });
    loaded.page.onLoad();
    await flushPromises();

    assert(loaded.page.data.assessmentMode === "topic", "recommended topic should preselect topic mode");
    assert(loaded.page.data.selectedTopicId === "main_structure", "recommended enabled topic should be selected");
    assert(loaded.page.data.welcomeTitle === "主体结构专题测评", "recommended title should follow selected topic");
    assert(loaded.page.data.assessmentRecommendationReason.indexOf("主体结构") >= 0, "recommendation reason should be visible");
    assert(loaded.page.data.topicCatalog[1].recommended === true, "recommended topic should be marked");
  });

  await run("welcome renders topic catalog and create uses selected topic", async function () {
    var loaded = loadPage();
    loaded.page.onLoad();
    await flushPromises();
    assert(loaded.page.data.topicCatalog.length === 2, "welcome should load topic catalog");
    assert(loaded.page.data.topicCatalog[0].topicId === "waterproof", "waterproof should be first catalog topic");
    assert(loaded.page.data.topicCatalog[1].enabled === false, "authoring_needed topic should be disabled");

    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
    assert(loaded.page.data.welcomeTitle === "防水工程专题测评", "topic title should follow selected topic");
    loaded.page.onSelectTopic({ currentTarget: { dataset: { topicId: "decoration" } } });
    assert(loaded.page.data.selectedTopicId === "waterproof", "disabled topic should not become selected");
    loaded.page.onStart();
    await flushPromises();
    assert(loaded.createPayloads[0].topic_ids[0] === "waterproof", "create should use selected enabled topic");
  });

  await run("authoring needed topic is fail-closed even if backend sends enabled true", async function () {
    var loaded = loadPage({
      getAssessmentTopics: function () {
        return Promise.resolve({
          recommendation: {
            recommended_mode: "topic",
            recommended_topic_id: "safety",
            recommended_count: 12,
            reason: "安全管理薄弱",
          },
          topics: [
            {
              topic_id: "safety",
              label: "安全管理",
              status: "authoring_needed",
              enabled: true,
              form_count: 1,
            },
            {
              topic_id: "waterproof",
              label: "防水工程",
              status: "stable",
              enabled: true,
              form_count: 5,
            },
          ],
        });
      },
    });
    loaded.page.onLoad();
    await flushPromises();

    var safety = loaded.page.data.topicCatalog.find(function (item) {
      return item.topicId === "safety";
    });
    assert(safety.enabled === false, "authoring_needed must override backend enabled=true");
    assert(safety.statusLabel === "待补题", "authoring_needed should show 待补题");
    assert(loaded.page.data.assessmentMode === "diagnostic", "recommendation must not auto-enter authoring_needed topic");
    assert(loaded.page.data.recommendedMode === "diagnostic", "recommended mode should fail closed to diagnostic");
    assert(loaded.page.data.selectedTopicId === "waterproof", "first enabled stable topic should remain selectable");
  });

  await run("late topic recommendation must not override manual comprehensive selection", async function () {
    var resolveTopics;
    var loaded = loadPage({
      getAssessmentTopics: function () {
        return new Promise(function (resolve) {
          resolveTopics = resolve;
        });
      },
    });
    loaded.page.onLoad();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "diagnostic" } } });
    resolveTopics({
      recommendation: {
        recommended_mode: "topic",
        recommended_topic_id: "main_structure",
        recommended_count: 12,
        reason: "主体结构薄弱，建议先专题。",
      },
      topics: [
        {
          topic_id: "main_structure",
          label: "主体结构",
          status: "stable",
          enabled: true,
          form_count: 5,
        },
      ],
    });
    await flushPromises();

    assert(loaded.page.data.recommendedMode === "topic", "late recommendation should still update recommendation badge");
    assert(loaded.page.data.selectedTopicId === "main_structure", "late catalog should still update selected topic metadata");
    assert(loaded.page.data.assessmentMode === "diagnostic", "manual comprehensive selection must remain authoritative");
    assert(loaded.page.data.welcomeTitle === "综合摸底", "manual comprehensive welcome copy must not be overwritten");
  });

  await run("late topic recommendation must not override manually selected topic", async function () {
    var resolveTopics;
    var loaded = loadPage({
      getAssessmentTopics: function () {
        return new Promise(function (resolve) {
          resolveTopics = resolve;
        });
      },
    });
    loaded.page.onLoad();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
    loaded.page.onSelectTopic({ currentTarget: { dataset: { topicId: "waterproof" } } });
    resolveTopics({
      recommendation: {
        recommended_mode: "topic",
        recommended_topic_id: "main_structure",
        recommended_count: 12,
        reason: "主体结构薄弱，建议先专题。",
      },
      topics: [
        {
          topic_id: "waterproof",
          label: "防水工程",
          status: "stable",
          enabled: true,
          form_count: 5,
        },
        {
          topic_id: "main_structure",
          label: "主体结构",
          status: "stable",
          enabled: true,
          form_count: 5,
        },
      ],
    });
    await flushPromises();
    loaded.page.onStart();
    await flushPromises();

    assert(loaded.page.data.assessmentMode === "topic", "manual topic mode must remain authoritative");
    assert(loaded.page.data.selectedTopicId === "waterproof", "manual topic selection must remain authoritative");
    assert(loaded.page.data.welcomeTitle === "防水工程专题测评", "manual topic welcome copy must not be overwritten");
    assert(loaded.createPayloads[0].topic_ids[0] === "waterproof", "create should use manually selected topic");
  });

  await run("create failure uses classified learner-facing error copy", async function () {
    var loaded = loadPage({
      createAssessment: function (payload) {
        loaded.createPayloads.push(payload);
        return Promise.reject({ status: 503, detail: { error: "assessment_sessions_unavailable" } });
      },
      describeRequestError: function (err, fallbackMsg, opts) {
        var msg = opts.customMap({ status: err.status, detailText: "assessment_sessions_unavailable", rawMessage: "" });
        return msg || fallbackMsg;
      },
    });
    loaded.page.onStart();
    await flushPromises();

    var toastText = loaded.toastCalls.map(function (item) { return item.title || ""; }).join("|");
    assert(toastText.indexOf("题库服务暂时不可用") >= 0, "create failure should show specific service-unavailable copy");
    assert(toastText.indexOf("加载题目失败") < 0, "create failure should not collapse to generic load failure");
    assert(loaded.page.data.stage === "welcome", "failed create should return to welcome");
  });

  await run("P0A start uses topic diagnostic request and redacted pre-submit payload", async function () {
    var loaded = loadPage();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
    loaded.page.onStart();
    await flushPromises();

    var createPayload = loaded.createPayloads[0] || {};
    assert(createPayload.assessment_type === "topic_diagnostic", "create should request topic_diagnostic");
    assert(createPayload.subject_id === "construction_exam", "create should include subject_id");
    assert(createPayload.topic_ids[0] === "waterproof", "create should request waterproof topic");
    assert(createPayload.count === 12, "create should request signed P0A count");
    assert(createPayload.device_id === loaded.storage["deeptutor.assessment.deviceId"], "topic create should include local assessment device id");
    assert(stringify(loaded.page.data.questions).indexOf("correct_answer") < 0, "pre-submit payload should not expose correct_answer");
    assert(stringify(loaded.page.data.questions).indexOf('"answer"') < 0, "pre-submit payload should not expose answer");
  });

  await run("P0A submit renders backend report as display authority", async function () {
    var loaded = loadPage();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
    loaded.page.onStart();
    await flushPromises();

    loaded.page.setData({
      selectedKeys: { q1: "A", q2: "B" },
      answeredCount: 2,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    assert(loaded.submitPayloads[0].deviceId === loaded.storage["deeptutor.assessment.deviceId"], "submit should reuse local assessment device id");
    assert(loaded.page.data.serverReportMode === true, "result should use P0A server report mode");
    assert(loaded.page.data.scoreTitle.indexOf("本次") === 0, "score title must be scoped to this test");
    assert(loaded.page.data.resultScore === 50, "score should come from backend report");
    assert(loaded.page.data.knowledgeMap[0].name === "地下防水", "knowledge map should come from report");
    assert(loaded.page.data.wrongItems[0].correctAnswer === "A", "wrong item should show post-submit answer");
    assert(loaded.page.data.wrongItems[0].options.length === 2, "wrong item should reuse redacted question options after submit");
    assert(loaded.page.data.wrongItems[0].explanation.indexOf("解析：") === 0, "wrong item default review should use learner-facing 解析 label");
    assert(loaded.page.data.wrongItems[0].expanded === false, "AI detailed review should be collapsed by default");
    assert(loaded.page.data.issueSummary.length === 5, "result should group mistakes into trainable issue types");
    assert(loaded.page.data.actionKnowledgeMap[0].actionLabel === "优先补", "knowledge map should answer what to train first");
    assert(loaded.page.data.prescriptionSteps[0].title.indexOf("错题讲评") >= 0, "result should include user-facing prescription steps");
    assert(loaded.page.data.attemptRefs[0].attempt_ref === "attempt_signed", "attempt refs should be preserved");
    assert(loaded.page.data.archetypeName === "", "P0A report must not derive learner profile locally");
    assert(loaded.page.data.responseLabel === "", "P0A report must not derive response profile locally");

    loaded.page.onToggleWrongDetail({ currentTarget: { dataset: { questionId: "q2" } } });
    assert(loaded.page.data.wrongItems[0].expanded === true, "AI detailed review should expand on demand");
    assert(loaded.page.data.wrongItems[0].detailStatus === "loading", "AI detailed review should show generation workflow status");
    await flushPromises();
    assert(loaded.page.data.wrongItems[0].detailStatus === "ready", "AI detailed review should resolve from backend LLM endpoint");
    assert(loaded.page.data.wrongItems[0].detailBilling === "本次消耗 20 点", "AI detailed review should show captured point cost");
    assert(
      loaded.page.data.wrongItems[0].detail.whyWrong.indexOf("凿毛清理") >= 0,
      "AI detailed review should use generated explanation, not static projection",
    );
  });

  await run("successful legacy diagnostic submit is not reported as submit failure when render data is irregular", async function () {
    var loaded = loadPage({
      createAssessment: function (payload) {
        loaded.createPayloads.push(payload);
        return Promise.resolve({
          quiz_id: "quiz_legacy",
          assessment_type: "diagnostic",
          blueprint_version: "diagnostic_v1",
          requested_count: 20,
          delivered_count: 1,
          scored_count: 1,
          profile_count: 0,
          questions: [
            {
              question_id: "q1",
              question_stem: "综合摸底旧卷题",
              question_type: "single_choice",
              options: [{ key: "A", text: "A" }],
            },
          ],
        });
      },
      submitAssessment: function () {
        return Promise.resolve({
          score: 12,
          level: "beginner",
          diagnostic_feedback: {
            ability_overview: { score_pct: 12, chapter_mastery: {} },
            action_plan: {
              priority_chapters: { name: "建筑实务综合" },
              plan_strategy: "先补最薄弱知识点。",
            },
          },
        });
      },
    });
    loaded.page.onStart();
    await flushPromises();
    loaded.page.setData({
      selectedKeys: { q1: "A" },
      answeredCount: 1,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    var toastText = loaded.toastCalls.map(function (item) { return item.title || ""; }).join("|");
    assert(toastText.indexOf("提交失败") < 0, "successful submit must not show submit failure for render-only errors");
    assert(loaded.page.data.stage === "result", "successful submit should still land on result stage");
    assert(loaded.page.data.resultScore === 12, "fallback result should preserve server score");
    assert(
      loaded.page.data.planStrategy.indexOf("先补最薄弱知识点") >= 0,
      "irregular priority_chapters should not prevent rendering backend action plan strategy",
    );
  });

  await run("P0A copy invariants and degraded/deep explanation behavior hold", async function () {
    var loaded = loadPage();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
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

  await run("result CTA returns to report training view instead of chat", async function () {
    var wxml = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/assessment/assessment.wxml"),
      "utf8",
    );
    assert(wxml.indexOf('bindtap="goLearningPlan"') >= 0, "result CTA should bind to report training navigation");
    assert(wxml.indexOf("AI详细解析") >= 0, "result should expose AI detailed review action");
    assert(
      wxml.indexOf("错题讲评") < wxml.indexOf("错因结构"),
      "wrong item review should render before issue structure",
    );
    assert(wxml.indexOf('bindtap="goChat"') < 0, "assessment result must not route learners back to chat");

    var loaded = loadPage();
    loaded.page.goLearningPlan();

    assert(
      loaded.reLaunchCalls[0] && loaded.reLaunchCalls[0].url === "/packageDeeptutor/pages/report/report?detail=training",
      "result CTA should relaunch report training detail",
    );
  });

  await run("wrong item practice carries attempt and error context to report training", async function () {
    var loaded = loadPage();
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
    loaded.page.onStart();
    await flushPromises();
    loaded.page.setData({
      selectedKeys: { q1: "A", q2: "B" },
      answeredCount: 2,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    loaded.page.onPracticeWrongItem({ currentTarget: { dataset: { questionId: "q2" } } });

    assert(loaded.pendingChatIntents.length === 0, "wrong item practice should not open chat training");
    var storedIntent = loaded.storage && loaded.storage["deeptutor.report.pendingTrainingAction"];
    assert(storedIntent.prompt.indexOf("3 道") >= 0, "practice prompt should request three similar questions");
    assert(storedIntent.source === "assessment_result_wrong_item", "stored intent source should be the assessment wrong item");
    assert(storedIntent.attempt_ref === "attempt_signed", "stored intent should carry attempt_ref");
    assert(storedIntent.concept_label === "地下防水", "stored intent should carry knowledge point");
    assert(storedIntent.error_label === "M01", "stored intent should carry error code");
    assert(
      storedIntent.followupQuestionContext &&
        storedIntent.followupQuestionContext.question_id === "q2",
      "stored intent should carry the wrong-item question context",
    );
    assert(
      storedIntent.followupQuestionContext.user_answer === "B" &&
        storedIntent.followupQuestionContext.correct_answer === "A",
      "stored wrong-item context should carry learner and correct answers",
    );
    assert(
      storedIntent.followupQuestionContext.options &&
        storedIntent.followupQuestionContext.options.A === "先凿毛清理再处理",
      "stored wrong-item context should carry normalized options",
    );
    assert(storedIntent.question_count === 3, "stored intent should request three questions");
    assert(
      loaded.reLaunchCalls[0].url.indexOf("/packageDeeptutor/pages/report/report?") === 0 &&
        loaded.reLaunchCalls[0].url.indexOf("detail=training") >= 0 &&
        loaded.reLaunchCalls[0].url.indexOf("attempt_ref=attempt_signed") >= 0,
      "wrong item practice should open report training with signed attempt context",
    );
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
    loaded.page.onSelectAssessmentMode({ currentTarget: { dataset: { mode: "topic" } } });
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
