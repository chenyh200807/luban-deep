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

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
    loading: true,
    errorText: "",
    items: [],
    total: 0,
    answeredCount: 0,
    correctCount: 0,
    done: false,
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    var packId = String((query && query.pack_id) || "").trim();
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDark(),
      packId: packId,
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
    telemetry.trackProductBehavior("retest_item_answered", {
      module: "practice",
      action: "complete",
      objectType: "variant",
      objectId: item.variant_id,
      result: correct ? "correct" : "incorrect",
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
      // 复测完成 → 站完成信号(非 promoting, 重排下一跳到期; 旗标关=服务端拒收, 静默)
      api.postStationCompleted(this.data.packId || "", "").catch(function () {});
      // 复测完成（任务稿 luban_retest_complete 的登记名）
      telemetry.trackProductBehavior("learning_action_completed", {
        module: "practice",
        action: "complete",
        objectType: "retest",
        objectId: this.data.packId,
        result: correctCount + "/" + this.data.total,
      });
    }
  },

  _loadItems() {
    var that = this;
    return api
      .getLubanRetestItems(this.data.packId, RETEST_LIMIT)
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var raw = Array.isArray(body.items) ? body.items : [];
        var items = raw.map(function (item, idx) {
          return {
            key: String(item.variant_id || "v_" + idx),
            variant_id: item.variant_id,
            rule_group: item.rule_group,
            surface: item.surface,
            expected_ok: Boolean(item.expected_ok),
            correct_statement: item.correct_statement,
            anchor: item.anchor,
            answered: false,
            correct: null,
            chosenOk: null,
          };
        });
        that.setData({
          items: items,
          total: items.length,
          answeredCount: 0,
          correctCount: 0,
          done: false,
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
