// pages/billing/billing.js — 使用情况与额度

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    usagePrimaryLabel: "额度同步中",
    usagePrimaryPercent: 100,
    usageRows: [],
    packages: [],
    selectedPackageId: "sprint",
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
      var usageData = await api.getUsage();
      var walletData = null;
      try {
        walletData = await api.getWallet();
      } catch (_) {}
      this.setData(_normalizeUsage(usageData, walletData, this.data.selectedPackageId));
    } catch (_) {
      this.setData(_degradedUsageState());
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

function _normalizeUsage(raw, walletRaw, selectedPackageId) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) : raw || {};
  var wallet = api.unwrapResponse ? api.unwrapResponse(walletRaw) : walletRaw || {};
  if (data && data.status === "degraded") {
    return _degradedUsageState(data.display);
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
  var packages = _normalizePackages(wallet.packages);
  var selectedId = selectedPackageId || (packages[0] && packages[0].id) || "";
  var selected = _selectPackage(packages, selectedId);
  return {
    usagePrimaryLabel: display.primary_label || "剩余 " + primaryPercent + "%",
    usagePrimaryPercent: Math.max(0, Math.min(100, Math.round(primaryPercent))),
    packages: packages,
    selectedPackageId: selected ? selected.id : "",
    selectedPackage: selected,
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

function _normalizePackages(rawPackages) {
  var source = Array.isArray(rawPackages) && rawPackages.length
    ? rawPackages
    : [
        {
          id: "advance",
          name: "精学版",
          price: "99",
          points: 4400,
          desc: "适合持续复习，覆盖日常答疑、错题讲解和阶段训练。",
          badge: "",
        },
        {
          id: "sprint",
          name: "通关版",
          price: "199",
          points: 9000,
          desc: "适合冲刺阶段，高频训练、深度解析和复测闭环更从容。",
          badge: "推荐",
        },
      ];
  return source.map(function (pkg) {
    var id = String(pkg.id || pkg.package_id || "").trim();
    var price = String(pkg.price || pkg.price_yuan || "").trim();
    var points = Number(pkg.points || pkg.balance || 0) || 0;
    return {
      id: id,
      name: String(pkg.name || pkg.title || id || "学习包").trim(),
      price: price || "0",
      points: points,
      desc: String(pkg.desc || pkg.description || "").trim(),
      badge: String(pkg.badge || "").trim(),
    };
  }).filter(function (pkg) {
    return !!pkg.id;
  });
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
  return {
    usagePrimaryLabel: payload.primary_label || "额度暂不可用",
    usagePrimaryPercent: Math.max(0, Math.min(100, Math.round(primaryPercent))),
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
