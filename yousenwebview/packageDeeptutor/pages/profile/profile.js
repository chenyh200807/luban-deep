// pages/profile/profile.js — 个人中心

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");
var runtime = require("../../utils/runtime");
var route = require("../../utils/route");
var flags = require("../../utils/flags");
var auth = require("../../utils/auth");

// [W5-3] Debounce timer for settings save
var _saveTimer = null;
var SAVE_DEBOUNCE_MS = 500;
var BADGE_DESC_BY_ID = {
  1: "完成首次练习或摸底测试",
  2: "连续多题答对，保持稳定正确率",
  3: "覆盖多个章节并形成学习记录",
  4: "连续学习多天，形成复习节奏",
  5: "完成高质量解析或错题复盘",
  6: "在阶段测评中达到优秀表现",
  7: "在限定时间内完成练习任务",
  8: "持续完成学习目标并保持高掌握度",
};

function _normalizeBadges(remoteBadges, fallbackEarnedIds, currentBadges) {
  var earned = new Set(fallbackEarnedIds || []);
  var hasRemote = Array.isArray(remoteBadges) && remoteBadges.length;
  var source = hasRemote ? remoteBadges : currentBadges;
  return (source || []).map(function (badge) {
    var id = Number(badge.id);
    return {
      id: id,
      icon: badge.icon,
      name: badge.name,
      desc: badge.desc || BADGE_DESC_BY_ID[id] || "完成对应学习目标后自动点亮",
      earned: hasRemote && typeof badge.earned === "boolean" ? badge.earned : earned.has(id),
    };
  });
}

function _normalizeWalletUsage(raw, usageFallback, ledgerRaw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) || raw || {} : raw || {};
  var balance = Number(data.balance || data.points || data.display_balance || 0);
  if (!isFinite(balance)) balance = 0;
  var percent = _walletPercent(balance, data, usageFallback);
  var percentLabel = "剩余 " + _formatPercent(percent);
  var percentWidth = _barPercent(percent);
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

function _walletPercent(balance, walletRaw, usageRaw) {
  var denominator = _walletDenominator(balance, walletRaw, usageRaw);
  return Math.max(0, Math.min(100, (Number(balance || 0) / denominator) * 100));
}

function _walletDenominator(balance, walletRaw, usageRaw) {
  var entitlement = _entitlementPayload(walletRaw, usageRaw);
  var reference = Number(entitlement.reference_points || 0);
  if (reference > 0) return Math.max(1, Math.round(reference));
  var packageRef = _packageReferencePoints(walletRaw);
  if (packageRef > 0) return Math.max(1, Math.round(packageRef));
  return Math.max(1, Math.round(balance));
}

function _entitlementPayload(walletRaw, usageRaw) {
  var wallet = walletRaw && typeof walletRaw === "object" ? walletRaw : {};
  var usage = usageRaw && typeof usageRaw === "object" ? usageRaw : {};
  if (wallet.entitlement && typeof wallet.entitlement === "object") return wallet.entitlement;
  if (usage.entitlement && typeof usage.entitlement === "object") return usage.entitlement;
  var display = usage.display && typeof usage.display === "object" ? usage.display : {};
  return display;
}

function _packageReferencePoints(walletRaw) {
  var wallet = walletRaw && typeof walletRaw === "object" ? walletRaw : {};
  var packages = Array.isArray(wallet.packages) && wallet.packages.length
    ? wallet.packages
    : _launchPackages();
  var planId = _canonicalPackageId(wallet.plan_id || wallet.tier);
  if (!planId) return 0;
  for (var i = 0; i < packages.length; i++) {
    var pkg = packages[i] || {};
    if (_canonicalPackageId(pkg.id || pkg.package_id) === planId) {
      return Number(pkg.points || pkg.balance || 0) || 0;
    }
  }
  return 0;
}

function _launchPackages() {
  return [
    { id: "starter_19", points: 800 },
    { id: "light_98", points: 4400 },
    { id: "vip", points: 9000 },
    { id: "svip", points: 28000 },
    { id: "supreme_svip", points: 50000 },
  ];
}

function _canonicalPackageId(packageId) {
  var id = String(packageId || "").trim();
  var lower = id.toLowerCase();
  if (lower === "light_99" || lower === "lite_99" || lower === "99") return "light_98";
  return id;
}

function _formatPercent(value) {
  var rounded = Math.round(Number(value || 0) * 10) / 10;
  if (Math.abs(rounded - Math.round(rounded)) < 0.001) return String(Math.round(rounded)) + "%";
  return rounded.toFixed(1) + "%";
}

function _barPercent(value) {
  var bounded = Math.max(0, Math.min(100, Number(value || 0)));
  return String(Math.round(bounded * 10) / 10);
}

function buildLinkItems(workspaceFlags) {
  var flagsValue = workspaceFlags && typeof workspaceFlags === "object" ? workspaceFlags : {};
  var items = [];
  if (flagsValue.assessmentEnabled !== false) {
    items.push({ id: "assessment", icon: "📊", title: "摸底测试" });
  }
  if (flagsValue.reportEnabled !== false) {
    items.push({ id: "diagnostic", icon: "🔍", title: "摸底报告" });
  }
  items.push({ id: "membership", icon: "👑", title: "权益充值" });
  items.push({ id: "feedback", icon: "💬", title: "意见反馈" });
  items.push({ id: "terms", icon: "📄", title: "服务条款" });
  return items;
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    username: "用户",
    avatarChar: "U",
    avatarUrl: "",
    level: 1,
    xp: 0,
    isDark: true,
    usageLoading: true,
    usagePrimaryLabel: "剩余 --",
    usageRows: [],
    usageDetailShow: false,

    examDate: "",
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
    navBackLabel: "对话",

    badges: [
      { id: 1, icon: "🏆", name: "首战告捷", desc: "完成首次练习或摸底测试", earned: false },
      { id: 2, icon: "🎯", name: "连胜达人", desc: "连续多题答对，保持稳定正确率", earned: false },
      { id: 3, icon: "📚", name: "博览群书", desc: "覆盖多个章节并形成学习记录", earned: false },
      { id: 4, icon: "🔥", name: "坚持之星", desc: "连续学习多天，形成复习节奏", earned: false },
      { id: 5, icon: "💡", name: "解题高手", desc: "完成高质量解析或错题复盘", earned: false },
      { id: 6, icon: "🌟", name: "满分王者", desc: "在阶段测评中达到优秀表现", earned: false },
      { id: 7, icon: "⚡", name: "速战速决", desc: "在限定时间内完成练习任务", earned: false },
      { id: 8, icon: "🎖️", name: "精英学员", desc: "持续完成学习目标并保持高掌握度", earned: false },
    ],

    // 隐藏了"学习计划"（后期开发）
    linkItems: buildLinkItems(flags.getWorkspaceFlags()),
    isGuestPreview: false,
  },

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
    });
    // 读取本地缓存的头像
    var localAvatar = wx.getStorageSync("local_avatar_path");
    this._localAvatarPath = localAvatar || "";
    if (localAvatar) {
      this.setData({ avatarUrl: localAvatar });
    }
  },

  onShow: function () {
    var workspaceBack = runtime.getWorkspaceBack(route.profile());
    var workspaceFlags = flags.getWorkspaceFlags();
    if (!flags.ensureFeatureEnabled("profile")) return;
    this.setData({ isDark: helpers.isDark() });
    this.setData({
      navBackLabel: workspaceBack ? workspaceBack.label : "对话",
      linkItems: buildLinkItems(workspaceFlags),
    });
    helpers.syncTabBar(this, 3, {
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
        self.setData(_normalizeWalletUsage(results[0], results[1], results[2]));
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
        var update = {
          username: name,
          avatarChar: name.charAt(0).toUpperCase(),
          level: info.level || 1,
          xp: info.xp || 0,
          examDate: info.exam_date || "",
          dailyTarget: info.daily_target || 30,
          difficultyPref: info.difficulty_preference || "medium",
          explainStyle: info.explanation_style || "detailed",
          reviewReminder: info.review_reminder || false,
        };
        // 本地头像只作为当前设备 UI cache；没有本地头像时才回落到服务端值
        if (!self._localAvatarPath && info.avatar_url) {
          update.avatarUrl = info.avatar_url;
        }
        self.setData(update);

        self._loadBadges(info.earned_badge_ids || []);
      })
      .catch(function () {
        // getUserInfo 失败，保持默认值
      });
  },

  _loadBadges: function (fallbackEarnedIds) {
    var self = this;
    api
      .getBadges()
      .then(function (raw) {
        var data = api.unwrapResponse ? api.unwrapResponse(raw) || raw || {} : raw || {};
        self.setData({
          badges: _normalizeBadges(data.badges, fallbackEarnedIds, self.data.badges),
        });
      })
      .catch(function () {
        self.setData({
          badges: _normalizeBadges(null, fallbackEarnedIds, self.data.badges),
        });
      });
  },

  onBadgeTap: function (e) {
    var id = Number(e.currentTarget.dataset.id);
    var badge = this.data.badges.find(function (item) {
      return item.id === id;
    });
    if (!badge) return;
    wx.showModal({
      title: badge.name,
      content: (badge.earned ? "已获得：" : "未获得：") + badge.desc,
      showCancel: false,
      confirmText: "知道了",
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
    this.setData({ examDate: e.detail.value });
    this._saveSettings({ exam_date: e.detail.value });
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

  goHome: function () {
    var workspaceBack = runtime.consumeWorkspaceBack(route.profile());
    if (workspaceBack && workspaceBack.url) {
      wx.reLaunch({ url: workspaceBack.url });
      return;
    }
    runtime.setWorkspaceBack(route.profile(), "我的");
    runtime.markGoHome();
    wx.reLaunch({ url: route.chat() });
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
      level: 1,
      xp: 0,
      usageLoading: false,
      usagePrimaryLabel: "登录后查看权益",
      usageRows: [],
      usageDetailShow: false,
      examDate: "",
      dailyTarget: 30,
      difficultyPref: "medium",
      explainStyle: "detailed",
      reviewReminder: false,
      badges: _normalizeBadges(null, [], this.data.badges),
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
    } else if (id === "diagnostic") {
      if (!flags.ensureFeatureEnabled("report", { redirect: false })) return;
      runtime.setWorkspaceBack(route.profile(), "我的");
      wx.navigateTo({ url: route.report() });
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
        confirmColor: "#ef4444",
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
      confirmColor: "#ef4444",
      success: function (res) {
        if (res.confirm) {
          runtime.logout();
        }
      },
    });
  },
});
