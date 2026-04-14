// pages/profile/profile.js — 个人中心

var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

// [W5-3] Debounce timer for settings save
var _saveTimer = null;
var SAVE_DEBOUNCE_MS = 500;

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    username: "用户",
    avatarChar: "U",
    avatarUrl: "",
    level: 1,
    xp: 0,
    userPoints: 0,
    points: 0,
    isDark: true,

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

    badges: [
      { id: 1, icon: "🏆", name: "首战告捷", earned: false },
      { id: 2, icon: "🎯", name: "连胜达人", earned: false },
      { id: 3, icon: "📚", name: "博览群书", earned: false },
      { id: 4, icon: "🔥", name: "坚持之星", earned: false },
      { id: 5, icon: "💡", name: "解题高手", earned: false },
      { id: 6, icon: "🌟", name: "满分王者", earned: false },
      { id: 7, icon: "⚡", name: "速战速决", earned: false },
      { id: 8, icon: "🎖️", name: "精英学员", earned: false },
    ],

    // 隐藏了"学习计划"（后期开发）
    linkItems: [
      { id: "assessment", icon: "📊", title: "摸底测试" },
      { id: "diagnostic", icon: "🔍", title: "摸底报告" },
      { id: "membership", icon: "👑", title: "会员充值" },
      { id: "terms", icon: "📄", title: "服务条款" },
    ],
  },

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
    });
    // 读取本地缓存的头像
    var localAvatar = wx.getStorageSync("local_avatar_path");
    if (localAvatar) {
      this.setData({ avatarUrl: localAvatar });
    }
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
    helpers.syncTabBar(this, 3);
    var self = this;
    getApp().checkAuth(function () {
      self._loadUserInfo();
      self._loadPoints();
    });
  },

  _loadPoints: function () {
    var self = this;
    api
      .getWallet()
      .then(function (data) {
        self.setData({ userPoints: data.balance || 0 });
      })
      .catch(function () {});
  },

  _loadUserInfo: function () {
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
          points: info.points || 0,
          examDate: info.exam_date || "",
          dailyTarget: info.daily_target || 30,
          difficultyPref: info.difficulty_preference || "medium",
          explainStyle: info.explanation_style || "detailed",
          reviewReminder: info.review_reminder || false,
        };
        // 服务端头像优先，本地缓存兜底
        if (info.avatar_url) {
          update.avatarUrl = info.avatar_url;
        }
        self.setData(update);

        var earned = new Set(info.earned_badge_ids || []);
        var badges = self.data.badges.map(function (b) {
          return {
            id: b.id,
            icon: b.icon,
            name: b.name,
            earned: earned.has(b.id),
          };
        });
        self.setData({ badges: badges });
      })
      .catch(function () {
        // getUserInfo 失败，保持默认值
      });
  },

  // ── 修改昵称 ──────────────────────────────────
  onChangeName: function () {
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
            wx.setStorageSync("local_avatar_path", savedPath);
            self.setData({ avatarUrl: savedPath });
            self._saveSettings({ avatar_url: savedPath });
            wx.showToast({ title: "头像已更新", icon: "success" });
          },
          fail: function () {
            // saveFile 失败时直接用临时路径
            wx.setStorageSync("local_avatar_path", tempPath);
            self.setData({ avatarUrl: tempPath });
            self._saveSettings({ avatar_url: tempPath });
            wx.showToast({ title: "头像已更新", icon: "success" });
          },
        });
      },
    });
  },

  // ── 设置交互 ──────────────────────────────────
  onExamDateChange: function (e) {
    this.setData({ examDate: e.detail.value });
    this._saveSettings({ exam_date: e.detail.value });
  },

  setDailyTarget: function (e) {
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ dailyTarget: val });
    this._debouncedSave({ daily_target: val });
  },

  setDifficulty: function (e) {
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ difficultyPref: val });
    this._debouncedSave({ difficulty_preference: val });
  },

  setExplainStyle: function (e) {
    helpers.vibrate("light");
    var val = e.currentTarget.dataset.val;
    this.setData({ explainStyle: val });
    this._debouncedSave({ explanation_style: val });
  },

  onReminderChange: function (e) {
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
    api.updateSettings(patch).catch(function () {
      wx.showToast({ title: "保存失败，请重试", icon: "none" });
    });
  },

  goHome: function () {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },

  goBilling: function () {
    wx.navigateTo({ url: "/pages/billing/billing" });
  },

  openLink: function (e) {
    var id = e.currentTarget.dataset.id;
    helpers.vibrate("light");
    if (id === "assessment") {
      wx.navigateTo({ url: "/pages/assessment/assessment" });
    } else if (id === "diagnostic") {
      wx.switchTab({ url: "/pages/report/report" });
    } else if (id === "membership") {
      wx.navigateTo({ url: "/pages/billing/billing" });
    } else if (id === "terms") {
      wx.navigateTo({ url: "/pages/legal/terms" });
    }
  },

  logout: function () {
    wx.showModal({
      title: "退出登录",
      content: "确定要退出登录吗？",
      confirmColor: "#ef4444",
      success: function (res) {
        if (res.confirm) {
          getApp().logout();
        }
      },
    });
  },
});
