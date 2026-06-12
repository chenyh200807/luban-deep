var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var runtime = require("../../utils/runtime");

var SLIDES = [
  {
    id: "diagnosis",
    kicker: "先体验导学",
    title: "题刷了很多，分数却不涨？",
    desc: "很多一建学员不是不努力，而是不知道自己到底卡在考点、题型，还是答案不得分。",
    accent: "blue",
    floatA: "少刷无效题",
    floatB: "先找卡点",
    visualRows: ["先判断当前薄弱点", "区分不会做和不会写", "给出今天最该练的方向"],
    weakRows: [],
    bullets: ["定位卡点", "停止盲刷", "先练值钱题"],
    examples: [
      "我最近建筑实务总提不上去，先查哪里？",
      "这道题我为什么会丢分？",
      "今天只有 20 分钟，先练什么最值？",
    ],
  },
  {
    id: "grade",
    kicker: "按考试采分点拆答案",
    title: "案例题写了一大段，哪些话能得分？",
    desc: "标准答案只告诉你该写什么，鲁班会看你写出来的每一句，哪句命中、哪句漏分。",
    accent: "green",
    floatA: "命中几分",
    floatB: "哪里漏写",
    visualRows: ["命中 3 个采分点", "漏写 2 个关键词", "1 处表达过泛"],
    weakRows: [],
    bullets: ["采分点", "漏分点", "易错表达"],
    examples: [
      "这段答案大概能拿几分？",
      "我哪里没有踩到采分点？",
      "帮我把这段改成更像考试答案。",
    ],
  },
  {
    id: "loop",
    kicker: "错因沉淀成训练",
    title: "错因会沉淀成下一题",
    desc: "错题不是看完就结束。鲁班会记住你的薄弱考点和答题习惯，下一题围绕错因继续练。",
    accent: "gold",
    floatA: "错因画像",
    floatB: "同类再练",
    visualRows: ["法规依据缺失", "程序性采分点易漏", "推荐同类题再练"],
    weakRows: [
      { title: "法规依据缺失", progress: 54 },
      { title: "程序性采分点易漏", progress: 82 },
      { title: "推荐同类题再练", progress: 68 },
    ],
    bullets: ["错因画像", "同类再练", "学情变化"],
    examples: [
      "我最近最常漏哪类采分点？",
      "只练“法规依据缺失”这类题。",
      "根据我的错因，安排下一道题。",
    ],
  },
];

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    activeIndex: 0,
    activeSlide: SLIDES[0],
    slides: SLIDES,
    entrySource: "guest_preview",
    motionTick: 0,
  },

  onLoad: function (options) {
    try {
      var info = helpers.getWindowInfo();
      var safeBottom = info.safeArea ? info.screenHeight - info.safeArea.bottom : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: safeBottom,
      });
    } catch (_) {}
    this.setData({
      entrySource: String(
        (options && (options.entry_source || options.entrySource || options.source)) ||
          "guest_preview",
      ),
    });
  },

  setActiveIndex: function (index) {
    if (!Number.isFinite(index) || index < 0 || index >= SLIDES.length) return;
    this.setData({
      activeIndex: index,
      activeSlide: SLIDES[index],
      motionTick: this.data.motionTick + 1,
    });
  },

  goNext: function () {
    this.setActiveIndex(Math.min(SLIDES.length - 1, this.data.activeIndex + 1));
  },

  goPrev: function () {
    this.setActiveIndex(Math.max(0, this.data.activeIndex - 1));
  },

  jumpTo: function (event) {
    this.setActiveIndex(Number(event.currentTarget.dataset.index));
  },

  startExperience: function () {
    wx.reLaunch({
      url: route.chat({ entry_source: this.data.entrySource, preview: "1" }),
    });
  },

  quickLogin: function () {
    runtime.redirectToLogin(route.chat({ entry_source: this.data.entrySource, preview: "1" }));
  },

  tryExample: function (event) {
    var query = String(event.currentTarget.dataset.query || "").trim();
    if (query) {
      runtime.setPendingChatIntent(query, "AUTO", { source: "onboarding_example" }, null);
    }
    wx.reLaunch({
      url: route.chat({ entry_source: "onboarding_example", preview: "1" }),
    });
  },
});
