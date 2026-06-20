// pages/billing/billing.js — 使用情况与权益

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    usagePrimaryLabel: "权益同步中",
    usageGaugeLabel: "%",
    usageRows: [],
    ledgerRows: [],
    ledgerLoading: false,
  },

  onLoad() {
    this._unloaded = false;
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

  onUnload() {
    this._unloaded = true;
  },

  async _loadUsage() {
    if (this._loadUsageInFlight) return;
    this._loadUsageInFlight = true;
    try {
      this.setData({ ledgerLoading: true });
      var results = await Promise.all([
        api.getUsage(),
        api.getWallet().catch(function () {
          return null;
        }),
        api.getLedger(20).catch(function () {
          return null;
        }),
      ]);
      if (this._unloaded) return;
      var state = _normalizeUsage(results[0], results[1], results[2]);
      state.ledgerLoading = false;
      this.setData(state);
    } catch (_) {
      if (this._unloaded) return;
      var degraded = _degradedUsageState();
      degraded.ledgerLoading = false;
      this.setData(degraded);
    } finally {
      this._loadUsageInFlight = false;
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

function _normalizeUsage(raw, walletRaw, ledgerRaw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
  var wallet = api.unwrapResponse
    ? api.unwrapResponse(walletRaw)
    : walletRaw || {};
  var ledgerEntries = _ledgerEntries(ledgerRaw);
  if (data && data.status === "degraded") {
    return _degradedUsageState(data.display);
  }
  var balance = Number(
    wallet.balance || wallet.points || wallet.display_balance || 0,
  );
  if (isNaN(balance)) balance = 0;
  balance = Math.max(0, Math.round(balance));
  var denominator = _displayDenominator(balance, ledgerEntries);
  var remainingPercent = _percent(balance, denominator);
  var remainingLabel = "剩余 " + _formatPrimaryPercent(remainingPercent);
  return {
    usagePrimaryLabel: remainingLabel,
    usageGaugeLabel: _formatGaugePercent(remainingPercent),
    usageRows: [
      {
        key: "wallet_percent",
        label: "当前权益",
        remainingLabel: remainingLabel,
        barStyle:
          "width:" +
          Math.max(0, Math.min(100, Math.round(remainingPercent))) +
          "%",
      },
      {
        key: "usage_record",
        label: "使用记录",
        remainingLabel: "按使用记录",
        barStyle: "width:100%",
      },
    ],
    ledgerRows: _normalizeLedgerRows(ledgerEntries, denominator),
  };
}

function _degradedUsageState(display) {
  var payload = display && typeof display === "object" ? display : {};
  var primaryPercent = Number(payload.primary_percent);
  if (isNaN(primaryPercent)) primaryPercent = 100;
  var label = String(payload.primary_label || "权益暂不可用")
    .replace(new RegExp("额" + "度", "g"), "权益")
    .replace(new RegExp("点" + "数", "g"), "权益");
  return {
    usagePrimaryLabel: label,
    usageGaugeLabel: "%",
    usageRows: [],
    ledgerRows: [],
  };
}

function _ledgerEntries(raw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
  return Array.isArray(data.entries) ? data.entries : [];
}

function _displayDenominator(balance, entries) {
  var positive = 0;
  var debits = 0;
  (Array.isArray(entries) ? entries : []).forEach(function (entry) {
    var delta = Number(entry.delta || 0);
    if (delta > 0) positive += delta;
    if (delta < 0) debits += Math.abs(delta);
  });
  return Math.max(
    1,
    Math.round(positive),
    Math.round(balance + debits),
    Math.round(balance),
  );
}

function _percent(value, denominator) {
  if (!denominator) return 0;
  return Math.max(
    0,
    Math.min(100, (Number(value || 0) / Number(denominator || 1)) * 100),
  );
}

function _formatPrimaryPercent(value) {
  var rounded = Math.round(Number(value || 0) * 10) / 10;
  if (Math.abs(rounded - Math.round(rounded)) < 0.001)
    return String(Math.round(rounded)) + "%";
  return rounded.toFixed(1) + "%";
}

function _formatRecordPercent(value) {
  var num = Number(value || 0);
  if (num > 0 && num < 0.01) return "<0.01%";
  if (num < 1) return num.toFixed(2) + "%";
  return _formatPrimaryPercent(num);
}

function _formatGaugePercent(value) {
  return String(Math.max(0, Math.min(100, Math.round(Number(value || 0)))));
}

function _normalizeLedgerRows(entries, denominator) {
  return (Array.isArray(entries) ? entries : [])
    .filter(function (entry) {
      return Number(entry.delta || 0) < 0;
    })
    .slice(0, 10)
    .map(function (entry, idx) {
      var delta = Math.abs(Math.round(Number(entry.delta || 0)));
      var balanceAfter = Math.max(
        0,
        Math.round(Number(entry.balance_after || 0)),
      );
      var deltaPercent = _percent(delta, denominator);
      var balanceAfterPercent = _percent(balanceAfter, denominator);
      return {
        id: String(entry.id || entry.reference_id || entry.created_at || idx),
        title: _ledgerTitle(entry),
        timeLabel: _formatLedgerTime(entry.created_at),
        usageLabel: "-" + _formatRecordPercent(deltaPercent),
        balanceLabel: "剩余 " + _formatPrimaryPercent(balanceAfterPercent),
      };
    });
}

function _ledgerTitle(entry) {
  var reason = String(entry.reason || entry.reference_type || "").trim();
  if (reason === "capture" || reason === "ai_usage") return "AI 学习消耗";
  return "权益消耗";
}

function _formatLedgerTime(value) {
  var text = String(value || "").trim();
  if (!text) return "--";
  var date = new Date(text);
  if (isNaN(date.getTime())) return text;
  var now = new Date();
  var hh = String(date.getHours()).padStart(2, "0");
  var mm = String(date.getMinutes()).padStart(2, "0");
  if (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  ) {
    return hh + ":" + mm;
  }
  return date.getMonth() + 1 + "月" + date.getDate() + "日 " + hh + ":" + mm;
}
