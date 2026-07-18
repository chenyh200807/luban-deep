// pages/billing/billing.js — 使用情况与权益

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");

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
    packages: [],
    selectedPackageId: "vip",
    selectedPackage: null,
    checkoutLoading: false,
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
    runtime.checkAuth(() => {
      this._loadUsage();
    });
  },

  async _loadUsage() {
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
      var state = _normalizeUsage(results[0], results[1], results[2], this.data.selectedPackageId);
      state.ledgerLoading = false;
      this.setData(state);
    } catch (_) {
      var degraded = _degradedUsageState();
      degraded.ledgerLoading = false;
      this.setData(degraded);
    }
  },

  goBack() {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.chat() });
      },
    });
  },

  goHome() {
    runtime.markGoHome();
    wx.reLaunch({ url: route.chat() });
  },

  selectPackage(e) {
    var packageId = String((e && e.currentTarget && e.currentTarget.dataset.id) || "").trim();
    if (!packageId) return;
    this.setData({
      selectedPackageId: packageId,
      selectedPackage: _selectPackage(this.data.packages, packageId),
    });
  },

  async openCheckout() {
    var selected = this.data.selectedPackage;
    if (!selected || this.data.checkoutLoading) return;
    this.setData({ checkoutLoading: true });
    try {
      var raw = await api.createBillingCheckout({
        package_id: selected.id,
        channel: "wechat",
      });
      var checkout = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
      var payment = checkout && checkout.payment ? checkout.payment : {};
      var params = payment.params || null;
      if (!params) {
        throw new Error(checkout.message || "PAYMENT_UNAVAILABLE");
      }
      await _requestWechatPayment(params);
      wx.showToast({ title: "支付成功", icon: "success" });
      this._refreshUsageAfterPayment();
    } catch (err) {
      wx.showToast({ title: _paymentErrorMessage(err), icon: "none" });
    } finally {
      this.setData({ checkoutLoading: false });
    }
  },

  _refreshUsageAfterPayment() {
    var page = this;
    page._loadUsage();
    [1500, 4000].forEach(function (delayMs) {
      setTimeout(function () {
        page._loadUsage();
      }, delayMs);
    });
  },

});

function _normalizeUsage(raw, walletRaw, ledgerRaw, selectedPackageId) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
  var wallet = api.unwrapResponse ? api.unwrapResponse(walletRaw) : walletRaw || {};
  var ledgerEntries = _ledgerEntries(ledgerRaw);
  if (data && data.status === "degraded") {
    return _degradedUsageState(data.display);
  }
  var packages = _normalizePackages(wallet.packages);
  var selectedId = selectedPackageId || (packages[0] && packages[0].id) || "";
  var selected = _selectPackage(packages, selectedId);
  var balance = Number(wallet.balance || wallet.points || wallet.display_balance || 0);
  if (isNaN(balance)) balance = 0;
  balance = Math.max(0, Math.round(balance));
  var denominator = _displayDenominator(balance, ledgerEntries);
  var remainingPercent = _percent(balance, denominator);
  var remainingLabel = "剩余 " + _formatPrimaryPercent(remainingPercent);
  return {
    usagePrimaryLabel: remainingLabel,
    usageGaugeLabel: _formatGaugePercent(remainingPercent),
    packages: packages,
    selectedPackageId: selected ? selected.id : "",
    selectedPackage: selected,
    usageRows: [
      {
        key: "wallet_percent",
        label: "当前权益",
        remainingLabel: remainingLabel,
        barStyle: "width:" + Math.max(0, Math.min(100, Math.round(remainingPercent))) + "%",
      },
      // 「使用记录/按使用记录」伪行已删：零信息 + 恒 100% 假进度条，
      // 账本真身就在本页下方的使用记录区。
    ],
    ledgerRows: _normalizeLedgerRows(ledgerEntries, denominator),
  };
}

function _normalizePackages(rawPackages) {
  var source = Array.isArray(rawPackages) && rawPackages.length
    ? rawPackages
    : _launchPackages();
  var normalized = source.map(_normalizePackageItem).filter(function (pkg) {
    return !!pkg.id && _isLaunchPackageId(pkg.id);
  });
  if (normalized.length) return normalized;
  return _launchPackages().map(_normalizePackageItem);
}

function _launchPackages() {
  return [
    {
      id: "vip",
      name: "VIP",
      price: "198",
      original_price: "298",
      points: 9000,
      turns: 450,
      desc: "适合稳定备考，覆盖日常答疑、错题讲解和阶段训练。",
      badge: "",
    },
    {
      id: "svip",
      name: "SVIP",
      price: "598",
      original_price: "798",
      points: 28000,
      turns: 1400,
      desc: "适合高频训练、深度解析和复测闭环。",
      badge: "推荐",
    },
    {
      id: "supreme_svip",
      name: "至尊SVIP",
      price: "998",
      original_price: "1298",
      points: 50000,
      turns: 2500,
      desc: "适合长周期强化学习和集中冲刺。",
      badge: "",
    },
  ];
}

function _isLaunchPackageId(packageId) {
  return {
    vip: true,
    svip: true,
    supreme_svip: true,
  }[String(packageId || "").trim()] === true;
}

function _normalizePackageItem(pkg) {
  var id = String(pkg.id || pkg.package_id || "").trim();
  var price = String(pkg.price || pkg.price_yuan || "").trim();
  var points = Number(pkg.points || pkg.balance || 0) || 0;
  return {
    id: id,
    name: String(pkg.name || pkg.label || pkg.title || id || "学习包").trim(),
    price: price || "0",
    originalPrice: String(pkg.original_price || pkg.originalPrice || "").trim(),
    points: points,
    turns: Number(pkg.turns || 0) || 0,
    desc: String(pkg.desc || pkg.description || "").trim(),
    badge: String(pkg.badge || "").trim(),
  };
}

function _selectPackage(packages, packageId) {
  var list = Array.isArray(packages) ? packages : [];
  var target = String(packageId || "").trim();
  for (var i = 0; i < list.length; i++) {
    if (String(list[i].id || "") === target) return list[i];
  }
  return list[0] || null;
}

function _requestWechatPayment(params) {
  var payload = params && typeof params === "object" ? params : {};
  return new Promise(function (resolve, reject) {
    wx.requestPayment({
      timeStamp: String(payload.timeStamp || ""),
      nonceStr: String(payload.nonceStr || ""),
      package: String(payload.package || ""),
      signType: String(payload.signType || "RSA"),
      paySign: String(payload.paySign || ""),
      success: resolve,
      fail: reject,
    });
  });
}

function _paymentErrorMessage(err) {
  var text = String((err && (err.errMsg || err.message)) || "").trim();
  if (text.indexOf("cancel") >= 0) return "已取消支付";
  if (text.indexOf("required") >= 0 || text.indexOf("openid") >= 0) return "请先完成微信登录";
  return "支付暂不可用，请稍后再试";
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
  return Math.max(1, Math.round(positive), Math.round(balance + debits), Math.round(balance));
}

function _percent(value, denominator) {
  if (!denominator) return 0;
  return Math.max(0, Math.min(100, (Number(value || 0) / Number(denominator || 1)) * 100));
}

function _formatPrimaryPercent(value) {
  var rounded = Math.round(Number(value || 0) * 10) / 10;
  if (Math.abs(rounded - Math.round(rounded)) < 0.001) return String(Math.round(rounded)) + "%";
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
  return (Array.isArray(entries) ? entries : []).filter(function (entry) {
    return Number(entry.delta || 0) < 0;
  }).slice(0, 10).map(function (entry) {
    var delta = Math.abs(Math.round(Number(entry.delta || 0)));
    var balanceAfter = Math.max(0, Math.round(Number(entry.balance_after || 0)));
    var deltaPercent = _percent(delta, denominator);
    var balanceAfterPercent = _percent(balanceAfter, denominator);
    return {
      id: String(entry.id || entry.reference_id || entry.created_at || Math.random()),
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
