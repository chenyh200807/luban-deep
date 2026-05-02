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
    selectedPkg: "advance",
    paymentAvailability: {
      enabled: false,
      label: "暂未开放",
      reason: "充值通道正在接入微信支付，请联系运营开通或稍后再试",
    },
    packages: [
      {
        id: "trial",
        points: 100,
        price: "9",
        per: "约 10 次标准问答",
        badge: "尝鲜",
      },
      {
        id: "advance",
        points: 1200,
        price: "99",
        per: "约 120 次标准问答",
        badge: "推荐",
      },
      {
        id: "sprint",
        points: 2600,
        price: "199",
        per: "约 260 次标准问答",
        badge: "冲刺",
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
      var update = { balance: data.balance || 0 };
      var packages = _normalizePackages(data.packages);
      if (packages.length) {
        update.packages = packages;
        if (!_hasPackage(packages, this.data.selectedPkg)) {
          update.selectedPkg = packages[0].id;
        }
      }
      this.setData(update);
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
    var availability = this.data.paymentAvailability || {};
    if (!availability.enabled) {
      wx.showModal({
        title: availability.label || "暂未开放",
        content: availability.reason || "充值通道暂未开放，请稍后再试",
        showCancel: false,
        confirmText: "知道了",
      });
      return;
    }
    wx.showToast({ title: "支付通道未配置", icon: "none" });
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

function _normalizePackages(packages) {
  if (!Array.isArray(packages)) return [];
  return packages
    .filter(function (item) {
      return item && item.id && item.points && item.price;
    })
    .map(function (item) {
      return {
        id: String(item.id),
        points: Number(item.points) || 0,
        price: String(item.price),
        per: item.per || "",
        badge: item.badge || "",
      };
    });
}

function _hasPackage(packages, id) {
  return packages.some(function (item) {
    return item.id === id;
  });
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
