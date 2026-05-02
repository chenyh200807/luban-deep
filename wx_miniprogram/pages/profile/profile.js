// pages/profile/profile.js — 个人中心

var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

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
      { id: 1, icon: "🏆", name: "首战告捷", desc: "完成首次练习或摸底测试", earned: false },
      { id: 2, icon: "🎯", name: "连胜达人", desc: "连续多题答对，保持稳定正确率", earned: false },
      { id: 3, icon: "📚", name: "博览群书", desc: "覆盖多个章节并形成学习记录", earned: false },
      { id: 4, icon: "🔥", name: "坚持之星", desc: "连续学习多天，形成复习节奏", earned: false },
      { id: 5, icon: "💡", name: "解题高手", desc: "完成高质量解析或错题复盘", earned: false },
      { id: 6, icon: "🌟", name: "满分王者", desc: "在阶段测评中达到优秀表现", earned: false },
      { id: 7, icon: "⚡", name: "速战速决", desc: "在限定时间内完成练习任务", earned: false },
      { id: 8, icon: "🎖️", name: "精英学员", desc: "持续完成学习目标并保持高掌握度", earned: false },
    ],

    capabilityItems: [
      { id: "web_search", icon: "🌐", title: "联网搜索", status: "未开放", desc: "当前小程序答疑以建筑实务知识库和题库为主，联网搜索入口尚未接入。" },
      { id: "file_analysis", icon: "📎", title: "图片/文档分析", status: "未开放", desc: "当前仅支持文本提问，图片和文档上传分析需要单独的上传、审核和解析链路。" },
      { id: "mind_map", icon: "🧠", title: "思维导图", status: "未开放", desc: "思维导图生成需要结构化知识点输出和小程序渲染合同，尚未开放给用户。" },
    ],

    // 隐藏了"学习计划"（后期开发）
    linkItems: [
      { id: "assessment", icon: "📊", title: "摸底测试" },
      { id: "diagnostic", icon: "🔍", title: "摸底报告" },
      { id: "membership", icon: "👑", title: "会员充值" },
      { id: "feedback", icon: "💬", title: "意见反馈", nativeOpenType: "feedback" },
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

  onCapabilityTap: function (e) {
    var id = e.currentTarget.dataset.id;
    var item = this.data.capabilityItems.find(function (capability) {
      return capability.id === id;
    });
    if (!item) return;
    wx.showModal({
      title: item.title + " · " + item.status,
      content: item.desc,
      showCancel: false,
      confirmText: "知道了",
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
