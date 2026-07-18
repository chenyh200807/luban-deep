const api = require("../../utils/api");
const auth = require("../../utils/auth");
const helpers = require("../../utils/helpers");
const attemptDetailViewModel = require("../../utils/attempt-detail-view-model");

function decode(value) {
  try {
    return decodeURIComponent(String(value || ""));
  } catch (_err) {
    return String(value || "");
  }
}

function readCachedCard(cacheKey) {
  var cached =
    cacheKey && auth.readOwnerStorage ? auth.readOwnerStorage(cacheKey) : null;
  return cached && typeof cached === "object" ? cached.card || {} : {};
}

// 空态判定：view model 恒有兜底标题，只有摘要/解析/下一步全缺才算无证据可展示
function hasAttemptEvidence(detail) {
  return Boolean(
    detail &&
      (detail.concept ||
        detail.answerLine ||
        detail.error ||
        (detail.explanationSections && detail.explanationSections.length) ||
        detail.nextTraining)
  );
}

Page({
  data: {
    isDark: true,
    statusBarHeight: 0,
    navHeight: 96,
    loading: true,
    errorText: "",
    isEmpty: false,
    detail: attemptDetailViewModel.buildAttemptDetailViewModel({}, {}),
  },

  onLoad(options) {
    var info = typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var statusBarHeight = info.statusBarHeight || 0;
    this._attemptRef = decode(options && options.attemptRef);
    this._card = readCachedCard(decode(options && options.cacheKey));
    this.setData({
      isDark: helpers.isDarkOr("light"),
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      detail: attemptDetailViewModel.buildAttemptDetailViewModel({}, this._card),
    });
    this._loadDetail();
  },

  onShow() {
    this.setData({ isDark: helpers.isDarkOr("light") });
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: "/packageDeeptutor/pages/report/report" });
    }
  },

  async _loadDetail() {
    if (!this._attemptRef || !api.getLearningAttemptDetail) {
      var fallback = attemptDetailViewModel.buildAttemptDetailViewModel({}, this._card);
      this.setData({ loading: false, isEmpty: !hasAttemptEvidence(fallback) });
      return;
    }
    try {
      var detail = api.unwrapResponse(await api.getLearningAttemptDetail(this._attemptRef));
      var built = attemptDetailViewModel.buildAttemptDetailViewModel(detail, this._card);
      this.setData({
        loading: false,
        errorText: "",
        isEmpty: !hasAttemptEvidence(built),
        detail: built,
      });
    } catch (_err) {
      var cachedOnly = attemptDetailViewModel.buildAttemptDetailViewModel({}, this._card);
      this.setData({
        loading: false,
        errorText: "详情暂时加载失败，先显示学情页缓存的摘要。",
        isEmpty: !hasAttemptEvidence(cachedOnly),
        detail: cachedOnly,
      });
      if (typeof helpers.vibrate === "function") helpers.vibrate("light");
    }
  },
});
