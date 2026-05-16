// pages/billing/billing.js — 使用情况与额度

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    loading: true,
    error: false,
    errorTitle: "加载失败",
    usagePrimaryLabel: "额度同步中",
    usagePrimaryPercent: 100,
    usageRows: [],
    entries: [],
    page: 1,
    pageSize: 15,
    hasMore: false,
    selectedPkg: "sprint",
    selectedPkgLabel: "通关版",
    selectedPkgPrice: "199",
    selectedPkgUsage: "高频冲刺备考",
    selectedPkgDesc: "案例批改、整卷复盘、高频追问和薄弱点诊断",
    checkoutVisible: false,
    selectedPayChannel: "wechat",
    paying: false,
    payChannels: [
      {
        id: "wechat",
        label: "微信支付",
        desc: "小程序内完成支付",
      },
      {
        id: "alipay",
        label: "支付宝",
        desc: "生成支付宝订单",
      },
    ],
    packages: [
      {
        id: "advance",
        label: "精学版",
        usageLabel: "每周稳定学习",
        points: 4400,
        price: "99",
        per: "适合每周稳定学习",
        badge: "",
        desc: "错题讲解、章节复盘、1-2 套卷深度复盘",
        rhythm: "适合每周 1-2 套卷",
      },
      {
        id: "sprint",
        label: "通关版",
        usageLabel: "高频冲刺备考",
        points: 9000,
        price: "199",
        per: "适合考前 3-6 个月",
        badge: "适合考前冲刺",
        desc: "案例批改、整卷复盘、高频追问和薄弱点诊断",
        rhythm: "适合高强度冲刺",
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
      this._loadUsage();
      this._loadLedger();
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
        error: !!data.degraded,
        errorTitle: data.degraded ? "额度记录同步中" : "加载失败",
        loading: false,
      });
    } catch (_) {
      this.setData({ loading: false, error: true, errorTitle: "额度记录同步中" });
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
    var selectedPkg = e.currentTarget.dataset.id;
    var pkg = _selectedPackage(this.data.packages, selectedPkg);
    this.setData({
      selectedPkg: selectedPkg,
      selectedPkgLabel: pkg.label,
      selectedPkgPrice: pkg.price,
      selectedPkgUsage: pkg.usageLabel,
      selectedPkgDesc: pkg.desc,
    });
  },

  onRecharge: function () {
    if (!this.data.selectedPkg) return;
    this.setData({ checkoutVisible: true });
  },

  closeCheckout: function () {
    if (this.data.paying) return;
    this.setData({ checkoutVisible: false });
  },

  noop: function () {},

  onSelectPayChannel: function (e) {
    this.setData({ selectedPayChannel: e.currentTarget.dataset.id });
  },

  onConfirmPay: async function () {
    if (this.data.paying) return;
    var pkg = _selectedPackage(this.data.packages, this.data.selectedPkg);
    if (!pkg || !pkg.id) return;
    this.setData({ paying: true });
    try {
      var rawOrder = await api.createBillingCheckout({
        package_id: pkg.id,
        channel: this.data.selectedPayChannel,
      });
      var order = api.unwrapResponse ? api.unwrapResponse(rawOrder) : rawOrder;
      var payResult = await _runPayment(order);
      wx.showToast({
        title: payResult && payResult.pending ? "订单已生成" : "支付完成",
        icon: payResult && payResult.pending ? "none" : "success",
      });
      this.setData({ checkoutVisible: false });
      this._loadUsage();
      this._loadLedger();
    } catch (err) {
      wx.showModal({
        title: "支付未完成",
        content: _paymentErrorMessage(err),
        showCancel: false,
        confirmText: "知道了",
      });
    } finally {
      this.setData({ paying: false });
    }
  },

  retry() {
    this.setData({ page: 1 });
    this._loadUsage();
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

function _selectedPackage(packages, selectedPkg) {
  var items = Array.isArray(packages) ? packages : [];
  for (var i = 0; i < items.length; i++) {
    if (String(items[i].id || "") === String(selectedPkg || "")) return items[i];
  }
  return items[0] || {};
}

function _runPayment(order) {
  var payload = order && order.payment ? order.payment : {};
  if (payload.type === "wechat_mp" && payload.params) {
    return new Promise(function (resolve, reject) {
      wx.requestPayment(
        Object.assign({}, payload.params, {
          success: resolve,
          fail: reject,
        })
      );
    });
  }
  if (payload.type === "alipay_qr" && payload.qr_code_url) {
    return new Promise(function (resolve, reject) {
      wx.previewImage({
        current: payload.qr_code_url,
        urls: [payload.qr_code_url],
        success: function () { resolve({ pending: true }); },
        fail: reject,
      });
    });
  }
  var err = new Error(order && order.status ? order.status : "PAYMENT_ORDER_NOT_READY");
  err.order = order;
  throw err;
}

function _paymentErrorMessage(err) {
  var order = err && err.order ? err.order : {};
  if (order.status === "payment_config_missing") {
    return "支付订单已创建，但商户支付参数缺失。请先配置微信支付商户号/API v3 密钥或支付宝应用私钥。";
  }
  if (err && err.errMsg && err.errMsg.indexOf("cancel") >= 0) {
    return "你已取消本次支付，套餐没有变更。";
  }
  return "订单没有完成扣款，套餐不会变更。请稍后重试。";
}

function _friendlyReason(reason) {
  if (!reason) return "使用量变动";
  var map = {
    capture: "对话消耗",
    grant: "每日赠送",
    refund: "退回",
    purchase: "会员开通",
    admin_grant: "系统赠送",
    signup_bonus: "注册奖励",
  };
  return map[reason] || reason;
}

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
