const api = require("../../utils/api");
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
  if (!cacheKey || typeof wx === "undefined" || typeof wx.getStorageSync !== "function") return {};
  try {
    var cached = wx.getStorageSync(cacheKey);
    return cached && typeof cached === "object" ? cached.card || {} : {};
  } catch (_err) {
    return {};
  }
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    loading: true,
    errorText: "",
    detail: attemptDetailViewModel.buildAttemptDetailViewModel({}, {}),
  },

  onLoad(options) {
    var info = typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var statusBarHeight = info.statusBarHeight || 0;
    this._attemptRef = decode(options && options.attemptRef);
    this._card = readCachedCard(decode(options && options.cacheKey));
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      detail: attemptDetailViewModel.buildAttemptDetailViewModel({}, this._card),
    });
    this._loadDetail();
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.switchTab) {
      wx.switchTab({ url: "/pages/report/report" });
    }
  },

  async _loadDetail() {
    if (!this._attemptRef || !api.getLearningAttemptDetail) {
      this.setData({ loading: false });
      return;
    }
    try {
      var detail = api.unwrapResponse(await api.getLearningAttemptDetail(this._attemptRef));
      this.setData({
        loading: false,
        errorText: "",
        detail: attemptDetailViewModel.buildAttemptDetailViewModel(detail, this._card),
      });
    } catch (_err) {
      this.setData({
        loading: false,
        errorText: "详情暂时加载失败，先显示学情页缓存的摘要。",
        detail: attemptDetailViewModel.buildAttemptDetailViewModel({}, this._card),
      });
      if (typeof helpers.vibrate === "function") helpers.vibrate("light");
    }
  },
});
