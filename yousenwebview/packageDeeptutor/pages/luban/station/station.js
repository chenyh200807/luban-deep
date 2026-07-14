// 鲁班学习双轮 · 站点页（spike 形态）
// 统一路径：finished 成品讲懂 → finished 成品五题随堂练 → 服务端复核收据。
//
// 已知结构性 caveat（spike 先按设计稿实现，不硬编绕过）：
// 微信 web-view 会自动铺满整个页面并覆盖其他原生组件——底部原生按钮在
// DevTools 模拟器可见，真机上可能被 web-view 盖住。若真机验证不可用，
// 成品卡内负责将同一轮作答交给原生收据页；底栏只做 fallback。
//
// 学-evidence 上报（融合计划 §2.1）：讲懂幕看完 → lesson_viewed（唯一 writer
// /api/v1/lesson-progress，后端 progress_countable=false/exposed，绝不算掌握 M0）。
// 除此之外仍零学习证据写入：掌握态/判分归判分链路，本页不碰。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 站进入 = module_viewed（object_type=station, object_id=pack_id）
// - 幕/档位切换 = learning_action_started（action=start_training,
//   object_id="<pack>:<tier>"）
const api = require("../../../utils/api");
const telemetry = require("../../../utils/surface-telemetry");
const helpers = require("../../../utils/helpers");

var TIER_LESSON = "lesson";
var TIER_PRACTICE = "practice";

Page({
  data: {
    packId: "",
    isDark: false,
    title: "",
    loading: true,
    errorText: "",
    tier: TIER_LESSON,
    currentUrl: "",
    cardUrl: "",
    practiceUrl: "",
    cardSha: "",
    _lessonReported: false, // 客户端去重(后端亦按业务日 dedupe)
  },

  onLoad(query) {
    var packId = String((query && query.pack_id) || "").trim();
    this.setData({ packId: packId, isDark: false /* 第10版主色=宣纸亮,默认亮色;夜宣纸暗版 wxss 仍在 */ });
    // 站进入（任务稿 luban_station_enter 的登记名）
    telemetry.trackProductBehavior("module_viewed", {
      module: "learning",
      action: "view",
      objectType: "station",
      objectId: packId,
    });
    if (!packId) {
      this.setData({ loading: false, errorText: "缺少站点参数，请从提分路线进入" });
      return;
    }
    this._loadDetail();
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._loadDetail();
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

  // 看完讲解进入同 pack 的 finished 成品随堂练。
  onPrimaryTap() {
    if (this.data.tier === TIER_LESSON) {
      // 融合计划 §2.1:讲懂幕看完 = lesson_viewed 学-evidence(唯一 writer)。
      this._reportLessonViewed();
      if (!this.data.practiceUrl) {
        this.setData({ errorText: "成品练习版本校验失败，请稍后再试" });
        return;
      }
      this._enterTier(TIER_PRACTICE);
      return;
    }
    // 必须由成品结果页提交同一轮答案，禁止绕过题目直接产生完成态。
  },

  _reportLessonViewed() {
    if (this.data._lessonReported || !this.data.packId) return;
    this.setData({ _lessonReported: true });
    var packId = this.data.packId;
    // fire-and-forget 但绝不静默吞：失败必留 console 痕迹（真机验收可观测）。
    try {
      var p = api.postLessonProgress(packId, TIER_LESSON, this.data.cardSha, { silent: true });
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          console.warn("[station] lesson_viewed 上报失败(不打断学习流)", packId, err);
        });
      }
    } catch (e) {
      console.warn("[station] lesson_viewed 上报异常(不打断学习流)", packId, e);
    }
  },

  _enterTier(tier) {
    var url = tier === TIER_PRACTICE ? this.data.practiceUrl : this.data.cardUrl;
    this.setData({ tier: tier, currentUrl: url });
    // 幕/档位切换（任务稿 luban_practice_tier 的登记名）
    telemetry.trackProductBehavior("learning_action_started", {
      module: "learning",
      action: "start_training",
      objectType: "station",
      objectId: this.data.packId + ":" + tier,
    });
  },

  _loadDetail() {
    var that = this;
    return api
      .getLubanLessonDetail(this.data.packId)
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var cardUrl = String(body.card_url || "");
        if (!cardUrl) {
          that.setData({
            title: String(body.title || ""),
            loading: false,
            errorText: "这一站微课即将开通",
          });
          return;
        }
        var practiceUrl = String(body.practice_url || "");
        that.setData({
          title: String(body.title || ""),
          cardUrl: cardUrl,
          practiceUrl: practiceUrl,
          cardSha: String(body.content_sha256 || ""),
          loading: false,
          errorText: "",
        });
        that._enterTier(TIER_LESSON);
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "站点加载失败，请稍后重试"),
        });
      });
  },
});
