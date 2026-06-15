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
    checkoutVisible: false,
    checkoutLoading: false,
    checkoutMessage: "",
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
      checkoutMessage: "",
    });
  },

  openCheckout() {
    if (!this.data.selectedPackage) return;
    this.setData({ checkoutVisible: true, checkoutMessage: "" });
  },

  closeCheckout() {
    if (this.data.checkoutLoading) return;
    this.setData({ checkoutVisible: false, checkoutMessage: "" });
  },

  noop() {},

  async submitCheckout() {
    var selected = this.data.selectedPackage;
    if (!selected || this.data.checkoutLoading) return;
    this.setData({ checkoutLoading: true, checkoutMessage: "" });
    try {
      var raw = await api.createBillingCheckout({
        package_id: selected.id,
        channel: "wechat",
      });
      var checkout = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
      var payment = checkout.payment && typeof checkout.payment === "object" ? checkout.payment : {};
      if (checkout.status === "payment_config_missing" || !payment.params) {
        this.setData({
          checkoutMessage: "支付通道还未配置。这版先验证权益门和开通流程，不会伪造支付成功。",
        });
        return;
      }
      await _requestPayment(payment.params);
      wx.showToast({ title: "支付完成，正在同步权益", icon: "none" });
      this.setData({ checkoutVisible: false });
      this._loadUsage();
    } catch (err) {
      var msg = api.describeRequestError
        ? api.describeRequestError(err, "下单失败，请稍后重试")
        : "下单失败，请稍后重试";
      this.setData({ checkoutMessage: msg });
    } finally {
      this.setData({ checkoutLoading: false });
    }
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

function _requestPayment(params) {
  return new Promise(function (resolve, reject) {
    if (!wx || typeof wx.requestPayment !== "function") {
      reject(new Error("当前微信版本暂不支持支付"));
      return;
    }
    wx.requestPayment(Object.assign({}, params || {}, {
      success: resolve,
      fail: reject,
    }));
  });
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
