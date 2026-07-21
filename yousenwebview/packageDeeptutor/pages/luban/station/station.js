// 鲁班学习双轮 · 站点页（spike 形态）
// 统一路径：finished 成品讲懂 → finished 成品五题随堂练 → 服务端复核收据。
//
// 微信 web-view 是本页唯一交互面：卡内负责问答、进入练习与学习证据桥接。
// 禁止在 web-view 上叠原生 fixed 控件；即使视觉上被 H5 覆盖，原生层仍会
// 截获底部触摸，导致卡内「问鲁班」等控件看得见却点不动。
//
// 学-evidence 由 finished 卡内 bridge 委托 canonical 服务写入；掌握态/判分归
// 判分链路，本页不碰，也不保留第二个 native lesson_viewed writer。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 站进入 = module_viewed（object_type=station, object_id=pack_id）
// - 卡片打开 = learning_action_started（action=start_training,
//   object_type=microlesson, object_id="<pack>:tp:<episode>" —— 带 episode 粒度）
// - 停留时长 = module_viewed/module_exited（onShow/onHide 对，dwell 计时）
const api = require("../../../utils/api");
const helpers = require("../../../utils/helpers");
const auth = require("../../../utils/auth");
const route = require("../../../utils/route");
const runtime = require("../../../utils/runtime");
const telemetry = require("../../../utils/surface-telemetry");

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
    episodeIndex: 1,
    isDark: false,
    title: "",
    loading: true,
    errorText: "",
    currentUrl: "",
    cardUrl: "",
  },

  onLoad(query) {
    var packId = String((query && query.pack_id) || "").trim();
    var episode = Number(query && query.episode);
    if (!Number.isFinite(episode) || episode < 1) episode = 1;
    episode = Math.floor(episode);
    this.setData({ packId: packId, episodeIndex: episode, isDark: helpers.isDarkOr("light") });
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

  // 停留时长信号(观看时长的唯一正解——完播率架构拿不到):onShow 起计,
  // onHide/onUnload 结算 durationMs(trackModuleExit)。与 onLoad 的 station-enter
  // module_viewed(带 object_type=station 的进站漏斗事件)并存——此处是 dwell 计时对,
  // trackModuleView 的 __productBehaviorVisit 守卫保证同一页实例只起计一次。
  onShow() {
    telemetry.trackModuleView(this, { module: "learning", section: "station" });
  },

  onHide() {
    telemetry.trackModuleExit(this);
  },

  onUnload() {
    telemetry.trackModuleExit(this);
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
      runtime.redirectToLogin(route.lubanStation(this.data.packId, this.data.episodeIndex));
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
        url: route.lubanTeachingPoints(),
      });
    }
  },

  _showLessonCard() {
    this.setData({ currentUrl: this.data.cardUrl });
    // 微课集打开(episode 粒度)。teaching_point_id 不在 lesson detail 响应内
    // (后端仅在教学集列表派生 `<pack>:lesson:<index>`),故 object_id 用 tp 占位符
    // 保留 episode 粒度——旧值 `<pack>:lesson` 把同 pack 多集压成一条,粒度丢失。
    // 与 teaching-points 列表页 openEpisode 同构 object_id,可 join 成漏斗。
    telemetry.trackProductBehavior("learning_action_started", {
      module: "learning",
      action: "start_training",
      objectType: "microlesson",
      objectId: this.data.packId + ":tp:" + this.data.episodeIndex,
    });
  },

  _loadDetail() {
    var that = this;
    if (!this._requireAuth()) return Promise.resolve();
    return api
      .getLubanLessonDetail(this.data.packId, {
        episode: this.data.episodeIndex,
        suppressAuthRedirect: true,
      })
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
        // web-view 无法安全取得小程序 Authorization header。这里由已认证的
        // 站点签发仅绑定本卡的短期凭据；H5 会马上从地址栏抹去，绝不写入缓存。
        return api.issueLubanCardEntry(that.data.packId, { suppressAuthRedirect: true }).then(function (ticketResp) {
          var ticketBody = api.unwrapResponse(ticketResp) || {};
          var cardEntryUrl = appendCardEntryTicket(cardUrl, ticketBody.entry_ticket);
          if (!cardEntryUrl) throw new Error("CARD_ENTRY_UNAVAILABLE");
          that.setData({
            title: String(body.title || ""),
            cardUrl: cardEntryUrl,
            loading: false,
            errorText: "",
          });
          that._showLessonCard();
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
