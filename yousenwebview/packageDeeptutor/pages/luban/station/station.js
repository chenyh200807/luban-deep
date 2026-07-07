// 鲁班学习双轮 · 站点页（spike 形态）
// 两幕切换：幕1 web-view 加载 card_url（讲懂）→ 幕2 web-view 加载 practice url（闯关）
// → 跳 handoff 交接页。practice url = card_url 把结尾 lesson.html 换成 practice.html。
//
// 已知结构性 caveat（spike 先按设计稿实现，不硬编绕过）：
// 微信 web-view 会自动铺满整个页面并覆盖其他原生组件——底部原生按钮在
// DevTools 模拟器可见，真机上可能被 web-view 盖住。若真机验证不可用，
// 后续方案 = 卡内 wx.miniProgram.navigateTo 桥接，或原生壳 + navigateTo 分幕。
//
// 零学习证据写入：本页只做投影消费 + telemetry，不写任何掌握态/学习证据接口。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 站进入 = module_viewed（object_type=station, object_id=pack_id）
// - 幕/档位切换 = learning_action_started（action=start_training,
//   object_id="<pack>:<tier>"）
const api = require("../../../utils/api");
const telemetry = require("../../../utils/surface-telemetry");

var TIER_LESSON = "lesson";
var TIER_PRACTICE = "practice";

function practiceUrlFrom(cardUrl) {
  var url = String(cardUrl || "");
  if (!/lesson\.html$/.test(url)) return "";
  return url.replace(/lesson\.html$/, "practice.html");
}

Page({
  data: {
    packId: "",
    title: "",
    loading: true,
    errorText: "",
    tier: TIER_LESSON, // "lesson" | "practice"
    currentUrl: "",
    cardUrl: "",
    practiceUrl: "",
  },

  onLoad(query) {
    var packId = String((query && query.pack_id) || "").trim();
    this.setData({ packId: packId });
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

  // 底部常驻按钮：幕1「看完了，去闯关」→ 幕2「闯关完成」→ handoff
  onPrimaryTap() {
    if (this.data.tier === TIER_LESSON) {
      this._enterTier(TIER_PRACTICE);
      return;
    }
    if (typeof wx !== "undefined" && wx.redirectTo) {
      wx.redirectTo({
        url:
          "/packageDeeptutor/pages/luban/handoff/handoff?pack_id=" +
          encodeURIComponent(this.data.packId),
      });
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
        that.setData({
          title: String(body.title || ""),
          cardUrl: cardUrl,
          practiceUrl: practiceUrlFrom(cardUrl),
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
