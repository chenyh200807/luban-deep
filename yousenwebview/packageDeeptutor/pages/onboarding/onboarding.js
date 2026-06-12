var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var runtime = require("../../utils/runtime");
var motion = require("../../utils/motion-timeline");
var SCENES = require("./motion-script");

// 逐字 mask-rise 用：把文案拆成 [{c, accent, d}]，d 为该字的动画延迟(ms)。
function riseChars(text, accentStart, accentEnd, baseDelay, step) {
  var arr = [];
  for (var i = 0; i < text.length; i++) {
    arr.push({
      c: text.charAt(i),
      accent: accentStart != null && i >= accentStart && i < accentEnd,
      d: (baseDelay || 0) + i * (step || 50),
    });
  }
  return arr;
}

// 三页文案（标题两行逐字升起 / 说明两行 / 标签 chips）
var ACTS = [
  { id: "hook" },
  {
    id: "p1",
    titleLines: [
      riseChars("题刷了很多，", null, 0, 0, 50),
      riseChars("分数却不涨？", null, 0, 340, 50),
    ],
    desc: ["你缺的不是更多题，", "而是没人告诉你为什么丢分。"],
    tags: ["案例题", "丢分诊断"],
  },
  {
    id: "p2",
    titleLines: [
      riseChars("你写了一大段，", null, 0, 0, 50),
      riseChars("哪些话真能得分？", 3, 7, 380, 50),
    ],
    desc: ["鲁班按采分点拆解你的答案，", "看清哪里命中、哪里漏分、哪里白写。"],
    tags: ["采分点", "漏分点", "无效表达"],
  },
  {
    id: "p3",
    titleLines: [
      riseChars("别只收藏错题，", null, 0, 0, 50),
      riseChars("要知道下一步练什么", 3, 6, 380, 50),
    ],
    desc: ["鲁班会记住你的错因和薄弱点，", "把每次丢分变成下一次提分训练。"],
    tags: ["错因画像", "精准训练", "持续提分"],
  },
];

// 幕 1 词轮播（Fuse 式垂直 roller）：从「盲刷」滚到「提分」收住点亮。
var ROLL_WORDS = ["盲刷", "判分", "错因", "提分"];

// CTA 收束：第二行整行品牌蓝。
var CTA_LINES = [
  riseChars("让每一分", null, 0, 0, 60),
  riseChars("都有据可依", 0, 5, 380, 60),
];

// 幕 id → ACTS 下标（决定当前页文案）
var ACT_SLIDE = { wave: 0, hook: 0, p1: 1, p2: 2, p3: 3, cta: 3 };

var PILL_ACT_IDS = SCENES.slice(1).map(function (s) {
  return s.id;
});

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    rollWords: ROLL_WORDS,
    ctaLines: CTA_LINES,
    pills: PILL_ACT_IDS,
    actId: "wave",
    actIndex: 0,
    activeSlide: ACTS[0],
    fx: {},
    entrySource: "guest_preview",
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

  onReady: function () {
    var that = this;
    this._timeline = motion.createTimeline(SCENES, {
      onSceneStart: function (index, scene) {
        var slideIndex = ACT_SLIDE[scene.id] || 0;
        that.setData({
          actId: scene.id,
          actIndex: index,
          fx: {},
          activeSlide: ACTS[slideIndex],
        });
      },
      onStep: function (patch) {
        that.setData(patch);
      },
    });
    this._timeline.start();
  },

  onHide: function () {
    if (this._timeline) {
      this._wasPlaying = this._timeline.getState().status === "playing";
      this._timeline.pause();
    }
  },

  onShow: function () {
    if (this._timeline && this._wasPlaying) {
      this._wasPlaying = false;
      this._timeline.resume();
    }
  },

  onUnload: function () {
    if (this._timeline) this._timeline.destroy();
  },

  // —— 手动导航（一票接管自动播放）——
  _jumpAct: function (index) {
    if (!this._timeline) return;
    var max = SCENES.length - 1;
    var clamped = Math.max(1, Math.min(max, index)); // 不允许跳回 wave 转场幕
    this._timeline.jumpTo(clamped);
  },

  goNext: function () {
    this._jumpAct(this.data.actIndex + 1);
  },

  goPrev: function () {
    this._jumpAct(this.data.actIndex - 1);
  },

  jumpTo: function (event) {
    this._jumpAct(Number(event.currentTarget.dataset.index) + 1);
  },

  skipToCta: function () {
    this._jumpAct(SCENES.length - 1);
  },

  onPageTouchStart: function (event) {
    var t = event.touches && event.touches[0];
    this._touchY = t ? t.clientY : null;
  },

  onPageTouchEnd: function (event) {
    if (this._touchY == null) return;
    var t = event.changedTouches && event.changedTouches[0];
    var startY = this._touchY;
    this._touchY = null;
    if (!t) return;
    var dy = t.clientY - startY;
    if (dy <= -60) this.goNext();
    else if (dy >= 60) this.goPrev();
  },

  onPageTouchCancel: function () {
    this._touchY = null;
  },

  // —— 出口（行为与改造前一致）——
  startExperience: function () {
    wx.reLaunch({
      url: route.chat({ entry_source: this.data.entrySource, preview: "1" }),
    });
  },

  quickLogin: function () {
    runtime.redirectToLogin(route.chat({ entry_source: this.data.entrySource, preview: "1" }));
  },
});
