const api = require("../../utils/api");
const route = require("../../utils/route");
const mistakeBookViewModel = require("../../utils/mistake-book-view-model");

function buildAttemptCache(item) {
  return {
    key: item.key,
    attemptRef: item.attemptRef,
    title: item.title,
    questionText: item.title,
    concept: item.conceptLabel,
    diagnosis: item.errorLabel,
    diagnosisDetail: item.note,
    answerLine: "",
    resultLabel: "错题",
    tone: "wrong",
  };
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    loading: true,
    errorText: "",
    filter: "all",
    model: mistakeBookViewModel.buildMistakeBookViewModel({ items: [] }),
    filteredItems: [],
  },

  onLoad() {
    var info = typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var statusBarHeight = info.statusBarHeight || 0;
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
    });
    this._loadMistakeBook();
  },

  onPullDownRefresh() {
    this._loadMistakeBook().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.report() });
    }
  },

  setFilter(event) {
    var filter =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.filter
        : "all";
    this.setData({ filter: filter || "all" });
    this._applyFilter();
  },

  openAttemptDetail(event) {
    var item = this._itemFromEvent(event);
    if (!item || !item.attemptRef) return;
    var cacheKey = "mistake_book_attempt:" + String(item.key || Date.now()).replace(/[^a-zA-Z0-9:_-]/g, "_");
    if (typeof wx !== "undefined" && typeof wx.setStorageSync === "function") {
      try {
        wx.setStorageSync(cacheKey, { card: buildAttemptCache(item), savedAt: Date.now() });
      } catch (_err) {}
    }
    if (typeof wx !== "undefined" && typeof wx.navigateTo === "function") {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/attempt-detail/attempt-detail?cacheKey=" +
          encodeURIComponent(cacheKey) +
          "&attemptRef=" +
          encodeURIComponent(item.attemptRef),
      });
    }
  },

  async recordReview(event) {
    var item = this._itemFromEvent(event);
    if (!item || !item.attemptRef || !api.recordMistakeBookItemReview) return;
    try {
      await api.recordMistakeBookItemReview(item.attemptRef);
      this._toast("已记录本次复习", "success");
      await this._loadMistakeBook();
    } catch (_err) {
      this._toast("复习记录失败，请稍后重试", "none");
    }
  },

  async markMastered(event) {
    var item = this._itemFromEvent(event);
    if (!item || !item.attemptRef || !api.markMistakeBookItemMastered) return;
    try {
      await api.markMistakeBookItemMastered(item.attemptRef);
      this._toast("已标记掌握", "success");
      await this._loadMistakeBook();
    } catch (_err) {
      this._toast("标记失败，请稍后重试", "none");
    }
  },

  async removeItem(event) {
    var item = this._itemFromEvent(event);
    if (!item || !item.attemptRef || !api.removeMistakeBookItem) return;
    try {
      await api.removeMistakeBookItem(item.attemptRef);
      this._toast("已移出错题集", "success");
      await this._loadMistakeBook();
    } catch (_err) {
      this._toast("移出失败，请稍后重试", "none");
    }
  },

  retry() {
    this._loadMistakeBook();
  },

  async _loadMistakeBook() {
    this.setData({ loading: true, errorText: "" });
    try {
      var body =
        api.unwrapResponse(
          await api.getMistakeBook({ include_mastered: true }, { suppressAuthRedirect: true }),
        ) || {};
      var model = mistakeBookViewModel.buildMistakeBookViewModel(body);
      this.setData({ loading: false, errorText: "", model: model });
      this._applyFilter();
    } catch (_err) {
      this.setData({
        loading: false,
        errorText: "错题集暂时加载失败，请稍后重试",
        model: mistakeBookViewModel.buildMistakeBookViewModel({ items: [] }),
        filteredItems: [],
      });
    }
  },

  _applyFilter() {
    var filter = this.data.filter || "all";
    var items = (this.data.model && this.data.model.visibleItems) || [];
    var filtered = items.filter(function (item) {
      if (filter === "due") return item.state === "due";
      if (filter === "active") return item.state !== "mastered";
      if (filter === "mastered") return item.state === "mastered";
      return true;
    });
    this.setData({ filteredItems: filtered });
  },

  _itemFromEvent(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    return ((this.data.model && this.data.model.items) || []).find(function (item) {
      return item.key === key;
    });
  },

  _toast(title, icon) {
    if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
      wx.showToast({ title: title, icon: icon || "none", duration: 1600 });
    }
  },
});
