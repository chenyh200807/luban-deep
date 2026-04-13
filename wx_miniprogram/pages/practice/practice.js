// pages/practice/practice.js — 练习中心页逻辑

const api = require("../../utils/api");
const auth = require("../../utils/auth");
const helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    // 今日目标
    todayDone: 0,
    dailyTarget: 30,
    progressPct: 0,
    streakDays: 0,

    // 练习模式
    practiceModes: [
      {
        id: "smart",
        icon: "🧠",
        title: "智能推荐",
        desc: "AI 精选高价值题",
        color: "#7c3aed",
        bgColor: "rgba(124,58,237,0.15)",
      },
      {
        id: "chapter",
        icon: "📖",
        title: "章节练习",
        desc: "按章节系统攻克",
        color: "#0891b2",
        bgColor: "rgba(8,145,178,0.15)",
      },
      {
        id: "mock",
        icon: "📝",
        title: "模考模拟",
        desc: "仿真考试环境",
        color: "#b45309",
        bgColor: "rgba(180,83,9,0.15)",
      },
      {
        id: "weak",
        icon: "🎯",
        title: "薄弱攻克",
        desc: "针对错误题型",
        color: "#dc2626",
        bgColor: "rgba(220,38,38,0.15)",
      },
    ],

    // 章节进度
    chaptersLoading: true,
    chapters: [],
  },

  onLoad() {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
      isDark: helpers.isDark(),
    });
  },

  onShow() {
    this.setData({ isDark: helpers.isDark() });
    const app = getApp();
    app.checkAuth(() => {
      this._loadProgress();
      this._loadChapters();
    });
  },

  async _loadProgress() {
    try {
      const raw = await api.getTodayProgress();
      const data = api.unwrapResponse(raw);
      const done = data.today_done || 0;
      const target = data.daily_target || 30;
      this.setData({
        todayDone: done,
        dailyTarget: target,
        progressPct: Math.min(100, Math.round((done / target) * 100)),
        streakDays: data.streak_days || 0,
      });
    } catch (e) {
      wx.showToast({ title: "数据加载失败", icon: "none", duration: 2000 });
    }
  },

  async _loadChapters() {
    try {
      const raw = await api.getChapterProgress();
      const data = api.unwrapResponse(raw);
      const chapterColors = [
        "#3b82f6",
        "#7c3aed",
        "#0891b2",
        "#059669",
        "#b45309",
        "#dc2626",
        "#db2777",
        "#0284c7",
      ];
      const chapters = (data || []).map((c, i) => ({
        id: c.chapter_id || i,
        name: c.chapter_name,
        done: c.done || 0,
        total: c.total || 0,
        pct: c.total > 0 ? Math.round((c.done / c.total) * 100) : 0,
        color: chapterColors[i % chapterColors.length],
      }));
      this.setData({ chapters, chaptersLoading: false });
    } catch (e) {
      // 显示默认章节
      wx.showToast({ title: "数据加载失败", icon: "none", duration: 2000 });
      this.setData({
        chaptersLoading: false,
        chapters: [
          {
            id: 1,
            name: "建筑构造",
            done: 23,
            total: 30,
            pct: 77,
            color: "#3b82f6",
          },
          {
            id: 2,
            name: "装饰装修",
            done: 14,
            total: 30,
            pct: 47,
            color: "#7c3aed",
          },
          {
            id: 3,
            name: "建筑地基",
            done: 8,
            total: 30,
            pct: 27,
            color: "#0891b2",
          },
          {
            id: 4,
            name: "施工组织",
            done: 0,
            total: 30,
            pct: 0,
            color: "#059669",
          },
        ],
      });
    }
  },

  goHome() {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },

  startMode(e) {
    const modeId = e.currentTarget.dataset.id;
    wx.showToast({ title: `${modeId} 模式即将上线`, icon: "none" });
  },

  startChapter(e) {
    wx.showToast({ title: "章节练习即将上线", icon: "none" });
  },

  viewReport() {
    wx.navigateTo({ url: "/pages/report/report" });
  },
});
