// test_assessment_contract.js — assessment question/state authority checks
// Run: node wx_miniprogram/tests/test_assessment_contract.js

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

function loadPage(relativePath) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef = null;
  var modalCalls = [];
  var apiMock = {
    createAssessment: function () {
      return Promise.resolve({
        quiz_id: "quiz_1",
        blueprint_version: "diagnostic_v1",
        requested_count: 20,
        delivered_count: 3,
        scored_count: 2,
        profile_count: 1,
        available_count: 3,
        shortfall_count: 17,
        questions: [
          {
            question_id: "q_1",
            text: "第一题",
            options: { A: "对", B: "错" },
          },
          {
            text: "第二题缺少后端 id",
            options: { A: "对", B: "错" },
          },
          {
            id: "q_3",
            question_stem:
              "复习一章内容后，你更容易坚持哪种复盘方式？\nA. same_day_review\nB. delayed_batch_review\nC. application_review\nD. needs_review_structure",
            question_type: "profile_probe",
            difficulty: "profile",
            scored: false,
            options: [
              { key: "A", text: "当天用 5 分钟回看错因", value: "same_day_review" },
              { key: "B", text: "隔一两天集中整理错题", value: "delayed_batch_review" },
              { key: "C", text: "等到做综合题时再回看", value: "application_review" },
              { key: "D", text: "目前还没有固定复盘方式", value: "needs_review_structure" },
            ],
          },
        ],
      });
    },
    submitAssessment: function () {
      return Promise.resolve({
        score: 38,
        level: "beginner",
        diagnostic_feedback: {
          ability_overview: {
            score_pct: 38,
            chapter_mastery: {
              "1A412030": { name: "1A412030", mastery: 100 },
              "1A411010": { name: "1A411010", mastery: 0 },
            },
            error_pattern: "gap_dominant",
          },
          cognitive_insight: {
            response_profile: "fluent",
            calibration_label: "accurate",
          },
          learner_profile: {
            archetype: "policy_seeded",
            traits: ["按测评结果动态调整"],
            study_tip: "建议把题目拆成步骤，每一步确认后再推进。",
          },
          action_plan: {
            priority_chapters: [{ name: "1A411010" }],
            plan_strategy: "先补最弱章节，再做一次短组针对训练。",
          },
        },
      });
    },
  };
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/route") {
        return {
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
          getAnimConfig: function () {
            return { enableBreathingOrbs: false };
          },
          vibrate: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function () {},
      showModal: function (options) {
        modalCalls.push(options || {});
      },
      setStorageSync: function () {},
      switchTab: function () {},
      reLaunch: function () {},
      navigateBack: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: relativePath });

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
  };
}

(async function main() {
  await run("assessment should normalize every question into a stable answer authority", async function () {
    var loaded = loadPage("pages/assessment/assessment.js");
    loaded.page.onStart();
    await flushPromises();

    assert(loaded.page.data.questions.length === 3, "assessment should load all returned questions");
    assert(
      loaded.page.data.questions[1].id === "q_2",
      "assessment should assign a stable fallback id when backend omits question id",
    );
    assert(
      loaded.page.data.answerSheet.length === 3,
      "assessment should expose an answer card from the normalized questions",
    );
    assert(
      loaded.page.data.answeredCount === 0 && loaded.page.data.unansweredCount === 3,
      "assessment should start with explicit 0/3 answered state",
    );
    assert(
      loaded.page.data.requestedCount === 20 &&
        loaded.page.data.deliveredCount === 3 &&
        loaded.page.data.shortfallCount === 17,
      "assessment should preserve requested/delivered count authority from backend",
    );
    assert(
      loaded.page.data.blueprintVersion === "diagnostic_v1" &&
        loaded.page.data.scoredCount === 2 &&
        loaded.page.data.profileCount === 1,
      "assessment should preserve blueprint/scored/profile authority from backend",
    );
    var profileQuestion = loaded.page.data.questions[2];
    assert(
      profileQuestion.options[0].text === "当天用 5 分钟回看错因" &&
        profileQuestion.options[0].value === "same_day_review",
      "profile probe should render Chinese option text while preserving internal option value",
    );
    assert(
      profileQuestion.question_stem.indexOf("same_day_review") < 0 &&
        profileQuestion.question_stem.indexOf("A.") < 0,
      "assessment should strip duplicated inline options from the displayed stem",
    );
    assert(
      loaded.page.data.assessmentNotice.indexOf("本次先完成 3 题") >= 0,
      "assessment should tell users when the delivered count is lower than requested",
    );
  });

  await run("assessment answer card should stay in sync with selected answers", async function () {
    var loaded = loadPage("pages/assessment/assessment.js");
    loaded.page.onStart();
    await flushPromises();

    loaded.page.onSelectOption({ currentTarget: { dataset: { key: "A" } } });
    assert(loaded.page.data.answeredCount === 1, "selecting an option should increment answeredCount");
    assert(loaded.page.data.unansweredCount === 2, "selecting an option should decrement unansweredCount");
    assert(
      loaded.page.data.answerSheet[0].answered === true &&
        loaded.page.data.answerSheet[1].answered === false,
      "answer card should mark only answered questions as answered",
    );
  });

  await run("assessment submit copy should distinguish blank and partial submissions", async function () {
    var loaded = loadPage("pages/assessment/assessment.js");
    loaded.page.onStart();
    await flushPromises();

    loaded.page.onSubmit();
    assert(
      loaded.modalCalls[0] && loaded.modalCalls[0].content.indexOf("尚未作答") >= 0,
      "blank submit should not look the same as partial submit",
    );

    loaded.page.onSelectOption({ currentTarget: { dataset: { key: "A" } } });
    loaded.page.onSubmit();
    assert(
      loaded.modalCalls[1] && loaded.modalCalls[1].content.indexOf("还有 2 题未答") >= 0,
      "partial submit should say how many questions remain unanswered",
    );
  });

  await run("assessment should submit after all delivered questions are answered despite requested shortfall", async function () {
    var loaded = loadPage("pages/assessment/assessment.js");
    loaded.page.onStart();
    await flushPromises();

    loaded.page.setData({
      selectedKeys: { q_1: "A", q_2: "A", q_3: "A" },
      answeredCount: 3,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();

    assert(loaded.modalCalls.length === 0, "fully answered delivered set should not show unanswered modal");
    assert(loaded.page.data.stage === "loading", "fully answered delivered set should proceed to submit");
  });

  await run("assessment result should not expose backend enum labels or chapter codes", async function () {
    var loaded = loadPage("pages/assessment/assessment.js");
    loaded.page.onStart();
    await flushPromises();

    loaded.page.setData({
      selectedKeys: { q_1: "A", q_2: "A", q_3: "A" },
      answeredCount: 3,
      unansweredCount: 0,
    });
    loaded.page.onSubmit();
    await flushPromises();

    assert(loaded.page.data.stage === "result", "submitted assessment should render result state");
    assert(
      loaded.page.data.archetypeName === "动态调节型学员",
      "result should translate policy seeded learner type into Chinese",
    );
    assert(
      loaded.page.data.chapterList[0].name.indexOf("1A") < 0 &&
        loaded.page.data.priorityChapters[0].indexOf("1A") < 0,
      "result should translate textbook chapter codes into user-facing Chinese labels",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_assessment_contract.js (" + pass + " assertions)");
})();
