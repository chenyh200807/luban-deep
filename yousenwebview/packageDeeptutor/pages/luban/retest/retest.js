// 鲁班学习双轮 · 变体复测（spike 形态）
// 拉 /retest-items（服务端确定性投影 + selection identity）→ 客户端只回传选择；
// 全题完成后 POST /retest-complete，由服务端按 canonical 内容源重判并提交唯一 terminal。
// 页面不写 learner state、不发 station_completed；保存失败不展示收据。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 每题作答 = retest_item_answered（module=practice, action=complete,
//   object_type=variant, object_id=variant_id, result=correct|incorrect）
// - 全部答完 = learning_action_completed（object_type=retest,
//   object_id=pack_id, result="<correct>/<total>"）
const api = require("../../../utils/api");
const telemetry = require("../../../utils/surface-telemetry");
const helpers = require("../../../utils/helpers");
const route = require("../../../utils/route");
const auth = require("../../../utils/auth");

var RETEST_LIMIT = 5;

function parseBridgeReceipt(query, mode) {
  if (mode !== "forward" || String((query && query.presentation) || "") !== "receipt") {
    return { requested: false, projectionReceipt: "", answers: [] };
  }
  var projectionReceipt = String((query && query.projection_receipt) || "").trim();
  var raw = String((query && query.answers) || "").trim();
  try {
    var answers = JSON.parse(raw);
    var variantIds = {};
    if (
      !projectionReceipt ||
      !Array.isArray(answers) ||
      answers.length !== RETEST_LIMIT ||
      answers.some(function (answer) {
        var variantId = String((answer && answer.variant_id) || "").trim();
        var optionId = String((answer && answer.selected_option_id) || "").trim();
        if (!variantId || !optionId || variantIds[variantId]) return true;
        variantIds[variantId] = true;
        return false;
      })
    ) return null;
    return { requested: true, projectionReceipt: projectionReceipt, answers: answers };
  } catch (_error) {
    return null;
  }
}

// 两种取题模式共用本页（复用同一 retest 页/内核，不建第二答题页）：
// - review（默认，复习轮换皮复测）；
// - forward（学习轮五题轻练；有 finished 供给的题面/答案来自 compiled HTML）。
// review 旧判断题保留即时呈现；forward 单选不下发答案，服务端 completion 是唯一判分/写回入口。
var COPY = {
  review: {
    navTitle: "换皮复测",
    heroKicker: "昨天的考点，换了一身皮",
    heroTitle: "看看你能不能一眼认出它",
    loadingText: "正在取今天的题…",
    emptyText: "今天这一站暂时没有复测题，明天再来。",
    doneTitlePrefix: "今天的回炉完成",
    doneDesc: "本轮结果已保存，系统会按你的复习节奏再次安排。",
  },
  forward: {
    navTitle: "课后轻练 · 5 题",
    heroKicker: "刚学完，用五题把它钉牢",
    heroTitle: "条件、工序、纠错、检查、诊断各来一题",
    loadingText: "正在给你抽题…",
    emptyText: "这一站的轻练题即将开通，先去把它讲懂。",
    doneTitlePrefix: "这 5 题已记下",
    doneDesc: "这次先记为已练过；是否稳定，等下一次换皮复测。",
  },
};

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
    practiceSurface: "",
    mode: "review",
    probeId: "",
    trainingIntentId: "",
    dayIndex: 0,
    selectionId: "",
    completionId: "",
    syncStatus: "idle",
    syncError: "",
    terminalEventId: "",
    receiptSyncText: "",
    receiptStateText: "",
    receiptNextText: "",
    navTitle: COPY.review.navTitle,
    heroKicker: COPY.review.heroKicker,
    heroTitle: COPY.review.heroTitle,
    loadingText: COPY.review.loadingText,
    emptyText: COPY.review.emptyText,
    doneTitlePrefix: COPY.review.doneTitlePrefix,
    doneDesc: COPY.review.doneDesc,
    loading: true,
    errorText: "",
    items: [],
    total: 0,
    pool: null,          // 题池元信息 {core_total, rule_groups_total}(呈现层规模感)
    practiceSource: "signed_variant",
    bridgeMode: false,
    bridgeProjectionReceipt: "",
    bridgeAnswers: [],
    projectionReceipt: "",
    projectionDigest: "",
    seenCount: 0,        // 本地已见变体数(收集感, storage 呈现层)
    answeredCount: 0,
    correctCount: 0,
    done: false,
    // 单题聚焦流(纸墨版): 当前题指针 + 完场收据
    currentIndex: 0,
    showReceipt: false,
    wrongItems: [],      // 收据"再看一眼"清单(签发 correct_statement 逐字)
    ruleGroupCount: 0,   // 考法覆盖(去重 rule_group 数, 呈现层统计)
    textbookCount: 0,    // 翻出的教材原文句数(join 命中数, 呈现层统计)
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    var packId = String((query && query.pack_id) || "").trim();
    var mode = String((query && query.mode) || "review") === "forward" ? "forward" : "review";
    var practiceSurface = String((query && query.practice_surface) || "").trim();
    var bridgeReceipt = parseBridgeReceipt(query, mode);
    var bridgeRequested = String((query && query.presentation) || "") === "receipt";
    var probeId = String((query && query.probe_id) || "").trim();
    var trainingIntentId = String((query && query.training_intent_id) || "").trim();
    var completionId =
      "retest_" +
      String(packId || "unknown") +
      "_" +
      mode +
      "_" +
      Date.now() +
      "_" +
      Math.random().toString(16).slice(2, 10);
    var copy = COPY[mode];
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDark(),
      packId: packId,
      practiceSurface: practiceSurface,
      mode: mode,
      bridgeMode: bridgeRequested,
      bridgeProjectionReceipt: bridgeReceipt ? bridgeReceipt.projectionReceipt : "",
      bridgeAnswers: bridgeReceipt ? bridgeReceipt.answers : [],
      probeId: probeId,
      trainingIntentId: trainingIntentId,
      completionId: completionId,
      navTitle: copy.navTitle,
      heroKicker: copy.heroKicker,
      heroTitle: copy.heroTitle,
      loadingText: copy.loadingText,
      emptyText: copy.emptyText,
      doneTitlePrefix: copy.doneTitlePrefix,
      doneDesc: copy.doneDesc,
    });
    if (!packId) {
      this.setData({ loading: false, errorText: "缺少站点参数，请从提分路线进入" });
      return;
    }
    if (bridgeRequested && bridgeReceipt === null) {
      this.setData({ loading: false, errorText: "题目内容已更新，请返回重新完成五题" });
      return;
    }
    this._loadItems();
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._loadItems();
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: route.lubanTeachingPoints(),
      });
    }
  },

  // 「这样做妥当」/「不妥当」——本地确定性判分：选择 == expected_ok
  onChoiceTap(event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var choiceOk = dataset.choice === "ok";
    var items = this.data.items;
    if (!Number.isFinite(index) || index < 0 || index >= items.length) return;
    var item = items[index];
    if (!item || item.answered) return;

    var correct = choiceOk === Boolean(item.expected_ok);
    // 每题作答（任务稿 luban_retest_answer 的登记名）
    // practice_mode 判别位（spike 命门）：forward=学习轮当天轻练 / review=复习轮次日复测,
    // 埋点里必须可分,否则 D1 留存(GO 门)读不出。register-before-use catalog 已登记允许值。
    telemetry.trackProductBehavior("retest_item_answered", {
      module: "practice",
      action: "complete",
      objectType: "variant",
      objectId: item.variant_id,
      result: correct ? "correct" : "incorrect",
      practiceMode: this.data.mode,
    });

    var answeredCount = this.data.answeredCount + 1;
    var correctCount = this.data.correctCount + (correct ? 1 : 0);
    var allAnswered = answeredCount >= this.data.total && this.data.total > 0;
    var patch = {
      answeredCount: answeredCount,
      correctCount: correctCount,
      done: false,
    };
    patch["items[" + index + "].answered"] = true;
    patch["items[" + index + "].correct"] = correct;
    patch["items[" + index + "].chosenOk"] = choiceOk;
    this.setData(patch);
    var draftItems = items.slice();
    draftItems[index] = Object.assign({}, item, {
      answered: true,
      correct: correct,
      chosenOk: choiceOk,
    });
    this._persistDraft(draftItems);

    if (allAnswered) {
      // 收据数据(呈现层统计, 全部来自签发字段)
      var all = items.slice();
      all[index] = Object.assign({}, item, { answered: true, correct: correct });
      var groups = {};
      var textbookCount = 0;
      var wrong = [];
      all.forEach(function (it) {
        if (it.rule_group) groups[it.rule_group] = true;
        if (it.textbook) textbookCount += 1;
        if (it.answered && it.correct === false) wrong.push(it);
      });
      this.setData({
        wrongItems: wrong,
        ruleGroupCount: Object.keys(groups).length,
        textbookCount: textbookCount,
      });
      this._submitCompletion(all);
    }
  },

  // 编译 HTML 单选题：客户端只记录 option identity，不持有正确答案。
  onOptionTap(event) {
    var dataset = (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var optionId = String(dataset.optionId || "").trim();
    var items = this.data.items;
    if (!Number.isFinite(index) || index < 0 || index >= items.length || !optionId) return;
    var item = items[index];
    if (!item || item.answered || item.answer_type !== "single_choice") return;
    if (!(item.options || []).some(function (option) { return option.option_id === optionId; })) return;

    var answeredCount = this.data.answeredCount + 1;
    var allAnswered = answeredCount >= this.data.total && this.data.total > 0;
    var patch = { answeredCount: answeredCount, done: false };
    patch["items[" + index + "].answered"] = true;
    patch["items[" + index + "].selectedOptionId"] = optionId;
    this.setData(patch);
    var draftItems = items.slice();
    draftItems[index] = Object.assign({}, item, {
      answered: true,
      selectedOptionId: optionId,
    });
    this._persistDraft(draftItems);
    if (allAnswered) {
      var all = items.slice();
      all[index] = Object.assign({}, item, {
        answered: true,
        selectedOptionId: optionId,
      });
      this._submitCompletion(all);
    }
  },

  _draftKey() {
    return "luban_retest_draft:" + String(this.data.packId || "") + ":" + String(this.data.mode || "review");
  },

  _readDraft() {
    try {
      return auth.readOwnerStorage ? auth.readOwnerStorage(this._draftKey()) : null;
    } catch (_error) {
      return null;
    }
  },

  _persistDraft(items) {
    if (!this.data.selectionId || !auth.writeOwnerStorage) return;
    var answers = (items || this.data.items || [])
      .filter(function (item) { return item && item.answered; })
      .map(function (item) {
        return {
          variant_id: String(item.variant_id || ""),
          selected_option_id: String(item.selectedOptionId || ""),
          choice_ok: item.chosenOk === true,
          answer_type: String(item.answer_type || ""),
        };
      });
    try {
      auth.writeOwnerStorage(this._draftKey(), {
        projection_receipt: this.data.projectionReceipt,
        projection_digest: this.data.projectionDigest,
        selection_id: this.data.selectionId,
        completion_id: this.data.completionId,
        answers: answers,
        updated_at: Date.now(),
      });
    } catch (_error) {}
  },

  _clearDraft() {
    try {
      if (auth.removeOwnerStorage) auth.removeOwnerStorage(this._draftKey());
    } catch (_error) {}
  },

  _restoreDraft(items, selectionId, projectionReceipt, projectionDigest) {
    var draft = this._readDraft();
    if (
      !draft ||
      !selectionId ||
      String(draft.selection_id || "") !== String(selectionId || "") ||
      (
        this.data.bridgeMode &&
        (
          !projectionReceipt ||
          draft.projection_receipt !== projectionReceipt ||
          String(draft.projection_digest || "") !== String(projectionDigest || "")
        )
      ) ||
      !Array.isArray(draft.answers)
    ) {
      if (draft) this._clearDraft();
      return { items: items, completionId: "" };
    }
    var byVariant = {};
    draft.answers.forEach(function (answer) {
      byVariant[String((answer && answer.variant_id) || "")] = answer;
    });
    var restored = items.map(function (item) {
      var answer = byVariant[String(item.variant_id || "")];
      if (!answer) return item;
      if (item.answer_type === "single_choice") {
        var optionId = String(answer.selected_option_id || "");
        if (!(item.options || []).some(function (option) { return option.option_id === optionId; })) return item;
        return Object.assign({}, item, { answered: true, selectedOptionId: optionId });
      }
      return Object.assign({}, item, { answered: true, chosenOk: answer.choice_ok === true });
    });
    return { items: restored, completionId: String(draft.completion_id || "") };
  },

  // 本地"已见变体"集合(收集感, 呈现层非学情): 读旧集合并入本场
  _seenCount(items) {
    var key = "luban_retest_seen:" + (this.data.packId || "");
    var ownerId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    var seen = [];
    try {
      var raw = auth.readOwnerStorage ? auth.readOwnerStorage(key) : null;
      if (raw && Array.isArray(raw.ids)) seen = raw.ids;
    } catch (_e) {}
    var set = {};
    seen.forEach(function (id) { set[id] = true; });
    (items || []).forEach(function (it) { set[it.variant_id] = true; });
    var ids = Object.keys(set);
    try {
      if (ownerId && auth.writeOwnerStorage)
        auth.writeOwnerStorage(key, { ids: ids, at: Date.now() });
    } catch (_e) {}
    return ids.length;
  },

  // 单题流推进: 下一题 / 最后一题 → 今日收据
  nextQuestion() {
    var next = this.data.currentIndex + 1;
    if (next >= this.data.total) {
      if (this.data.syncStatus === "synced") this.setData({ showReceipt: true });
      else if (this.data.syncStatus === "error") this.retryCompletion();
      return;
    }
    this.setData({ currentIndex: next });
  },

  retryCompletion() {
    var all = (this.data.items || []).slice();
    if (!all.length || all.some(function (item) { return !item.answered; })) return;
    this._submitCompletion(all);
  },

  goConceptCards: function () {
    var packId = this.data.packId || "";
    if (!packId) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: route.lubanConceptCards({ pack_id: packId }),
      });
    }
  },

  continueAfterReceipt() {
    // Canonical receipt is already rendered on this page.  Do not hand a
    // terminal truth to another page through forgeable query parameters.
    this.goBack();
  },

  // 收据错项呈现层：按 selectedOptionId 从签发 options 里取所选选项文本。
  // 纯查找零造词；查不到（如判断题无 options）返回空串 → 对应层整行隐藏。
  _selectedOptionText(item) {
    var selectedId = String((item && item.selectedOptionId) || "").trim();
    if (!selectedId) return "";
    var options = (item && item.options) || [];
    for (var i = 0; i < options.length; i++) {
      if (String(options[i].option_id || "") === selectedId) {
        return String(options[i].text || "");
      }
    }
    return "";
  },

  _submitCompletion(items) {
    if (this.data.syncStatus === "syncing" || this.data.syncStatus === "synced") return;
    var that = this;
    this.setData({ syncStatus: "syncing", syncError: "" });
    return api
      .completeLubanRetest(this.data.packId, {
        completion_id: this.data.completionId,
        selection_id: this.data.selectionId,
        mode: this.data.mode,
        day_index: this.data.dayIndex,
        training_intent_id: this.data.trainingIntentId,
        probe_id: this.data.probeId,
        answers: items.map(function (item) {
          if (item.answer_type === "single_choice") {
            return {
              variant_id: item.variant_id,
              selected_option_id: item.selectedOptionId,
            };
          }
          return { variant_id: item.variant_id, choice_ok: item.chosenOk === true };
        }),
      })
      .then(function (response) {
        var body = api.unwrapResponse(response) || response || {};
        var terminalEventId = String(body.terminal_event_id || "").trim();
        if (!terminalEventId) throw new Error("canonical terminal receipt missing");
        var changeStatus = String((body.learning_change || {}).status || "").trim();
        var expectedChange = that.data.mode === "forward"
          ? changeStatus === "practice_recorded"
          : changeStatus === "verification_passed" || changeStatus === "verification_failed";
        if (!expectedChange) throw new Error("canonical learning change missing");
        var serverResults = {};
        (body.items || []).forEach(function (result) {
          serverResults[String(result.variant_id || "")] = result;
        });
        var scoredItems = items.map(function (item) {
          var result = serverResults[item.variant_id] || {};
          var next = Object.assign({}, item, {
            correct: result.is_correct === true,
            correct_statement: String(result.correct_statement || item.correct_statement || ""),
            feedback: result.feedback || null,
          });
          if (item.answer_type === "single_choice") {
            telemetry.trackProductBehavior("retest_item_answered", {
              module: "practice",
              action: "complete",
              objectType: "variant",
              objectId: item.variant_id,
              result: next.correct ? "correct" : "incorrect",
              practiceMode: that.data.mode,
            });
          }
          return next;
        });
        var score = body.score || {};
        var serverCorrectCount = Number(score.correct_count || 0);
        var groups = {};
        var textbookCount = 0;
        var wrong = [];
        scoredItems.forEach(function (item) {
          if (item.rule_group) groups[item.rule_group] = true;
          if (item.textbook) textbookCount += 1;
          if (item.correct === false) {
            wrong.push(Object.assign({}, item, {
              selectedOptionText: that._selectedOptionText(item),
            }));
          }
        });
        telemetry.trackProductBehavior("learning_action_completed", {
          module: "practice",
          action: "complete",
          objectType: "retest",
          objectId: that.data.packId,
          result: serverCorrectCount + "/" + that.data.total,
          practiceMode: that.data.mode,
        });
        that._clearDraft();
        var reviewPassed = changeStatus === "verification_passed";
        that.setData({
          syncStatus: "synced",
          syncError: "",
          terminalEventId: terminalEventId,
          receiptSyncText: "服务器已复核 · 已更新学习记录",
          receiptStateText: that.data.mode === "forward"
            ? "已练过 · 待验证"
            : (reviewPassed ? "复测通过 · 已更新" : "还需巩固 · 已更新"),
          receiptNextText: that.data.mode === "forward"
            ? "本次课后轻练不等于已经掌握；学习页会按记录安排下一次验证。"
            : (reviewPassed ? "这次换皮复测通过，学习页会按记录安排后续验证。" : "本次薄弱点已记录，学习页会继续安排验证。"),
          items: scoredItems,
          correctCount: serverCorrectCount,
          wrongItems: wrong,
          ruleGroupCount: Object.keys(groups).length,
          textbookCount: textbookCount,
          done: true,
          showReceipt: true,
        });
      })
      .catch(function (err) {
        that._persistDraft(items);
        that.setData({
          syncStatus: "error",
          syncError: api.describeRequestError(err, "保存失败，请重试后再查看收据"),
        });
      });
  },

  _loadItems() {
    var that = this;
    return api
      .getLubanRetestItems(this.data.packId, RETEST_LIMIT, this.data.mode, {
        practiceSurface: this.data.practiceSurface,
        projectionReceipt: this.data.bridgeProjectionReceipt,
        probeId: this.data.probeId,
      })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var raw = Array.isArray(body.items) ? body.items : [];
        var practiceSource = String(body.practice_source || "signed_variant");
        var projectionReceipt = String(body.projection_receipt || "").trim();
        var projectionDigest = String(body.projection_digest || "").trim();
        var pool = body.pool && body.pool.core_total ? body.pool : null;
        var items = raw.map(function (item, idx) {
          return {
            key: String(item.variant_id || "v_" + idx),
            variant_id: item.variant_id,
            rule_group: item.rule_group,
            answer_type: item.answer_type || "boolean",
            surface: item.surface,
            stem: item.stem || item.surface,
            options: Array.isArray(item.options) ? item.options : [],
            expected_ok: item.answer_type === "single_choice" ? null : Boolean(item.expected_ok),
            correct_statement: item.correct_statement,
            anchor: item.anchor,
            textbook: item.textbook || null, // 教材原文并排卡(join 命中才有, 前端零造词)
            answered: false,
            correct: null,
            chosenOk: null,
            selectedOptionId: "",
            feedback: null,
          };
        });
        var selectionId = String(body.selection_id || "");
        var restored = that._restoreDraft(
          items, selectionId, projectionReceipt, projectionDigest
        );
        items = restored.items;
        var restoredCount = items.filter(function (item) { return item.answered; }).length;
        var bridgedItems = null;
        if (that.data.bridgeMode) {
          if (
            practiceSource !== "compiled_html" ||
            !projectionReceipt ||
            projectionReceipt !== that.data.bridgeProjectionReceipt ||
            that.data.bridgeAnswers.length !== items.length
          ) {
            throw new Error("content_updated_retake");
          }
          bridgedItems = items.map(function (item, index) {
            var answer = that.data.bridgeAnswers[index] || {};
            var optionId = String(answer.selected_option_id || "");
            if (
              String(answer.variant_id || "") !== String(item.variant_id || "") ||
              !(item.options || []).some(function (option) { return option.option_id === optionId; })
            ) throw new Error("content_updated_retake");
            return Object.assign({}, item, {
              answered: true,
              selectedOptionId: optionId,
            });
          });
          items = bridgedItems;
        }
        that.setData({
          pool: pool,
          practiceSource: practiceSource,
          dayIndex: Number(body.day_index || 0),
          selectionId: selectionId,
          completionId: restored.completionId || that.data.completionId,
          projectionReceipt: projectionReceipt,
          projectionDigest: projectionDigest,
          seenCount: that._seenCount(items),
          items: items,
          total: items.length,
          answeredCount: bridgedItems ? bridgedItems.length : restoredCount,
          correctCount: 0,
          done: false,
          currentIndex: Math.max(0, (bridgedItems ? bridgedItems.length : restoredCount || 1) - 1),
          showReceipt: false,
          wrongItems: [],
          ruleGroupCount: 0,
          textbookCount: 0,
          loading: false,
          errorText: "",
          syncStatus: "idle",
          syncError: "",
          receiptSyncText: "",
          receiptStateText: "",
          receiptNextText: "",
        });
        that._persistDraft(items);
        if (bridgedItems) that._submitCompletion(bridgedItems);
        else if (restoredCount === items.length && items.length > 0) that._submitCompletion(items);
      })
      .catch(function (err) {
        var errorCode = api.errorCodeOf ? api.errorCodeOf(err) : String((err && err.message) || "");
        var contentUpdated = errorCode === "content_updated_retake" || String((err && err.message) || "") === "content_updated_retake";
        if (contentUpdated) that._clearDraft();
        that.setData({
          loading: false,
          errorText: contentUpdated
            ? "题目内容已更新，请返回重新完成五题"
            : api.describeRequestError(err, "复测题加载失败，请稍后重试"),
        });
      });
  },
});
