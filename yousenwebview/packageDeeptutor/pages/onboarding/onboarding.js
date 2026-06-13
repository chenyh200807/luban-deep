var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var runtime = require("../../utils/runtime");
var auth = require("../../utils/auth");
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
    tags: ["懂了还错", "写不到采分点"],
  },
  {
    id: "p2",
    titleLines: [
      riseChars("案例题写了一大段，", null, 0, 0, 50),
      riseChars("哪些话能得分？", 3, 6, 420, 50),
    ],
    desc: ["鲁班按采分点批改你的作答，", "拆出命中、漏点和表达问题。"],
    tags: ["案例批改", "采分点", "易错点"],
  },
  {
    id: "p3",
    titleLines: [
      riseChars("每天刷题，", null, 0, 0, 50),
      riseChars("下一步到底练什么？", 0, 3, 280, 50),
    ],
    desc: [
      "鲁班记住你的薄弱考点和丢分原因，",
      "把错题变成专属训练，越用越懂你。",
    ],
    tags: ["错因画像", "专属训练", "越用越懂你"],
  },
];

// 幕 1 词轮播（Fuse 式垂直 roller）：从「盲刷」滚到「提分」收住点亮。
var ROLL_WORDS = ["上班太忙", "记了又忘", "写了白写", "这次上岸"];

// 幕 id → ACTS 下标（决定当前页文案）
var ACT_SLIDE = { wave: 0, hook: 0, p1: 1, p2: 2, p3: 3 };

// 出场等待 = wxss `.exiting .horizon` 的 760ms transition + 40ms 余量；改任一处必须同步另一处。
var EXIT_MS = 800;

var PILL_ACT_IDS = SCENES.slice(1).map(function (s) {
  return s.id;
});

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    rollWords: ROLL_WORDS,
    pills: PILL_ACT_IDS,
    actId: "wave",
    actIndex: 0,
    activeSlide: ACTS[0],
    fx: {},
    entrySource: "guest_preview",
    destLogin: false,
    ctaExit: false,
  },

  onLoad: function (options) {
    try {
      var info = helpers.getWindowInfo();
      var safeBottom = info.safeArea
        ? info.screenHeight - info.safeArea.bottom
        : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: safeBottom,
      });
    } catch (_) {}
    this.setData({
      entrySource: String(
        (options &&
          (options.entry_source || options.entrySource || options.source)) ||
          "guest_preview",
      ),
      destLogin: !!(options && options.dest === "login"),
    });
    // 已登录用户不重复看导学+登录：直接进 chat（保持旧 bridge 的无缝再入语义）
    if (options && options.dest === "login" && auth.isLoggedIn()) {
      wx.reLaunch({
        url: route.chat({ entry_source: this.data.entrySource }),
      });
      return;
    }
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
      onFinish: function () {
        that._exit();
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
    if (this._exitTimer) {
      clearTimeout(this._exitTimer);
      this._exitTimer = null;
    }
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
    this._exit();
  },

  // 色浪转深 → 登录页（dest=login）；游客模式回退到 chat 试用。
  _exit: function () {
    if (this._exiting) return;
    this._exiting = true;
    var that = this;
    if (this._timeline) this._timeline.pause();
    this.setData({ ctaExit: true });
    this._exitTimer = setTimeout(function () {
      that._exitTimer = null;
      if (that.data.destLogin) {
        runtime.redirectToLogin(
          route.chat({ entry_source: that.data.entrySource }),
        );
      } else {
        wx.reLaunch({
          url: route.chat({
            entry_source: that.data.entrySource,
            preview: "1",
          }),
        });
      }
      that._exiting = false;
    }, EXIT_MS);
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
    // 轻点（dy≈0）不在此处理：tap 事件由 page-shell 的 onTapAccelerate 承接，
    // 功能控件用 catchtap 阻止 tap 冒泡，从而点控件不会误触发快进。
  },

  onPageTouchCancel: function () {
    this._touchY = null;
  },

  // 轻点页面空白/内容区：快进当前段（保持自动播放）
  onTapAccelerate: function () {
    if (this._timeline) this._timeline.skipSceneRest();
  },

  startExperience: function () {
    this._exit();
  },
});
