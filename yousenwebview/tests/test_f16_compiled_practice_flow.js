// Run: node yousenwebview/tests/test_f16_compiled_practice_flow.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function setPath(target, key, value) {
  var match = /^items\[(\d+)\]\.(.+)$/.exec(key);
  if (!match) {
    target[key] = value;
    return;
  }
  target.items[Number(match[1])][match[2]] = value;
}

function items(packId) {
  return [0, 1, 2, 3, 4].map(function (index) {
    return {
      answer_type: "single_choice",
      variant_id: packId + "-q" + (index + 1),
      rule_group: "维度" + (index + 1),
      stem: "第" + (index + 1) + "题",
      anchor: "compiled_html:" + packId.toLowerCase() + "#Q" + (index + 1),
      options: [
        { option_id: "q" + (index + 1) + ":a", text: "选项A" },
        { option_id: "q" + (index + 1) + ":b", text: "选项B" },
      ],
    };
  });
}

function loadPage(options) {
  options = options || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = { complete: [], items: [], telemetry: [] };
  var ownerDraft = options.ownerDraft || null;
  var api = {
    getLubanRetestItems: function (packId, _limit, _mode, opts) {
      calls.items.push(opts || {});
      var receipt = String((opts && opts.projectionReceipt) || options.projectionReceipt || ("projection-" + packId));
      var response = {
        items: items(packId),
        day_index: 2026194,
        selection_id: options.selectionId || "signed-five",
        practice_source: "compiled_html",
        projection_receipt: receipt,
        projection_digest: "digest-" + packId,
        pool: { core_total: 5, rule_groups_total: 5 },
      };
      if (options.omitProjection) {
        delete response.projection_receipt;
        delete response.projection_digest;
      }
      return Promise.resolve(response);
    },
    completeLubanRetest: function (_packId, payload) {
      calls.complete.push(payload);
      if (options.rejectCompletion) return Promise.reject(options.rejectCompletion);
      if (options.rejectCompletionOnce && calls.complete.length === 1) {
        return Promise.reject(options.rejectCompletionOnce);
      }
      var response = {
        terminal_event_id: "evt-terminal",
        learning_change: { status: "practice_recorded" },
        score: { correct_count: 3, question_count: 5 },
        items: payload.answers.map(function (answer, index) {
          return {
            variant_id: answer.variant_id,
            is_correct: index < 3,
            correct_statement: "服务端解析" + (index + 1),
            feedback: { fix: "按服务端解析修正" },
          };
        }),
      };
      if (options.omitLearningChange) delete response.learning_change;
      return Promise.resolve(response);
    },
    unwrapResponse: function (value) { return value; },
    describeRequestError: function (_error, fallback) { return fallback; },
    errorCodeOf: function (error) { return String((error && error.message) || ""); },
  };
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../../utils/api") return api;
      if (request === "../../../utils/surface-telemetry") {
        return {
          trackProductBehavior: function (name, payload) {
            calls.telemetry.push({ name: name, payload: payload });
          },
        };
      }
      if (request === "../../../utils/helpers") return { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, isDark: function () { return false; } };
      if (request === "../../../utils/auth") {
        return {
          getUserId: function () { return "student-a"; },
          readOwnerStorage: function () { return ownerDraft; },
          writeOwnerStorage: function (_key, value) { ownerDraft = value; return true; },
          removeOwnerStorage: function () { ownerDraft = null; return true; },
        };
      }
      if (request === "../../../utils/route") {
        return { lubanConceptCards: function () { return "/packageDeeptutor/pages/luban/concept-cards/concept-cards"; } };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
      getStorageSync: function () { return null; },
      setStorageSync: function () {},
    },
    Page: function (definition) { pageDef = definition; },
  };
  vm.runInNewContext(source, sandbox, { filename: "retest.js" });
  var page = {
    data: JSON.parse(JSON.stringify(pageDef.data)),
    setData: function (patch) {
      var that = this;
      Object.keys(patch || {}).forEach(function (key) { setPath(that.data, key, patch[key]); });
    },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls, ownerDraft: function () { return ownerDraft; } };
}

async function answerFive(setup) {
  for (var index = 0; index < 5; index++) {
    setup.page.onOptionTap({
      currentTarget: { dataset: { index: index, optionId: "q" + (index + 1) + ":b" } },
    });
    if (index < 4) setup.page.nextQuestion();
  }
  await flush();
  await flush();
}

(async function main() {
  var setup = loadPage();
  setup.page.onLoad({ pack_id: "N01", mode: "forward" });
  await flush();
  assert.strictEqual(setup.page.data.total, 5);
  assert.strictEqual(setup.page.data.practiceSource, "compiled_html");
  assert.strictEqual(setup.page.data.items[0].expected_ok, null, "client must not receive an answer bit");

  await answerFive(setup);
  assert.strictEqual(setup.calls.complete.length, 1);
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(setup.calls.complete[0].answers)),
    [0, 1, 2, 3, 4].map(function (index) {
      return { variant_id: "N01-q" + (index + 1), selected_option_id: "q" + (index + 1) + ":b" };
    }),
  );
  assert.strictEqual(setup.page.data.correctCount, 3, "receipt score must use server rescore");
  assert.strictEqual(setup.page.data.terminalEventId, "evt-terminal");
  assert.strictEqual(setup.page.data.showReceipt, true);
  assert.strictEqual(setup.page.data.receiptStateText, "已练过 · 待验证");
  assert.ok(setup.page.data.receiptNextText.indexOf("不等于已经掌握") >= 0);

  var bridgeAnswers = ["b", "a", "b", "a", "b"].map(function (letter, index) {
    return { variant_id: "S05-q" + (index + 1), selected_option_id: "q" + (index + 1) + ":" + letter };
  });
  var bridged = loadPage();
  bridged.page.onLoad({
    pack_id: "S05",
    mode: "forward",
    presentation: "receipt",
    practice_surface: "practice.html",
    projection_receipt: "projection-S05",
    answers: JSON.stringify(bridgeAnswers),
  });
  await flush();
  await flush();
  assert.strictEqual(bridged.page.data.bridgeMode, true);
  assert.strictEqual(bridged.page.data.practiceSurface, "practice.html");
  assert.strictEqual(bridged.calls.items[0].practiceSurface, "practice.html");
  assert.strictEqual(bridged.calls.items[0].projectionReceipt, "projection-S05");
  assert.strictEqual(bridged.calls.complete.length, 1, "finished HTML answers must auto-submit without a second quiz");
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(bridged.calls.complete[0].answers)),
    bridgeAnswers,
  );
  assert.strictEqual(bridged.page.data.showReceipt, true);

  var invalidBridge = loadPage();
  invalidBridge.page.onLoad({ pack_id: "X01", mode: "forward", presentation: "receipt", projection_receipt: "projection-X01", answers: "[]" });
  assert.ok(invalidBridge.page.data.errorText.indexOf("题目内容已更新") >= 0);
  assert.strictEqual(invalidBridge.calls.complete.length, 0);

  var offline = loadPage({ rejectCompletion: new Error("offline"), omitProjection: true });
  offline.page.onLoad({ pack_id: "X01", mode: "forward" });
  await flush();
  await answerFive(offline);
  assert.strictEqual(offline.page.data.syncStatus, "error");
  assert.strictEqual(offline.page.data.showReceipt, false, "failed write must never look complete");
  assert.strictEqual(offline.page.data.terminalEventId, "");
  assert.ok(offline.ownerDraft(), "offline exact receipt and answers must be owner-scoped for restart");

  var restarted = loadPage({ ownerDraft: offline.ownerDraft(), omitProjection: true });
  restarted.page.onLoad({ pack_id: "X01", mode: "forward" });
  await flush();
  await flush();
  assert.strictEqual(restarted.calls.complete.length, 1, "exact same projection must resume and retry after restart");
  assert.strictEqual(
    restarted.calls.complete[0].completion_id,
    offline.calls.complete[0].completion_id,
    "restart must preserve completion identity for the same exact draft",
  );
  assert.strictEqual(restarted.page.data.showReceipt, true);

  var changedSupply = loadPage({
    ownerDraft: offline.ownerDraft(),
    omitProjection: true,
    selectionId: "signed-five-after-supply-change",
  });
  changedSupply.page.onLoad({ pack_id: "X01", mode: "forward" });
  await flush();
  assert.strictEqual(changedSupply.page.data.answeredCount, 0, "new signed selection must clear stale answers");
  assert.strictEqual(changedSupply.calls.complete.length, 0);

  var reviewDraft = {
    projection_receipt: "",
    projection_digest: "",
    selection_id: "signed-review",
    completion_id: "review-completion-before-restart",
    answers: [{
      variant_id: "S05-q1",
      selected_option_id: "q1:b",
      choice_ok: false,
      answer_type: "single_choice",
    }],
  };
  var reviewRestart = loadPage({
    ownerDraft: reviewDraft,
    omitProjection: true,
    selectionId: "signed-review",
  });
  reviewRestart.page.onLoad({ pack_id: "S05", mode: "review", probe_id: "probe-S05-d1" });
  await flush();
  assert.strictEqual(reviewRestart.page.data.answeredCount, 1, "ordinary review must restore by exact signed selection");
  assert.strictEqual(reviewRestart.page.data.completionId, "review-completion-before-restart");
  assert.strictEqual(reviewRestart.calls.items[0].probeId, "probe-S05-d1");

  var recovered = loadPage({ rejectCompletionOnce: new Error("offline-once") });
  recovered.page.onLoad({ pack_id: "S05", mode: "forward" });
  await flush();
  await answerFive(recovered);
  assert.strictEqual(recovered.page.data.syncStatus, "error");
  recovered.page.retryCompletion();
  await flush();
  await flush();
  assert.strictEqual(recovered.page.data.showReceipt, true);
  assert.strictEqual(recovered.calls.complete.length, 2);
  assert.strictEqual(
    recovered.calls.complete[0].completion_id,
    recovered.calls.complete[1].completion_id,
    "retry must preserve the completion identity",
  );
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(recovered.calls.complete[0].answers)),
    JSON.parse(JSON.stringify(recovered.calls.complete[1].answers)),
    "retry must preserve the same five answers",
  );

  var missingChange = loadPage({ omitLearningChange: true });
  missingChange.page.onLoad({ pack_id: "N01", mode: "forward" });
  await flush();
  await answerFive(missingChange);
  assert.strictEqual(missingChange.page.data.syncStatus, "error");
  assert.strictEqual(missingChange.page.data.showReceipt, false, "receipt needs the canonical learning-change projection");

  console.log("PASS test_f16_compiled_practice_flow.js");
})().catch(function (error) {
  console.error(error);
  process.exit(1);
});
