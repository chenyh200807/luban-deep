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

function items() {
  return [0, 1, 2, 3, 4].map(function (index) {
    return {
      answer_type: "single_choice",
      variant_id: "F16-q" + (index + 1),
      rule_group: "维度" + (index + 1),
      stem: "第" + (index + 1) + "题",
      anchor: "compiled_html:f16#Q" + (index + 1),
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
  var api = {
    getLubanRetestItems: function (_packId, _limit, _mode, opts) {
      calls.items.push(opts || {});
      return Promise.resolve({
        items: items(),
        day_index: 2026194,
        selection_id: "signed-five",
        practice_source: "compiled_html",
        pool: { core_total: 5, rule_groups_total: 5 },
      });
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
      if (request === "../../../utils/helpers") return { isDark: function () { return false; } };
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
  return { page: page, calls: calls };
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
  setup.page.onLoad({ pack_id: "F16", mode: "forward" });
  await flush();
  assert.strictEqual(setup.page.data.total, 5);
  assert.strictEqual(setup.page.data.practiceSource, "compiled_html");
  assert.strictEqual(setup.page.data.items[0].expected_ok, null, "client must not receive an answer bit");

  await answerFive(setup);
  assert.strictEqual(setup.calls.complete.length, 1);
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(setup.calls.complete[0].answers)),
    [0, 1, 2, 3, 4].map(function (index) {
      return { variant_id: "F16-q" + (index + 1), selected_option_id: "q" + (index + 1) + ":b" };
    }),
  );
  assert.strictEqual(setup.page.data.correctCount, 3, "receipt score must use server rescore");
  assert.strictEqual(setup.page.data.terminalEventId, "evt-terminal");
  assert.strictEqual(setup.page.data.showReceipt, true);
  assert.strictEqual(setup.page.data.receiptStateText, "已练过 · 待验证");
  assert.ok(setup.page.data.receiptNextText.indexOf("不等于已经掌握") >= 0);

  var bridged = loadPage();
  bridged.page.onLoad({
    pack_id: "S01",
    mode: "forward",
    presentation: "receipt",
    practice_surface: "practice2.html",
    answer_indexes: "1,0,1,0,1",
  });
  await flush();
  await flush();
  assert.strictEqual(bridged.page.data.bridgeMode, true);
  assert.strictEqual(bridged.page.data.practiceSurface, "practice2.html");
  assert.strictEqual(bridged.calls.items[0].practiceSurface, "practice2.html");
  assert.strictEqual(bridged.calls.complete.length, 1, "finished HTML answers must auto-submit without a second quiz");
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(bridged.calls.complete[0].answers)),
    ["b", "a", "b", "a", "b"].map(function (letter, index) {
      return { variant_id: "F16-q" + (index + 1), selected_option_id: "q" + (index + 1) + ":" + letter };
    }),
  );
  assert.strictEqual(bridged.page.data.showReceipt, true);

  var invalidBridge = loadPage();
  invalidBridge.page.onLoad({ pack_id: "F16", mode: "forward", presentation: "receipt", answer_indexes: "1,0" });
  assert.ok(invalidBridge.page.data.errorText.indexOf("答案传递无效") >= 0);
  assert.strictEqual(invalidBridge.calls.complete.length, 0);

  var offline = loadPage({ rejectCompletion: new Error("offline") });
  offline.page.onLoad({ pack_id: "F16", mode: "forward" });
  await flush();
  await answerFive(offline);
  assert.strictEqual(offline.page.data.syncStatus, "error");
  assert.strictEqual(offline.page.data.showReceipt, false, "failed write must never look complete");
  assert.strictEqual(offline.page.data.terminalEventId, "");

  var recovered = loadPage({ rejectCompletionOnce: new Error("offline-once") });
  recovered.page.onLoad({ pack_id: "F16", mode: "forward" });
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
  missingChange.page.onLoad({ pack_id: "F16", mode: "forward" });
  await flush();
  await answerFive(missingChange);
  assert.strictEqual(missingChange.page.data.syncStatus, "error");
  assert.strictEqual(missingChange.page.data.showReceipt, false, "receipt needs the canonical learning-change projection");

  console.log("PASS test_f16_compiled_practice_flow.js");
})().catch(function (error) {
  console.error(error);
  process.exit(1);
});
