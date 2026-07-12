// 鲁班学习双轮 · 变体复测（spike 形态）
// 拉 /retest-items（服务端确定性抽取 + selection identity）→ 本地只给即时反馈；
// 全题完成后 POST /retest-complete，由服务端按签发池重判并提交唯一 terminal。
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

var RETEST_LIMIT = 5;

// 两种取题模式共用本页（复用同一 retest 页/内核，不建第二答题页）：
// - review（默认，复习轮换皮复测）；
// - forward（学习轮 2 分钟正向轻练，对刚学完 pack 覆盖不同 rule_group 取一组）。
// 差别只在题面选序（后端 build_retest_items(mode) 决定）+ 文案，判分/证据链路完全一致：
// 本地反馈（选择==expected_ok）不具 truth authority；服务端 completion 是唯一判分/写回入口。
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
    navTitle: "2 分钟轻练",
    heroKicker: "刚学完，趁热练一练",
    heroTitle: "这一考点的不同考法，你能答对几道",
    loadingText: "正在给你抽题…",
    emptyText: "这一站的轻练题即将开通，先去把它讲懂。",
    doneTitlePrefix: "轻练完成",
    doneDesc: "轻练结果已保存；何时再练以复习页的服务端排程为准。",
  },
};

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
    mode: "review",
    probeId: "",
    trainingIntentId: "",
    dayIndex: 0,
    selectionId: "",
    completionId: "",
    syncStatus: "idle",
    syncError: "",
    terminalEventId: "",
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
      mode: mode,
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
        url: "/packageDeeptutor/pages/luban/stations/stations",
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
      this._submitCompletion(all, correctCount);
    }
  },

  // 本地"已见变体"集合(收集感, 呈现层非学情): 读旧集合并入本场
  _seenCount(items) {
    var key = "luban_retest_seen:" + (this.data.packId || "");
    var seen = [];
    try {
      if (typeof wx !== "undefined" && wx.getStorageSync) {
        var raw = wx.getStorageSync(key);
        if (raw && Array.isArray(raw.ids)) seen = raw.ids;
      }
    } catch (_e) {}
    var set = {};
    seen.forEach(function (id) { set[id] = true; });
    (items || []).forEach(function (it) { set[it.variant_id] = true; });
    var ids = Object.keys(set);
    try {
      if (typeof wx !== "undefined" && wx.setStorageSync) {
        wx.setStorageSync(key, { ids: ids, at: Date.now() });
      }
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
    this._submitCompletion(all, this.data.correctCount);
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

  _submitCompletion(items, correctCount) {
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
          return { variant_id: item.variant_id, choice_ok: item.chosenOk === true };
        }),
      })
      .then(function (response) {
        var body = api.unwrapResponse(response) || response || {};
        var terminalEventId = String(body.terminal_event_id || "").trim();
        if (!terminalEventId) throw new Error("canonical terminal receipt missing");
        telemetry.trackProductBehavior("learning_action_completed", {
          module: "practice",
          action: "complete",
          objectType: "retest",
          objectId: that.data.packId,
          result: correctCount + "/" + that.data.total,
          practiceMode: that.data.mode,
        });
        that.setData({
          syncStatus: "synced",
          syncError: "",
          terminalEventId: terminalEventId,
          done: true,
          showReceipt: true,
        });
      })
      .catch(function (err) {
        that.setData({
          syncStatus: "error",
          syncError: api.describeRequestError(err, "保存失败，请重试后再查看收据"),
        });
      });
  },

  _loadItems() {
    var that = this;
    return api
      .getLubanRetestItems(this.data.packId, RETEST_LIMIT, this.data.mode)
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var raw = Array.isArray(body.items) ? body.items : [];
        var pool = body.pool && body.pool.core_total ? body.pool : null;
        var items = raw.map(function (item, idx) {
          return {
            key: String(item.variant_id || "v_" + idx),
            variant_id: item.variant_id,
            rule_group: item.rule_group,
            surface: item.surface,
            expected_ok: Boolean(item.expected_ok),
            correct_statement: item.correct_statement,
            anchor: item.anchor,
            textbook: item.textbook || null, // 教材原文并排卡(join 命中才有, 前端零造词)
            answered: false,
            correct: null,
            chosenOk: null,
          };
        });
        that.setData({
          pool: pool,
          dayIndex: Number(body.day_index || 0),
          selectionId: String(body.selection_id || ""),
          seenCount: that._seenCount(items),
          items: items,
          total: items.length,
          answeredCount: 0,
          correctCount: 0,
          done: false,
          currentIndex: 0,
          showReceipt: false,
          wrongItems: [],
          ruleGroupCount: 0,
          textbookCount: 0,
          loading: false,
          errorText: "",
          syncStatus: "idle",
          syncError: "",
        });
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "复测题加载失败，请稍后重试"),
        });
      });
  },
});
