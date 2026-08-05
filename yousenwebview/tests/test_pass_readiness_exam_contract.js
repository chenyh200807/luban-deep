// Run: node yousenwebview/tests/test_pass_readiness_exam_contract.js
// 过线体检测评页(屏 2)合同:
// 1. create 载荷 = assessment_type:"pass_readiness" + device_id(不带写死题数);
// 2. 中场检查点完全由响应 checkpoint_after 驱动: 答满 N 道计分题 → 检查点屏,
//    只出现一次; checkpoint_after 缺失 → 永不打断;
// 3. 检查点屏零证据/零弱点, 唯一 CTA 后回到第一道未答题;
// 4. 本地草稿 + 服务端 resume, 同题冲突服务端赢;
// 5. 提交 wire = dict[str,str]; 成功后清草稿、存报告、redirect 报告页。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var source = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/pass-readiness/exam/exam.js"),
  "utf8",
);
var wxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/pass-readiness/exam/exam.wxml"),
  "utf8",
);

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}
function flushTimers() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 320);
  });
}

function buildQuestions() {
  var rows = [];
  for (var i = 1; i <= 6; i++) {
    rows.push({
      question_id: "s" + i,
      question_stem: "计分题 " + i,
      question_type: "single_choice",
      options: [{ key: "A", text: "甲" }, { key: "B", text: "乙" }],
    });
  }
  rows.push({
    question_id: "c1",
    question_stem: "案例题 1",
    question_type: "multi_choice",
    case_id: "case_a",
    options: [{ key: "A", text: "甲" }, { key: "B", text: "乙" }],
  });
  rows.push({
    question_id: "p1",
    question_stem: "备考情况题",
    question_type: "profile_probe",
    options: [{ key: "A", text: "第一次" }],
  });
  return rows;
}

function loadPage(overrides) {
  var calls = {
    createPayloads: [],
    submitPayloads: [],
    resumeCalls: [],
    redirects: [],
    toasts: [],
    modals: [],
    ownerStorage: {},
  };
  var createResponse = Object.assign(
    {
      quiz_id: "quiz_pr_exam",
      checkpoint_after: 6,
      scored_count: 12,
      profile_count: 3,
      questions: buildQuestions(),
    },
    (overrides && overrides.createResponse) || {},
  );
  var apiMock = {
    createAssessment: function (payload) {
      calls.createPayloads.push(payload);
      return Promise.resolve(createResponse);
    },
    getAssessmentSession: function (quizId, deviceId) {
      calls.resumeCalls.push({ quizId: quizId, deviceId: deviceId });
      if (overrides && overrides.resumeResponse) {
        return Promise.resolve(overrides.resumeResponse);
      }
      return Promise.reject(new Error("assessment_session_not_found"));
    },
    submitAssessment: function (quizId, answers, timeSpent, deviceId) {
      calls.submitPayloads.push({
        quizId: quizId,
        answers: answers,
        timeSpent: timeSpent,
        deviceId: deviceId,
      });
      return Promise.resolve({
        schema_version: "p0a-v1",
        pass_readiness: { band_status: "ok", estimated_score_band: "75–95 分" },
      });
    },
    describeRequestError: function (err, fallback) {
      return fallback;
    },
  };
  var pageDef = null;
  var sandbox = {
    console: console,
    Promise: Promise,
    Date: Date,
    Math: Math,
    setTimeout: setTimeout,
    isNaN: isNaN,
    Number: Number,
    String: String,
    Object: Object,
    require: function (request) {
      if (request === "../../../../utils/api") return apiMock;
      if (request === "../../../../utils/auth") {
        return {
          readOwnerStorage: function (key) {
            return calls.ownerStorage[key];
          },
          writeOwnerStorage: function (key, value) {
            calls.ownerStorage[key] = value;
            return true;
          },
        };
      }
      if (request === "../../../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDarkOr: function () {
            return false;
          },
          vibrate: function () {},
        };
      }
      if (request === "../../../../utils/route") {
        return {
          lubanPassReadiness: function () {
            return "/packageDeeptutor/pages/luban/pass-readiness/landing/landing";
          },
          lubanPassReadinessReport: function (query) {
            return (
              "/packageDeeptutor/pages/luban/pass-readiness/report/report?quiz_id=" +
              (query && query.quiz_id)
            );
          },
        };
      }
      if (request === "../../../../utils/surface-telemetry") {
        return {
          trackProductBehavior: function () {},
          trackModuleView: function () {},
          trackModuleExit: function () {},
        };
      }
      if (request === "../../../../utils/pass-readiness-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-view-model"));
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "device-1";
      },
      setStorageSync: function () {},
      showToast: function (opts) {
        calls.toasts.push(opts);
      },
      showModal: function (opts) {
        calls.modals.push(opts);
      },
      redirectTo: function (opts) {
        calls.redirects.push(opts.url);
      },
      navigateBack: function () {},
      reLaunch: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, { filename: "exam.js" });
  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

function answerCurrent(page, key) {
  page.onSelectOption({ currentTarget: { dataset: { key: key || "A" } } });
}

(async function main() {
  // WXML: 案例微进度与不计分标注绑定在场
  assert.ok(wxml.indexOf("currentQ.caseTag") >= 0, "案例微进度绑定缺失");
  assert.ok(wxml.indexOf("profile_probe") >= 0, "profile_probe 不计分标注缺失");
  assert.ok(wxml.indexOf("checkpoint.cta") >= 0, "检查点唯一 CTA 绑定缺失");

  // ── 1+2+3. create 载荷 + checkpoint_after 驱动 ──
  var loaded = loadPage();
  loaded.page.onLoad({});
  await flushPromises();
  assert.strictEqual(loaded.calls.createPayloads.length, 1);
  assert.strictEqual(loaded.calls.createPayloads[0].assessment_type, "pass_readiness");
  assert.ok(loaded.calls.createPayloads[0].device_id, "create 必须带 device_id");
  assert.ok(!("count" in loaded.calls.createPayloads[0]), "题数由蓝图定, 前端不传 count");
  assert.strictEqual(loaded.page.data.stage, "quiz");
  assert.strictEqual(loaded.page.data.totalCount, 8);

  // 答满 5 道计分题: 不触发
  for (var i = 0; i < 5; i++) {
    answerCurrent(loaded.page);
    await flushTimers();
  }
  assert.strictEqual(loaded.page.data.stage, "quiz", "5 题不触发检查点");
  // 第 6 道计分题 → 检查点
  answerCurrent(loaded.page);
  await flushTimers();
  assert.strictEqual(loaded.page.data.stage, "checkpoint", "第 6 题后进入检查点屏");
  var checkpoint = loaded.page.data.checkpoint;
  assert.strictEqual(checkpoint.coverageLabel, "证据覆盖：低");
  assert.strictEqual(checkpoint.cta, "再答 6 题：收窄分数带 + 定位失分采分点");
  assert.strictEqual(checkpoint.bandLine, "", "服务端未给粗带字段则不渲染粗带数值");

  // 唯一 CTA → 回到第一道未答题, 不再二次打断
  loaded.page.onCheckpointContinue();
  assert.strictEqual(loaded.page.data.stage, "quiz");
  assert.strictEqual(loaded.page.data.currentQ.id, "c1", "回到第一道未答题");
  answerCurrent(loaded.page, "A");
  await flushTimers();
  assert.strictEqual(loaded.page.data.stage, "quiz", "检查点只出现一次");

  // ── checkpoint_after 缺失 → 永不打断 ──
  var noCp = loadPage({ createResponse: { checkpoint_after: undefined } });
  noCp.page.onLoad({});
  await flushPromises();
  for (var j = 0; j < 6; j++) {
    answerCurrent(noCp.page);
    await flushTimers();
  }
  assert.strictEqual(noCp.page.data.stage, "quiz", "checkpoint_after 缺失时禁前端写死 6");

  // ── 4. resume: 草稿在 → 走服务端 resume, 冲突服务端赢 ──
  var resumed = loadPage({
    resumeResponse: {
      quiz_id: "quiz_pr_exam",
      checkpoint_after: 6,
      scored_count: 12,
      profile_count: 3,
      questions: buildQuestions(),
      draft_answer_snapshot: { s1: "B" },
    },
  });
  resumed.calls.ownerStorage["deeptutor.passReadiness.draft"] = {
    quizId: "quiz_pr_exam",
    selectedKeys: { s1: "A", s2: "A" },
    currentIndex: 1,
    checkpointSeen: false,
  };
  resumed.page.onLoad({});
  await flushPromises();
  assert.strictEqual(resumed.calls.resumeCalls.length, 1);
  assert.strictEqual(resumed.calls.createPayloads.length, 0, "可恢复时不再新建");
  assert.strictEqual(resumed.page.data.selectedKeys.s1, "B", "同题冲突服务端赢");
  assert.strictEqual(resumed.page.data.selectedKeys.s2, "A", "服务端没有的题保留本地");
  assert.strictEqual(resumed.page.data.currentIndex, 1);

  // ── 5. 提交 wire + 清草稿 + 存报告 + redirect ──
  var toSubmit = loadPage({ createResponse: { checkpoint_after: 0 } });
  toSubmit.page.onLoad({});
  await flushPromises();
  for (var k = 0; k < 6; k++) {
    answerCurrent(toSubmit.page);
    await flushTimers();
  }
  // c1 是多选(不自动跳题): 答完手动进入下一题
  answerCurrent(toSubmit.page, "A");
  toSubmit.page.onNext();
  answerCurrent(toSubmit.page, "A");
  await flushTimers();
  toSubmit.page.onSubmit();
  await flushPromises();
  assert.strictEqual(toSubmit.calls.modals.length, 0, "全答完不弹确认");
  assert.strictEqual(toSubmit.calls.submitPayloads.length, 1);
  var submitted = toSubmit.calls.submitPayloads[0];
  assert.strictEqual(submitted.quizId, "quiz_pr_exam");
  Object.keys(submitted.answers).forEach(function (qId) {
    assert.strictEqual(typeof submitted.answers[qId], "string", "wire 必须 dict[str,str]");
    assert.ok(/^[A-Z]+$/.test(submitted.answers[qId]), "wire 值必须是字母");
  });
  assert.strictEqual(Object.keys(submitted.answers).length, 8);
  assert.strictEqual(
    toSubmit.calls.ownerStorage["deeptutor.passReadiness.draft"],
    null,
    "提交成功必须清草稿",
  );
  var storedReport = toSubmit.calls.ownerStorage["deeptutor.passReadiness.lastReport"];
  assert.ok(storedReport && storedReport.quizId === "quiz_pr_exam", "报告快照落 owner storage");
  assert.strictEqual(toSubmit.calls.redirects.length, 1);
  assert.ok(toSubmit.calls.redirects[0].indexOf("report?quiz_id=quiz_pr_exam") >= 0);

  console.log("PASS test_pass_readiness_exam_contract.js");
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
