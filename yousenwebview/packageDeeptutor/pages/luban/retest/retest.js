// 鲁班学习双轮 · 变体复测（spike 形态）
// 拉 /retest-items（服务端确定性抽取）→ 逐题判断题本地判分（选择==expected_ok，
// 档位①确定性判分，D5 离线可用）。复测结果只进 telemetry——
// 零学习证据/掌握态写入（学习证据归 learner_signal / 判分链路）。
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
// 本地确定性判分（选择==expected_ok）+ 完成发 station_completed（非 promoting）。
var COPY = {
  review: {
    navTitle: "换皮复测",
    heroKicker: "昨天的考点，换了一身皮",
    heroTitle: "看看你能不能一眼认出它",
    loadingText: "正在取今天的题…",
    emptyText: "今天这一站暂时没有复测题，明天再来。",
    doneTitlePrefix: "今天的回炉完成",
    doneDesc: "这个考点在你这儿越来越稳了。明天见。",
  },
  forward: {
    navTitle: "2 分钟轻练",
    heroKicker: "刚学完，趁热练一练",
    heroTitle: "这一考点的不同考法，你能答对几道",
    loadingText: "正在给你抽题…",
    emptyText: "这一站的轻练题即将开通，先去把它讲懂。",
    doneTitlePrefix: "轻练完成",
    doneDesc: "先热了个身。明天这个考点会换身皮再来考你一次，明天见。",
  },
};

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
    mode: "review",
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
    var copy = COPY[mode];
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDark(),
      packId: packId,
      mode: mode,
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
    var done = answeredCount >= this.data.total && this.data.total > 0;
    var patch = {
      answeredCount: answeredCount,
      correctCount: correctCount,
      done: done,
    };
    patch["items[" + index + "].answered"] = true;
    patch["items[" + index + "].correct"] = correct;
    patch["items[" + index + "].chosenOk"] = choiceOk;
    this.setData(patch);

    if (done) {
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
      // 复测终态本地记录: 错因银行呈现层销账用(本地 storage, 非学情真值,
      // 不写掌握态——掌握结论只归 learner truth 链路)
      if (typeof wx !== "undefined" && wx.setStorageSync) {
        try {
          wx.setStorageSync("luban_retest_last:" + (this.data.packId || ""), {
            correct: correctCount,
            total: this.data.total,
            at: Date.now(),
          });
        } catch (_err) {}
      }
      // 复测完成 → 站完成信号(非 promoting, 重排下一跳到期; 旗标关=服务端拒收, 静默)
      api.postStationCompleted(this.data.packId || "", "").catch(function () {});
      // 变体练完成（任务稿 luban_retest_complete 的登记名）
      // practice_mode 判别位（spike 命门）：D1 留存 = 人次日回来做 review 换皮复测,
      // 必须能从 forward(当天轻练)里分出来,否则 GO/NO-GO 判不了。
      telemetry.trackProductBehavior("learning_action_completed", {
        module: "practice",
        action: "complete",
        objectType: "retest",
        objectId: this.data.packId,
        result: correctCount + "/" + this.data.total,
        practiceMode: this.data.mode,
      });
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
      this.setData({ showReceipt: true });
      return;
    }
    this.setData({ currentIndex: next });
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
