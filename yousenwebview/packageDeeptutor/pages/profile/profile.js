// pages/profile/profile.js — 我的 tab（第10轮 10f：归位聚合 + exam_date 接线 + 时间预算偏好）
// 前端只展示后端 read model：exam_date / time_budget / review_reminder 全部经
// PATCH /api/v1/auth/profile/settings 落 member_console，回显走 GET /api/v1/auth/profile。

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");
var runtime = require("../../utils/runtime");
var route = require("../../utils/route");
var flags = require("../../utils/flags");
var auth = require("../../utils/auth");

// [W5-3] Debounce timer for settings save
var _saveTimer = null;
var SAVE_DEBOUNCE_MS = 500;

function _normalizeWalletUsage(raw, usageFallback, ledgerRaw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) || raw || {} : raw || {};
  var balance = Number(data.balance || data.points || data.display_balance || 0);
  if (!isFinite(balance)) balance = 0;
  var percent = _walletPercent(balance, ledgerRaw);
  var percentLabel = "剩余 " + _formatPercent(percent);
  var percentWidth = Math.max(0, Math.min(100, Math.round(percent)));
  var rows = [
    {
      key: "wallet_percent",
      label: "当前权益",
      detailLabel: percentLabel,
      remainingLabel: percentLabel,
      barStyle: "width:" + percentWidth + "%",
    },
  ];
  var packages = Array.isArray(data.packages) ? data.packages : [];
  var topPackage = packages[0] || {};
  if (topPackage && topPackage.points) {
    rows.push({
      key: "usage_record",
      label: "使用记录",
      detailLabel: "按使用记录",
      remainingLabel: "按使用记录",
      barStyle: "width:100%",
    });
  } else if (usageFallback) {
    rows.push({
      key: "usage_record",
      label: "使用记录",
      detailLabel: "按使用记录",
      remainingLabel: "按使用记录",
      barStyle: "width:100%",
    });
  }
  return {
    usagePrimaryLabel: percentLabel,
    usageRows: rows,
    usageDetailShow: false,
    usageLoading: false,
  };
}

function _walletPercent(balance, ledgerRaw) {
  var data = api.unwrapResponse ? api.unwrapResponse(ledgerRaw) : ledgerRaw || {};
  var entries = Array.isArray(data.entries) ? data.entries : [];
  var debits = 0;
  var positive = 0;
  entries.forEach(function (entry) {
    var delta = Number(entry.delta || 0);
    if (delta > 0) positive += delta;
    if (delta < 0) debits += Math.abs(delta);
  });
  var denominator = Math.max(1, Math.round(positive), Math.round(balance + debits), Math.round(balance));
  return Math.max(0, Math.min(100, (Number(balance || 0) / denominator) * 100));
}

function _formatPercent(value) {
  var rounded = Math.round(Number(value || 0) * 10) / 10;
  if (Math.abs(rounded - Math.round(rounded)) < 0.001) return String(Math.round(rounded)) + "%";
  return rounded.toFixed(1) + "%";
}

/**
 * 考试日期 → 头部副标题文案（10f：「考试日 9 月 19 日（剩 87 天）」）。
 * 纯展示派生，不做任何调度/掌握度计算。
 */
function _examDateLabel(examDate) {
  var raw = String(examDate || "").trim();
  if (!raw) return "考试日期待设置";
  var parts = raw.split("-");
  if (parts.length !== 3) return "考试日 " + raw;
  var month = Number(parts[1]);
  var day = Number(parts[2]);
  var dateLabel = month + " 月 " + day + " 日";
  var target = new Date(Number(parts[0]), month - 1, day);
  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var days = Math.round((target.getTime() - today.getTime()) / 86400000);
  if (!isFinite(days)) return "考试日 " + dateLabel;
  if (days > 0) return "考试日 " + dateLabel + "（剩 " + days + " 天）";
  if (days === 0) return "考试日 " + dateLabel + "（就是今天）";
  return "考试日 " + dateLabel + "（已过期，点这里更新）";
}

/**
 * 免费小课额度 ●●○（收集感：实心 = 剩余可点亮）。
 * 只消费后端 read model 字段 free_microlesson_quota（microlesson 状态机，
 * 归 member/wallet 域）；字段缺失时返回 null，区块整块隐藏，不造数。
 */
function _normalizeFreeQuota(payload) {
  var quota = payload && payload.free_microlesson_quota;
  if (!quota || typeof quota !== "object") return null;
  var total = Number(quota.total);
  if (!isFinite(total) || total <= 0) return null;
  var used = Math.max(0, Math.min(total, Number(quota.used) || 0));
  var remaining = isFinite(Number(quota.remaining))
    ? Math.max(0, Math.min(total, Number(quota.remaining)))
    : total - used;
  var dots = [];
  for (var i = 0; i < total; i++) {
    dots.push({ id: i, lit: i < remaining });
  }
  return { total: total, used: used, remaining: remaining, dots: dots };
}

function buildLinkItems(workspaceFlags) {
  var flagsValue = workspaceFlags && typeof workspaceFlags === "object" ? workspaceFlags : {};
  var items = [];
  items.push({ id: "membership", title: "权益充值" });
  if (flagsValue.assessmentEnabled !== false) {
    items.push({ id: "assessment", title: "摸底测试" });
  }
  items.push({ id: "feedback", title: "客服与反馈" });
  items.push({ id: "terms", title: "服务条款与隐私" });
  return items;
}

Page({
  data: {
    statusBarHeight: 0,
    username: "用户",
    avatarChar: "U",
    avatarUrl: "",
    isDark: true,
    usageLoading: true,
    usagePrimaryLabel: "剩余 --",
    usageRows: [],
    usageDetailShow: false,

    examDate: "",
    examDateLabel: "考试日期待设置",
    timeBudget: "",
    timeBudgetOptions: [
      { val: "light", label: "轻", desc: "约 15 分钟/天" },
      { val: "medium", label: "中", desc: "约 30 分钟/天" },
      { val: "heavy", label: "重", desc: "约 60 分钟/天" },
    ],
    dailyTarget: 30,
    dailyTargetOptions: [10, 30, 50],
    difficultyPref: "medium",
    difficultyOptions: [
      { val: "easy", label: "简单" },
      { val: "medium", label: "适中" },
      { val: "hard", label: "挑战" },
    ],
    explainStyle: "detailed",
    explainOptions: [
      { val: "brief", label: "简洁" },
      { val: "detailed", label: "详细" },
      { val: "socratic", label: "启发" },
    ],
    reviewReminder: false,

    // 免费小课额度（read model 字段缺失时为 null → 区块隐藏）
    freeQuota: null,

    linkItems: buildLinkItems(flags.getWorkspaceFlags()),
    isGuestPreview: false,
  },

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({ statusBarHeight: info.statusBarHeight });
    // 读取本地缓存的头像
    var localAvatar = wx.getStorageSync("local_avatar_path");
    this._localAvatarPath = localAvatar || "";
    if (localAvatar) {
      this.setData({ avatarUrl: localAvatar });
    }
  },

  onShow: function () {
    var workspaceFlags = flags.getWorkspaceFlags();
    if (!flags.ensureFeatureEnabled("profile")) return;
    this.setData({
      isDark: helpers.isDark(),
      linkItems: buildLinkItems(workspaceFlags),
    });
    // 五 tab 壳按当前路由自判高亮，序号参数已死，传 null 即可
    helpers.syncTabBar(this, null, {
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    if (!auth.isLoggedIn()) {
      this._showGuestPreview();
      return;
    }
    this.setData({ isGuestPreview: false });
    this._loadUserInfo();
    this._loadUsage();
  },

  _loadUsage: function () {
    if (!auth.isLoggedIn()) {
      this._showGuestPreview();
      return;
    }
    var self = this;
    self.setData({ usageLoading: true });
    Promise.all([
      api.getWallet(),
      api.getUsage().catch(function () {
        return null;
      }),
      api.getLedger(20).catch(function () {
        return null;
      }),
    ])
      .then(function (results) {
        var update = _normalizeWalletUsage(results[0], results[1], results[2]);
        // 免费小课额度若挂在 wallet read model 上，从这里消费
        var walletData = api.unwrapResponse
          ? api.unwrapResponse(results[0]) || results[0] || {}
          : results[0] || {};
        var freeQuota = _normalizeFreeQuota(walletData);
        if (freeQuota) update.freeQuota = freeQuota;
        self.setData(update);
      })
      .catch(function () {
        self.setData({ usageLoading: false, usageRows: [], usageDetailShow: false });
      });
  },

  openUsageDetail: function () {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    if (!this.data.usageRows.length) return;
    this.setData({ usageDetailShow: true });
  },

  closeUsageDetail: function () {
    this.setData({ usageDetailShow: false });
  },

  _loadUserInfo: function () {
    if (!auth.isLoggedIn()) {
      this._showGuestPreview();
      return;
    }
    var self = this;
    api
      .getUserInfo()
      .then(function (info) {
        var name = info.display_name || info.username || "用户";
        var examDate = info.exam_date || "";
        var update = {
          username: name,
          avatarChar: name.charAt(0).toUpperCase(),
          examDate: examDate,
          examDateLabel: _examDateLabel(examDate),
          timeBudget: info.time_budget || "",
          dailyTarget: info.daily_target || 30,
          difficultyPref: info.difficulty_preference || "medium",
          explainStyle: info.explanation_style || "detailed",
          reviewReminder: info.review_reminder || false,
        };
        // 免费小课额度若挂在 profile read model 上，从这里消费
        var freeQuota = _normalizeFreeQuota(info);
        if (freeQuota) update.freeQuota = freeQuota;
        // 本地头像只作为当前设备 UI cache；没有本地头像时才回落到服务端值
        if (!self._localAvatarPath && info.avatar_url) {
          update.avatarUrl = info.avatar_url;
        }
        self.setData(update);
      })
      .catch(function () {
        // getUserInfo 失败，保持默认值
      });
  },

  // ── 修改昵称 ──────────────────────────────────
  onChangeName: function () {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var self = this;
    helpers.vibrate("light");
    wx.showModal({
      title: "修改昵称",
      editable: true,
      placeholderText:
        self.data.username === "用户" ? "输入你的昵称" : self.data.username,
      success: function (res) {
        if (res.confirm && res.content && res.content.trim()) {
          var newName = res.content.trim().slice(0, 20);
          self.setData({
            username: newName,
            avatarChar: newName.charAt(0).toUpperCase(),
          });
          self._saveSettings({ display_name: newName });
          wx.showToast({ title: "昵称已更新", icon: "success" });
        }
      },
    });
  },

  // ── 修改头像 ──────────────────────────────────
  onChangeAvatar: function () {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var self = this;
    helpers.vibrate("light");
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: function (res) {
        var file = res.tempFiles[0];
        // 检查文件大小（压缩后仍超 2MB 则提示）
        if (file.size > 2 * 1024 * 1024) {
          wx.showToast({ title: "图片过大，请选择较小的图片", icon: "none" });
          return;
        }
        var tempPath = file.tempFilePath;
        // 保存到本地缓存
        wx.getFileSystemManager().saveFile({
          tempFilePath: tempPath,
          success: function (saveRes) {
            var savedPath = saveRes.savedFilePath;
            self._localAvatarPath = savedPath;
            wx.setStorageSync("local_avatar_path", savedPath);
            self.setData({ avatarUrl: savedPath });
            wx.showToast({ title: "头像已更新", icon: "success" });
          },
          fail: function () {
            // saveFile 失败时直接用临时路径
            self._localAvatarPath = tempPath;
            wx.setStorageSync("local_avatar_path", tempPath);
            self.setData({ avatarUrl: tempPath });
            wx.showToast({ title: "头像已更新", icon: "success" });
          },
        });
      },
    });
  },

  // ── 设置交互 ──────────────────────────────────
  onExamDateChange: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var value = e.detail.value;
    this.setData({
      examDate: value,
      examDateLabel: _examDateLabel(value),
    });
    this._saveSettings({ exam_date: value });
  },

  setTimeBudget: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ timeBudget: val });
    this._debouncedSave({ time_budget: val });
  },

  setDailyTarget: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ dailyTarget: val });
    this._debouncedSave({ daily_target: val });
  },

  setDifficulty: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ difficultyPref: val });
    this._debouncedSave({ difficulty_preference: val });
  },

  setExplainStyle: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ explainStyle: val });
    this._debouncedSave({ explanation_style: val });
  },

  onReminderChange: function (e) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var val = e.detail.value;
    this.setData({ reviewReminder: val });
    this._saveSettings({ review_reminder: val });
  },

  // ── 订阅消息说明（查看/说明；授权主入口仍在练完的「明天见」交接时刻） ──
  onSubscribeExplain: function () {
    helpers.vibrate("light");
    wx.showModal({
      title: "「明天见」复测提醒",
      content:
        "复测提醒通过微信订阅消息发送：每次练完，在「明天见」时刻由你按次授权，到期我们才提醒你回来复测。这里只查看开关状态；已授权的订阅可在微信「设置-订阅消息」里管理。",
      showCancel: false,
      confirmText: "知道了",
    });
  },

  // [W5-3] Debounced save — merges rapid successive changes into one API call
  _debouncedSave: function (patch) {
    // Merge new patch into pending patch
    this._pendingPatch = Object.assign(this._pendingPatch || {}, patch);
    var self = this;
    if (_saveTimer) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(function () {
      var merged = self._pendingPatch;
      self._pendingPatch = {};
      _saveTimer = null;
      self._saveSettings(merged);
    }, SAVE_DEBOUNCE_MS);
  },

  _saveSettings: function (patch) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    api.updateSettings(patch).catch(function () {
      wx.showToast({ title: "保存失败，请重试", icon: "none" });
    });
  },

  goBilling: function () {
    wx.navigateTo({ url: route.billing() });
  },

  goQuickLogin: function () {
    this._requireLogin();
  },

  _requireLogin: function () {
    runtime.redirectToLogin(route.profile());
  },

  _showGuestPreview: function () {
    this.setData({
      isGuestPreview: true,
      username: "未登录用户",
      avatarChar: "游",
      usageLoading: false,
      usagePrimaryLabel: "登录后查看权益",
      usageRows: [],
      usageDetailShow: false,
      examDate: "",
      examDateLabel: "考试日期待设置",
      timeBudget: "",
      dailyTarget: 30,
      difficultyPref: "medium",
      explainStyle: "detailed",
      reviewReminder: false,
      freeQuota: null,
    });
  },

  openFeedbackPage: function () {
    helpers.vibrate("light");
    wx.navigateTo({ url: route.feedback({ source: "profile" }) });
  },

  openLink: function (e) {
    var id = e.currentTarget.dataset.id;
    helpers.vibrate("light");
    if (id === "assessment") {
      if (!auth.isLoggedIn()) {
        this._requireLogin();
        return;
      }
      if (!flags.ensureFeatureEnabled("assessment", { redirect: false })) return;
      wx.navigateTo({ url: route.assessment() });
    } else if (id === "membership") {
      wx.navigateTo({ url: route.billing() });
    } else if (id === "feedback") {
      this.openFeedbackPage();
    } else if (id === "terms") {
      wx.navigateTo({ url: route.terms() });
    }
  },

  logout: function () {
    if (this.data.isGuestPreview || !auth.isLoggedIn()) {
      wx.showModal({
        title: "退出体验",
        content: "确定要退出先体验导学吗？",
        confirmColor: "#bf5b4e",
        success: function (res) {
          if (res.confirm) {
            runtime.logout();
          }
        },
      });
      return;
    }
    wx.showModal({
      title: "退出登录",
      content: "确定要退出登录吗？",
      confirmColor: "#bf5b4e",
      success: function (res) {
        if (res.confirm) {
          runtime.logout();
        }
      },
    });
  },
});
