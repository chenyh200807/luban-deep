// pages/billing/billing.js — 使用情况与额度

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    usagePrimaryLabel: "额度同步中",
    usagePrimaryPercent: 100,
    usageRows: [],
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
      this._loadUsage();
    });
  },

  async _loadUsage() {
    try {
      var data = await api.getUsage();
      this.setData(_normalizeUsage(data));
    } catch (_) {
      this.setData(_degradedUsageState());
    }
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

function _normalizeUsage(raw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
  if (data && data.status === "degraded") {
    return _degradedUsageState();
  }
  var display = data.display || {};
  var quota = data.quota || {};
  var rows = Array.isArray(quota.rows)
    ? quota.rows
    : Array.isArray(display.rows)
    ? display.rows
    : [];
  var primaryPercent = Number(
    display.primary_percent || display.primary_remaining_percent
  );
  if (isNaN(primaryPercent)) primaryPercent = 100;
  return {
    usagePrimaryLabel: display.primary_label || "剩余 " + primaryPercent + "%",
    usagePrimaryPercent: Math.max(0, Math.min(100, Math.round(primaryPercent))),
    usageRows: rows.filter(function (row) {
      return String(row.key || "") !== "five_hour";
    }).map(function (row) {
      var percent = Number(row.remaining_percent);
      if (isNaN(percent)) percent = 100;
      percent = Math.max(0, Math.min(100, Math.round(percent)));
      return {
        key: row.key || "",
        label: row.label || "使用限额",
        remainingLabel: "剩余 " + percent + "%",
        resetLabel: _formatUsageReset(row.reset_at),
        barStyle: "width:" + percent + "%",
      };
    }),
  };
}

function _degradedUsageState() {
  return {
    usagePrimaryLabel: "额度同步中",
    usagePrimaryPercent: 100,
    usageRows: [],
  };
}

function _formatUsageReset(resetAt) {
  var text = String(resetAt || "").trim();
  if (!text) return "";
  var d = new Date(text);
  if (isNaN(d)) return "";
  var now = new Date();
  var sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  var minutes = d.getMinutes();
  var time = d.getHours() + ":" + (minutes < 10 ? "0" : "") + minutes;
  if (sameDay) return time;
  return d.getMonth() + 1 + "月" + d.getDate() + "日";
}
