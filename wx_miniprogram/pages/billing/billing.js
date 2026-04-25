// pages/billing/billing.js — 积分充值

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    loading: true,
    error: false,
    balance: 0,
    entries: [],
    page: 1,
    pageSize: 15,
    hasMore: false,
    selectedPkg: "standard",
    packages: [
      { id: "starter", points: 100, price: "9.9", per: "", badge: "" },
      {
        id: "standard",
        points: 500,
        price: "39",
        per: "¥0.078/点",
        badge: "热门",
      },
      { id: "pro", points: 1200, price: "79", per: "¥0.066/点", badge: "" },
      {
        id: "ultimate",
        points: 3000,
        price: "169",
        per: "¥0.056/点",
        badge: "VIP",
      },
    ],
  },

  onLoad() {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
      isDark: helpers.isDark(),
    });
  },

  onShow() {
    this.setData({ isDark: helpers.isDark() });
    getApp().checkAuth(() => {
      this._loadWallet();
      this._loadLedger();
    });
  },

  async _loadWallet() {
    try {
      var data = await api.getWallet();
      this.setData({ balance: data.balance || 0 });
    } catch (_) {}
  },

  async _loadLedger() {
    var page = this.data.page;
    var size = this.data.pageSize;
    var offset = (page - 1) * size;
    this.setData({ loading: true, error: false });
    try {
      var data = await api.getLedger(size, offset);
      var entries = (data.entries || []).map(function (e) {
        return {
          id: e.id,
          delta: e.delta,
          reason: _friendlyReason(e.reason),
          time: _formatTime(e.created_at),
          isDebit: e.delta < 0,
        };
      });
      this.setData({
        entries: entries,
        hasMore: !!data.has_more,
        loading: false,
      });
    } catch (_) {
      this.setData({ loading: false, error: true });
    }
  },

  onPrevPage: function () {
    if (this.data.page <= 1) return;
    this.setData({ page: this.data.page - 1 });
    this._loadLedger();
  },

  onNextPage: function () {
    if (!this.data.hasMore) return;
    this.setData({ page: this.data.page + 1 });
    this._loadLedger();
  },

  onSelectPkg: function (e) {
    this.setData({ selectedPkg: e.currentTarget.dataset.id });
  },

  onRecharge: function () {
    if (!this.data.selectedPkg) return;
    wx.showToast({ title: "充值功能即将上线", icon: "none" });
  },

  retry() {
    this.setData({ page: 1 });
    this._loadWallet();
    this._loadLedger();
  },

  goBack() {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.switchTab({ url: "/pages/chat/chat" });
      },
    });
  },

  goHome() {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },
});

function _friendlyReason(reason) {
  if (!reason) return "智力点变动";
  var map = {
    capture: "对话消耗",
    grant: "每日赠送",
    refund: "退回",
    purchase: "充值",
    admin_grant: "系统赠送",
    signup_bonus: "注册奖励",
  };
  return map[reason] || reason;
}

function _formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    var d = new Date(isoStr);
    var pad = function (n) {
      return n < 10 ? "0" + n : "" + n;
    };
    return (
      d.getMonth() +
      1 +
      "/" +
      d.getDate() +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes())
    );
  } catch (_) {
    return "";
  }
}
