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
const auth = require("../../../utils/auth");
const route = require("../../../utils/route");
const runtime = require("../../../utils/runtime");
const telemetry = require("../../../utils/surface-telemetry");
const helpers = require("../../../utils/helpers");

var TIER_LESSON = "lesson";
var TIER_PRACTICE = "practice";

function appendCardEntryTicket(cardUrl, ticket) {
  var source = String(cardUrl || "");
  var capability = String(ticket || "").trim();
  if (!source || !capability) return "";
  var hashIndex = source.indexOf("#");
  // A web-view source URL is fetched before its H5 bridge can run. Keep the
  // short-lived capability in the fragment: WebView exposes it to the card,
  // but it is never sent to the static host nor leaked as an asset referrer.
  // Published cards do not use anchors, so an existing fragment is not a
  // competing business input here.
  var base = hashIndex >= 0 ? source.slice(0, hashIndex) : source;
  return base + "#entry_ticket=" + encodeURIComponent(capability);
}

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
    if (!packId) {
      this.setData({ loading: false, errorText: "缺少站点参数，请从提分路线进入" });
      return;
    }
    if (!this._requireAuth()) return;
    // 站进入（任务稿 luban_station_enter 的登记名）
    telemetry.trackProductBehavior("module_viewed", {
      module: "learning",
      action: "view",
      objectType: "station",
      objectId: packId,
    });
    this._loadDetail();
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._loadDetail();
  },

  _requireAuth() {
    if (auth.isLoggedIn()) {
      this._authRedirectPending = false;
      return true;
    }
    if (!this._authRedirectPending) {
      this._authRedirectPending = true;
      runtime.redirectToLogin(route.lubanStation(this.data.packId));
    }
    return false;
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
    if (!this._requireAuth()) return Promise.resolve(false);
    if (this.data.tier === TIER_LESSON) {
      if (!this.data.practiceUrl) {
        this.setData({ errorText: "成品练习版本校验失败，请稍后再试" });
        return Promise.resolve(false);
      }
      // 融合计划 §2.1:讲懂幕看完 = lesson_viewed 学-evidence(唯一 writer)。
      // 服务端判 token 过期时必须先回登录，不能与进入练习幕竞速。
      var that = this;
      return this._reportLessonViewed().then(function (canContinue) {
        if (!canContinue || !that._requireAuth()) return false;
        that._enterTier(TIER_PRACTICE);
        return true;
      });
    }
    // 必须由成品结果页提交同一轮答案，禁止绕过题目直接产生完成态。
    return Promise.resolve(false);
  },

  _reportLessonViewed() {
    if (this.data._lessonReported || !this.data.packId) return Promise.resolve(true);
    this.setData({ _lessonReported: true });
    var packId = this.data.packId;
    var that = this;
    // 只等待身份裁决：普通网络失败不阻断练习，401 则由本页保留 pack 回登录。
    try {
      var p = api.postLessonProgress(packId, TIER_LESSON, this.data.cardSha, {
        silent: true,
        suppressAuthRedirect: true,
      });
      if (p && typeof p.then === "function") {
        return p.then(function () {
          return true;
        }).catch(function (err) {
          that.setData({ _lessonReported: false });
          if (!auth.isLoggedIn()) {
            that._requireAuth();
            return false;
          }
          console.warn("[station] lesson_viewed 上报失败(不打断学习流)", packId, err);
          return true;
        });
      }
      return Promise.resolve(true);
    } catch (e) {
      this.setData({ _lessonReported: false });
      if (!auth.isLoggedIn()) {
        this._requireAuth();
        return Promise.resolve(false);
      }
      console.warn("[station] lesson_viewed 上报异常(不打断学习流)", packId, e);
      return Promise.resolve(true);
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
    if (!this._requireAuth()) return Promise.resolve();
    return api
      .getLubanLessonDetail(this.data.packId, { suppressAuthRedirect: true })
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
        // web-view 无法安全取得小程序 Authorization header。这里由已认证的
        // 站点签发仅绑定本卡的短期凭据；H5 会马上从地址栏抹去，绝不写入缓存。
        return api.issueLubanCardEntry(that.data.packId, { suppressAuthRedirect: true }).then(function (ticketResp) {
          var ticketBody = api.unwrapResponse(ticketResp) || {};
          var cardEntryUrl = appendCardEntryTicket(cardUrl, ticketBody.entry_ticket);
          if (!cardEntryUrl) throw new Error("CARD_ENTRY_UNAVAILABLE");
          that.setData({
            title: String(body.title || ""),
            cardUrl: cardEntryUrl,
            practiceUrl: practiceUrl,
            cardSha: String(body.content_sha256 || ""),
            loading: false,
            errorText: "",
          });
          that._enterTier(TIER_LESSON);
          return null;
        });
      })
      .catch(function (err) {
        if (!auth.isLoggedIn()) {
          that._requireAuth();
          return null;
        }
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "站点加载失败，请稍后重试"),
        });
        return null;
      });
  },
});
