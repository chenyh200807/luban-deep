// pages/practice/practice.js — 练习中心页逻辑

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");

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
    chaptersError: false,
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
    runtime.checkAuth(() => {
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
      this.setData({ chapters, chaptersLoading: false, chaptersError: false });
    } catch (e) {
      wx.showToast({ title: "数据加载失败", icon: "none", duration: 2000 });
      this.setData({
        chaptersLoading: false,
        chaptersError: true,
        chapters: [],
      });
    }
  },

  _openPracticeChat(query, mode) {
    runtime.setPendingChatIntent(query, mode || "AUTO");
    wx.reLaunch({ url: route.chat() });
  },

  goHome() {
    runtime.markGoHome();
    wx.reLaunch({ url: route.chat() });
  },

  startMode(e) {
    const modeId = e.currentTarget.dataset.id;
    const modeQueries = {
      smart: "根据我当前薄弱点，给我来5道高价值选择题，不要提前给答案和解析。",
      chapter: "请按我当前最薄弱的章节，给我安排5道章节专项选择题，不要提前给答案和解析。",
      mock: "请按一建建筑实务模考风格，给我来5道递进式选择题，不要提前给答案和解析。",
      weak: "针对我最近最薄弱的知识点，给我来5道攻克训练选择题，不要提前给答案和解析。",
    };
    this._openPracticeChat(modeQueries[modeId] || "给我安排一组练习题。", "AUTO");
  },

  startChapter(e) {
    const chapterId = e.currentTarget.dataset.id;
    const current = (this.data.chapters || []).find((item) => item.id === chapterId);
    const chapterName = current && current.name ? current.name : "当前章节";
    this._openPracticeChat(
      `我想练习${chapterName}，请给我来5道选择题，不要提前给答案和解析。`,
      "AUTO",
    );
  },

  viewReport() {
    wx.navigateTo({ url: route.report() });
  },
});
