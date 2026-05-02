// test_package_assessment_contract.js — package assessment question/state authority checks
// Run: node yousenwebview/tests/test_package_assessment_contract.js

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

function loadPage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/assessment/assessment.js"),
    "utf8",
  );
  var pageDef = null;
  var modalCalls = [];
  var apiMock = {
    createAssessment: function () {
      return Promise.resolve({
        quiz_id: "quiz_1",
        requested_count: 20,
        delivered_count: 3,
        available_count: 3,
        shortfall_count: 17,
        questions: [
          { question_id: "q_1", text: "第一题", options: { A: "对", B: "错" } },
          { text: "第二题缺少后端 id", options: { A: "对", B: "错" } },
          { id: "q_3", text: "第三题", options: { A: "对", B: "错" } },
        ],
      });
    },
    submitAssessment: function () {
      return Promise.resolve({ score: 0, diagnostic_feedback: {} });
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

  return { page: page, modalCalls: modalCalls };
}

(async function main() {
  await run("package assessment should expose normalized answer card state", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();

    assert(loaded.page.data.questions[1].id === "q_2", "missing question id should get stable fallback id");
    assert(loaded.page.data.answerSheet.length === 3, "answer card should mirror normalized questions");
    assert(loaded.page.data.answeredCount === 0, "initial answered count should be explicit");
    assert(
      loaded.page.data.requestedCount === 20 &&
        loaded.page.data.deliveredCount === 3 &&
        loaded.page.data.shortfallCount === 17,
      "package assessment should preserve requested/delivered count authority",
    );
    assert(
      loaded.page.data.assessmentNotice.indexOf("本次先完成 3 题") >= 0,
      "package assessment should expose a shortfall notice",
    );
  });

  await run("package assessment submit copy should distinguish blank and partial submissions", async function () {
    var loaded = loadPage();
    loaded.page.onStart();
    await flushPromises();

    loaded.page.onSubmit();
    assert(
      loaded.modalCalls[0] && loaded.modalCalls[0].content.indexOf("尚未作答") >= 0,
      "blank submit should have dedicated warning",
    );
    loaded.page.onSelectOption({ currentTarget: { dataset: { key: "A" } } });
    loaded.page.onSubmit();
    assert(
      loaded.modalCalls[1] && loaded.modalCalls[1].content.indexOf("还有 2 题未答") >= 0,
      "partial submit should include remaining unanswered count",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_package_assessment_contract.js (" + pass + " assertions)");
})();
