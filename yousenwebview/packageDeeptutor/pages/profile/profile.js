// pages/profile/profile.js — 我的 tab（第10轮 10f：权益透明 · 纸墨朱竹）
//
// 前端只展示后端 read model：exam_date / review_reminder / daily_target 等经
// PATCH /api/v1/auth/profile/settings 落 member_console，回显走 GET /api/v1/auth/profile。
// 点亮判定唯一权威 = utils/learn-view-model（pack_lifecycle 投影），本页零第二套判定。
// IA 铁律（五模块 Brief §2/§3）：历史与学习统计绝不放本页；学习统计入口只指向学情页。

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");
var runtime = require("../../utils/runtime");
var route = require("../../utils/route");
var flags = require("../../utils/flags");
var auth = require("../../utils/auth");
var learnViewModel = require("../../utils/learn-view-model");
var surfaceTelemetry = require("../../utils/surface-telemetry");

// [W5-3] Debounce timer for settings save
var _saveTimer = null;
var SAVE_DEBOUNCE_MS = 500;

function _normalizeWalletUsage(raw, usageFallback, ledgerRaw) {
  var data = api.unwrapResponse ? api.unwrapResponse(raw) || raw || {} : raw || {};
  var balance = Number(data.balance || data.points || data.display_balance || 0);
  if (!isFinite(balance)) balance = 0;
  // 计费真值 = 钱包 points（Supabase 钱包按 canonical_uid）。
  // balance <= 0 即后端免费试用三规则生效（mobile.py：每日 3 问 / 7 日 12 问 /
  // 连续 3 日满额提示充值）。后端没有暴露已用计数的读接口（quota 只出现在
  // 429 detail 与 start-turn 预约路径），本页不自算、不造数——降级为静态规则说明。
  if (balance <= 0) {
    return {
      freeTier: true,
      usagePrimaryLabel: "免费体验中",
      usageRows: [],
      usageDetailShow: false,
      usageLoading: false,
    };
  }
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
  // 「使用记录/按使用记录」伪行已删：两个分支推的是同一条零信息行，
  // 明细入口由卡片自身的「查看详情」承担，账本在权益中心。
  return {
    freeTier: false,
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
 * 纯展示派生，不做任何调度/掌握度计算——exam_date 真值喂后端复习调度引擎。
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
 * 我的路线卡投影：点亮数 = learn-view-model 单一权威（pack_lifecycle），
 * 总站数 = PACK_UNIVERSE(40)。learning-report 读不到时返回 null——
 * 卡片只保留会员口径文案，不声称任何点亮数（缺字段降级不造数）。
 */
function _normalizeRouteCard(reportRaw, lessonsRaw) {
  if (!reportRaw) return null;
  var report = api.unwrapResponse ? api.unwrapResponse(reportRaw) || reportRaw : reportRaw;
  var lessons = lessonsRaw
    ? api.unwrapResponse
      ? api.unwrapResponse(lessonsRaw) || lessonsRaw
      : lessonsRaw
    : {};
  if (!report || typeof report !== "object") return null;
  var vm = learnViewModel.buildLearnViewModel({
    homeDashboard: {},
    report: report,
    lessons: lessons || {},
  });
  var total = Number(vm.packUniverse) || 0;
  if (total <= 0) return null;
  var lit = Math.max(0, Math.min(total, Number(vm.litCount) || 0));
  var percent = Math.round((lit / total) * 100);
  // 已点亮但占比 <4% 时给最小可见宽度（纯视觉，不改数字口径）
  if (lit > 0 && percent < 4) percent = 4;
  return {
    lit: lit,
    total: total,
    label: "路线 " + lit + " / " + total + " 站已点亮",
    barStyle: "width:" + percent + "%",
  };
}

function buildLinkItems(workspaceFlags) {
  var flagsValue = workspaceFlags && typeof workspaceFlags === "object" ? workspaceFlags : {};
  var items = [];
  if (flagsValue.assessmentEnabled !== false) {
    items.push({ id: "assessment", title: "摸底测试" });
  }
  if (flagsValue.reportEnabled !== false) {
    // IA 铁律：学习统计并入学情，不在我的单列——本行只做去学情页的入口
    items.push({ id: "diagnostic", title: "学习统计" });
  }
  items.push({ id: "membership", title: "权益充值" });
  items.push({ id: "feedback", title: "客服与反馈" });
  items.push({ id: "terms", title: "服务条款与隐私" });
  items.push({ id: "about", title: "关于鲁班智考" });
  return items;
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    username: "用户",
    avatarChar: "U",
    avatarUrl: "",
    isDark: false, // 我的页默认亮色(owner 2026-07-12);用户显式选过主题则跟随
    usageLoading: true,
    usagePrimaryLabel: "剩余 --",
    usageRows: [],
    usageDetailShow: false,
    freeTier: false,

    examDate: "",
    examDateLabel: "考试日期待设置",
    // 我的路线（null → 只显示会员口径文案，不声称点亮数）
    routeCard: null,
    // 时间预算轻/中/重是设计目标形态；后端 member_console 尚无 time_budget
    // 字段（缺口），先保留 daily_target 控件按新视觉重铺。
    // TODO(time_budget): 后端落 time_budget(light/medium/heavy) 后，
    // 本控件换三档映射（约 15/30/60 分钟每天），daily_target 退役。
    dailyTarget: 30,
    appearance: "light", // 外观:当前主题(unset 默认亮)
    appearanceOptions: [
      { val: "light", label: "亮色" },
      { val: "dark", label: "暗色" },
    ],
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
    var localAvatar = auth.readOwnerStorage
      ? auth.readOwnerStorage("local_avatar_path")
      : "";
    this._localAvatarPath = localAvatar || "";
    if (localAvatar) {
      this.setData({ avatarUrl: localAvatar });
    }
  },

  onShow: function () {
    surfaceTelemetry.trackModuleView(this, { module: "profile", section: "home" });
    var workspaceBack = runtime.getWorkspaceBack(route.profile());
    var workspaceFlags = flags.getWorkspaceFlags();
    if (!flags.ensureFeatureEnabled("profile")) return;
    this.setData({
      isDark: helpers.isDarkOr("light"),
      appearance: helpers.isDarkOr("light") ? "dark" : "light",
    });
    this.setData({
      navBackLabel: workspaceBack ? workspaceBack.label : "对话",
      linkItems: buildLinkItems(workspaceFlags),
    });
    // 五 tab 壳:我的 index=4
    helpers.syncTabBar(this, 4, {
      hidden: !flags.shouldShowWorkspaceShell(),
      isDark: helpers.isDarkOr("light"),
    });
    if (!auth.isLoggedIn()) {
      this._showGuestPreview();
      return;
    }
    this.setData({ isGuestPreview: false });
    this._loadUserInfo();
    this._loadUsage();
    this._loadRoute();
  },

  onHide: function () {
    surfaceTelemetry.trackModuleExit(this);
  },

  onUnload: function () {
    surfaceTelemetry.trackModuleExit(this);
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

  // 我的路线：绿灯站列表（轻）+ learning-report（重 read model，静默拉，
  // 失败/缺字段 → routeCard=null，卡片降级为纯口径文案）
  _loadRoute: function () {
    if (!auth.isLoggedIn()) return;
    var self = this;
    var opt = { silent: true };
    var settle = function (make) {
      return Promise.resolve()
        .then(make)
        .catch(function () {
          return null;
        });
    };
    Promise.all([
      settle(function () {
        return api.getLearningReport(100, opt);
      }),
      settle(function () {
        return api.getLubanLessons(opt);
      }),
    ]).then(function (res) {
      self.setData({ routeCard: _normalizeRouteCard(res[0], res[1]) });
    });
  },

  goRoute: function () {
    helpers.vibrate("light");
    wx.navigateTo({
      url: route.learn(),
      fail: function () {
        if (wx.reLaunch) wx.reLaunch({ url: route.learn() });
      },
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
            if (auth.writeOwnerStorage)
              auth.writeOwnerStorage("local_avatar_path", savedPath);
            self.setData({ avatarUrl: savedPath });
            wx.showToast({ title: "头像已更新", icon: "success" });
          },
          fail: function () {
            // saveFile 失败时直接用临时路径
            self._localAvatarPath = tempPath;
            if (auth.writeOwnerStorage)
              auth.writeOwnerStorage("local_avatar_path", tempPath);
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

  setAppearance: function (e) {
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val === "dark" ? "dark" : "light";
    helpers.setTheme(val); // 单一写入口:globalData + Storage,全端页面 onShow 跟随
    var dark = val === "dark";
    this.setData({ isDark: dark, appearance: val });
    helpers.syncTabBar(this, 4, {
      hidden: !flags.shouldShowWorkspaceShell(),
      isDark: dark,
    });
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
      usageLoading: false,
      usagePrimaryLabel: "登录后查看权益",
      usageRows: [],
      usageDetailShow: false,
      freeTier: false,
      examDate: "",
      examDateLabel: "考试日期待设置",
      routeCard: null,
      dailyTarget: 30,
      difficultyPref: "medium",
      explainStyle: "detailed",
      reviewReminder: false,
    });
  },

  openFeedbackPage: function () {
    helpers.vibrate("light");
    wx.navigateTo({ url: route.feedback({ source: "profile" }) });
  },

  openAbout: function () {
    wx.showModal({
      title: "关于鲁班智考",
      content:
        "鲁班智考 · 一建建筑实务备考助手。不按题收费，会员解锁的是你这条路线的剩余部分；已点亮站点生成的复习单元永久可回炉。",
      showCancel: false,
      confirmText: "知道了",
    });
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
      // 学习统计归学情页（IA 铁律：不在我的单列，只做去学情的入口）
      if (!flags.ensureFeatureEnabled("report", { redirect: false })) return;
      runtime.setWorkspaceBack(route.profile(), "我的");
      wx.navigateTo({ url: route.report() });
    } else if (id === "membership") {
      wx.navigateTo({ url: route.billing() });
    } else if (id === "feedback") {
      this.openFeedbackPage();
    } else if (id === "terms") {
      wx.navigateTo({ url: route.terms() });
    } else if (id === "about") {
      this.openAbout();
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
