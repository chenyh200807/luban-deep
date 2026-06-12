# 「先体验导学」Onboarding Motion 升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `yousenwebview/packageDeeptutor/pages/onboarding/` 从手动翻页静态导学升级为六幕自动播放 motion 叙事，并给登录页 guest-entry 加色浪转场。

**Architecture:** 纯函数时间轴调度器（`utils/motion-timeline.js`，Node 可单测）按 `motion-script.js` 数据驱动 `setData` 翻转 `fx.*` 标志位；WXSS 用「fx-hold（移除即播）/ fx-pop+on（添加即播）」两种门控模式触发 keyframes。手动交互（滑动/进度点/按钮）一票接管自动播放。所有补间只用 transform/opacity（小元素的背景色高亮除外），零网络请求。

**Tech Stack:** 微信小程序原生（WXML/WXSS/JS，无构建步骤）、Node 原生 `assert` 单测（仓库既有 `node yousenwebview/tests/test_*.js` 模式）。

**设计权威:** [2026-06-12-luban-onboarding-motion-upgrade-design.md](2026-06-12-luban-onboarding-motion-upgrade-design.md)

---

## 执行前必读

1. **本 worktree 有并行未提交工作（约 959 行，billing/chat/login 等）。严禁 `git add -A` / `git add .`，只允许逐文件 staging。**
2. Task 6 改 `pages/login/` 三件套——这些文件上已有并行工作的未提交 diff。**Task 6 完成后不要提交 login 文件**，留在工作区并向用户报告（提交顺序由用户裁决）。
3. 工作目录：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial`，分支 `codex/wechat-entitlement-paywall-trial`，直接在该分支上干，不新建分支。
4. 六幕结构：`wave`(0) → `hook`(1) → `diagnosis`(2) → `grade`(3) → `loop`(4) → `cta`(5)。进度点只显示 1–5（wave 是转场不算幕）。

## 文件地图

| 文件 | 动作 | 职责 |
|---|---|---|
| `yousenwebview/packageDeeptutor/utils/motion-timeline.js` | 新建 | 纯函数时间轴调度器（定时器可注入） |
| `yousenwebview/packageDeeptutor/pages/onboarding/motion-script.js` | 新建 | 六幕步序数据（只有时间和 patch，无逻辑） |
| `yousenwebview/tests/test_onboarding_motion_timeline.js` | 新建 | 调度器行为 + 脚本契约单测 |
| `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.js` | 重写 | 接线 timeline ↔ setData、手动接管、生命周期清理 |
| `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxml` | 重写 | 六幕结构 + fx 门控 class |
| `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxss` | 追加 | 门控规则 + 新 keyframes（不改既有规则） |
| `yousenwebview/packageDeeptutor/pages/login/login.{js,wxml,wxss}` | 小改 | guest-entry 色浪出场（不提交，见上） |

---

### Task 1: 时间轴调度器（TDD）

**Files:**
- Test: `yousenwebview/tests/test_onboarding_motion_timeline.js`
- Create: `yousenwebview/packageDeeptutor/utils/motion-timeline.js`

- [ ] **Step 1: 写失败测试**

创建 `yousenwebview/tests/test_onboarding_motion_timeline.js`：

```js
// test_onboarding_motion_timeline.js — onboarding motion 时间轴调度器 + 脚本契约
// Run: node yousenwebview/tests/test_onboarding_motion_timeline.js
//
// 调度器与 wx API 解耦（定时器注入），这里用手动推进的假时钟做确定性断言。
"use strict";

var assert = require("assert");
var motion = require("../packageDeeptutor/utils/motion-timeline");

function createFakeTimers() {
  var t = 0;
  var seq = 0;
  var tasks = [];
  return {
    now: function () {
      return t;
    },
    setTimeout: function (fn, ms) {
      var id = ++seq;
      tasks.push({ id: id, at: t + Math.max(0, ms), fn: fn });
      return id;
    },
    clearTimeout: function (id) {
      tasks = tasks.filter(function (x) {
        return x.id !== id;
      });
    },
    tick: function (ms) {
      var target = t + ms;
      for (;;) {
        tasks.sort(function (a, b) {
          return a.at - b.at || a.id - b.id;
        });
        var next = tasks[0];
        if (!next || next.at > target) break;
        t = next.at;
        tasks.shift();
        next.fn();
      }
      t = target;
    },
  };
}

function harness(scenes) {
  var timers = createFakeTimers();
  var events = [];
  var tl = motion.createTimeline(
    scenes,
    {
      onSceneStart: function (index, scene) {
        events.push("scene:" + scene.id);
      },
      onStep: function (patch) {
        events.push("step:" + Object.keys(patch).sort().join(","));
      },
      onFinish: function () {
        events.push("finish");
      },
    },
    timers,
  );
  return { timers: timers, events: events, tl: tl };
}

var T1 = [
  { id: "a", duration: 100, steps: [{ at: 10, patch: { x: 1 } }, { at: 60, patch: { y: 2 } }] },
  { id: "b", duration: 80, steps: [{ at: 20, patch: { z: 3 } }] },
];

// 1. 顺序触发 + 自动推进 + onFinish
(function () {
  var h = harness(T1);
  h.tl.start();
  h.timers.tick(0);
  h.timers.tick(300);
  assert.deepStrictEqual(h.events, [
    "scene:a",
    "step:x",
    "step:y",
    "scene:b",
    "step:z",
    "finish",
  ]);
  assert.strictEqual(h.tl.getState().status, "done");
})();

// 2. 终幕 duration=0：步骤照发，不自动结束
(function () {
  var T2 = [
    { id: "a", duration: 50, steps: [] },
    { id: "end", duration: 0, steps: [{ at: 10, patch: { cta: 1 } }] },
  ];
  var h = harness(T2);
  h.tl.start();
  h.timers.tick(1000);
  assert.deepStrictEqual(h.events, ["scene:a", "scene:end", "step:cta"]);
  assert.strictEqual(h.tl.getState().status, "playing");
})();

// 3. pause 不漏发不重发，resume 后剩余步骤按相对时间触发；二次 pause 累计 elapsed
(function () {
  var h = harness(T1);
  h.tl.start();
  h.timers.tick(30); // x 已发（at=10）
  h.tl.pause();
  h.timers.tick(500); // 暂停期间无事发生
  assert.deepStrictEqual(h.events, ["scene:a", "step:x"]);
  h.tl.resume(); // 场景内已过 30ms，y 还差 30ms
  h.timers.tick(29);
  assert.deepStrictEqual(h.events, ["scene:a", "step:x"]);
  h.timers.tick(1);
  assert.deepStrictEqual(h.events, ["scene:a", "step:x", "step:y"]);
  h.tl.pause(); // 二次 pause：elapsed 应为 60，场景结束还差 40
  h.tl.resume();
  h.timers.tick(40);
  assert.strictEqual(h.events[3], "scene:b");
})();

// 4. jumpTo = 手动一票接管：重放目标幕步骤，幕末不再自动推进
(function () {
  var h = harness(T1);
  h.tl.start();
  h.timers.tick(15); // scene:a, step:x
  h.tl.jumpTo(1);
  h.timers.tick(2000);
  assert.deepStrictEqual(h.events, ["scene:a", "step:x", "scene:b", "step:z"]);
  assert.strictEqual(h.tl.getState().autoAdvance, false);
  assert.notStrictEqual(h.tl.getState().status, "done");
  // 回跳重放
  h.tl.jumpTo(0);
  h.timers.tick(200);
  assert.deepStrictEqual(h.events.slice(4), ["scene:a", "step:x", "step:y"]);
})();

// 5. destroy 之后静默
(function () {
  var h = harness(T1);
  h.tl.start();
  h.tl.destroy();
  h.timers.tick(1000);
  assert.deepStrictEqual(h.events, ["scene:a"]);
  assert.strictEqual(h.tl.getState().status, "destroyed");
})();

console.log("OK test_onboarding_motion_timeline (scheduler)");
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial && node yousenwebview/tests/test_onboarding_motion_timeline.js
```

预期：FAIL，`Cannot find module '../packageDeeptutor/utils/motion-timeline'`。

- [ ] **Step 3: 实现调度器**

创建 `yousenwebview/packageDeeptutor/utils/motion-timeline.js`：

```js
// motion-timeline.js — onboarding motion 纯函数时间轴调度器
// 与 wx API 解耦：定时器/时钟可注入，Node 单测直接跑。
//
// createTimeline(scenes, hooks, timers) → {start, pause, resume, jumpTo, destroy, getState}
//   scenes: [{ id, duration, steps: [{ at, patch }] }]
//     duration <= 0 表示终幕：步骤照常调度，但不自动推进、不触发 onFinish。
//   hooks: { onSceneStart(index, scene), onStep(patch, ctx), onFinish() }
//   timers: { setTimeout, clearTimeout, now }（缺省用全局实现）
//
// 手动接管语义：jumpTo() 之后 autoAdvance 永久关闭（手动一票接管），
// 目标幕步骤从头重放（patch 必须幂等）。
"use strict";

function createTimeline(scenes, hooks, timers) {
  var setT =
    (timers && timers.setTimeout) ||
    function (fn, ms) {
      return setTimeout(fn, ms);
    };
  var clearT =
    (timers && timers.clearTimeout) ||
    function (id) {
      clearTimeout(id);
    };
  var now =
    (timers && timers.now) ||
    function () {
      return Date.now();
    };

  var state = {
    sceneIndex: -1,
    status: "idle", // idle | playing | paused | done | destroyed
    autoAdvance: true,
  };
  var pendingIds = [];
  var sceneStartedAt = 0;
  var sceneElapsedBeforePause = 0;

  function clearPending() {
    for (var i = 0; i < pendingIds.length; i++) clearT(pendingIds[i]);
    pendingIds = [];
  }

  function scheduleScene(index, offsetMs) {
    var scene = scenes[index];
    if (!scene) return;
    state.sceneIndex = index;
    state.status = "playing";
    sceneStartedAt = now();
    sceneElapsedBeforePause = offsetMs;

    if (offsetMs === 0 && hooks && hooks.onSceneStart) {
      hooks.onSceneStart(index, scene);
    }

    var steps = scene.steps || [];
    for (var i = 0; i < steps.length; i++) {
      (function (step) {
        var delay = step.at - offsetMs;
        if (delay < 0) return; // resume 时已发过的步骤不补发
        pendingIds.push(
          setT(function () {
            if (state.status === "destroyed") return;
            if (hooks && hooks.onStep) {
              hooks.onStep(step.patch, { sceneIndex: state.sceneIndex });
            }
          }, delay),
        );
      })(steps[i]);
    }

    if (scene.duration > 0) {
      var endDelay = scene.duration - offsetMs;
      if (endDelay < 0) endDelay = 0;
      pendingIds.push(setT(advance, endDelay));
    }
  }

  function advance() {
    if (state.status === "destroyed") return;
    clearPending();
    if (!state.autoAdvance) return;
    var next = state.sceneIndex + 1;
    if (next >= scenes.length) {
      state.status = "done";
      if (hooks && hooks.onFinish) hooks.onFinish();
      return;
    }
    scheduleScene(next, 0);
  }

  return {
    start: function () {
      if (state.status !== "idle") return;
      scheduleScene(0, 0);
    },
    pause: function () {
      if (state.status !== "playing") return;
      sceneElapsedBeforePause += now() - sceneStartedAt;
      clearPending();
      state.status = "paused";
    },
    resume: function () {
      if (state.status !== "paused") return;
      scheduleScene(state.sceneIndex, sceneElapsedBeforePause);
    },
    jumpTo: function (index) {
      if (state.status === "destroyed") return;
      if (!scenes[index]) return;
      state.autoAdvance = false; // 手动一票接管
      clearPending();
      scheduleScene(index, 0);
    },
    destroy: function () {
      clearPending();
      state.status = "destroyed";
    },
    getState: function () {
      return {
        sceneIndex: state.sceneIndex,
        status: state.status,
        autoAdvance: state.autoAdvance,
      };
    },
  };
}

module.exports = { createTimeline: createTimeline };
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial && node yousenwebview/tests/test_onboarding_motion_timeline.js
```

预期：`OK test_onboarding_motion_timeline (scheduler)`。

- [ ] **Step 5: 提交（窄域）**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial \
  && git add yousenwebview/packageDeeptutor/utils/motion-timeline.js yousenwebview/tests/test_onboarding_motion_timeline.js \
  && git commit -m "feat(onboarding): motion 时间轴调度器（纯函数可单测）"
```

---

### Task 2: 六幕步序数据 motion-script.js + 脚本契约测试

**Files:**
- Create: `yousenwebview/packageDeeptutor/pages/onboarding/motion-script.js`
- Modify: `yousenwebview/tests/test_onboarding_motion_timeline.js`（文件末尾追加契约断言）

- [ ] **Step 1: 在测试文件末尾（`console.log` 之前）追加脚本契约断言**

```js
// 6. motion-script 契约：六幕、id 顺序、步序时间合法、patch 形状
var SCENES = require("../packageDeeptutor/pages/onboarding/motion-script");

(function () {
  assert.strictEqual(SCENES.length, 6);
  assert.deepStrictEqual(
    SCENES.map(function (s) {
      return s.id;
    }),
    ["wave", "hook", "diagnosis", "grade", "loop", "cta"],
  );
  assert.strictEqual(SCENES[SCENES.length - 1].duration, 0, "终幕必须 duration=0");
  for (var i = 0; i < SCENES.length; i++) {
    var s = SCENES[i];
    assert.ok(s.duration >= 0);
    var prevAt = -1;
    var steps = s.steps || [];
    for (var j = 0; j < steps.length; j++) {
      var step = steps[j];
      assert.ok(step.at >= 0 && step.at > prevAt, s.id + " 步序必须严格递增");
      if (s.duration > 0) assert.ok(step.at <= s.duration, s.id + " 步序不得超出幕长");
      assert.ok(
        step.patch && typeof step.patch === "object" && Object.keys(step.patch).length > 0,
        s.id + " patch 必须是非空对象",
      );
      prevAt = step.at;
    }
  }
})();

console.log("OK test_onboarding_motion_timeline (script contract)");
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial && node yousenwebview/tests/test_onboarding_motion_timeline.js
```

预期：FAIL，`Cannot find module '../packageDeeptutor/pages/onboarding/motion-script'`。

- [ ] **Step 3: 创建 motion-script.js**

创建 `yousenwebview/packageDeeptutor/pages/onboarding/motion-script.js`：

```js
// motion-script.js — 「先体验导学」六幕步序数据（纯数据，无逻辑）
// 幕结构: wave(转场) → hook(文字钩子) → diagnosis(诊断对话)
//        → grade(判分揭晓) → loop(错因沉淀) → cta(收束)
// patch 的 key 是 onboarding 页 data 路径；全部幂等（手动跳幕会整幕重放）。
"use strict";

module.exports = [
  { id: "wave", duration: 700, steps: [] },

  {
    id: "hook",
    duration: 3400,
    steps: [
      { at: 120, patch: { "fx.hookPlay": true } },
      { at: 1700, patch: { "fx.hookAccent": true } },
    ],
  },

  {
    id: "diagnosis",
    duration: 8200,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 900, patch: { "fx.stageIn": true } },
      { at: 1500, patch: { "fx.bubbleMe": true } },
      { at: 2600, patch: { "fx.bubbleAi": true } },
      { at: 3800, patch: { "fx.bubbleAi2": true } },
      { at: 5000, patch: { "fx.bullets": true } },
      { at: 6200, patch: { "fx.examples": true } },
    ],
  },

  {
    id: "grade",
    duration: 9600,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 900, patch: { "fx.stageIn": true } },
      { at: 1600, patch: { "fx.paper": true } },
      { at: 2400, patch: { "fx.scan": true } },
      { at: 3400, patch: { "fx.rows": 1 } },
      { at: 4300, patch: { "fx.rows": 2 } },
      { at: 5200, patch: { "fx.rows": 3 } },
      { at: 5800, patch: { "fx.scoreOn": true, "fx.scoreRoll": 5 } },
      { at: 6100, patch: { "fx.scoreRoll": 9 } },
      { at: 6400, patch: { "fx.scoreRoll": 12 } },
      { at: 7000, patch: { "fx.examples": true } },
    ],
  },

  {
    id: "loop",
    duration: 8200,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 900, patch: { "fx.stageIn": true } },
      { at: 1500, patch: { "fx.bars": 1 } },
      { at: 2100, patch: { "fx.bars": 2 } },
      { at: 2700, patch: { "fx.bars": 3 } },
      { at: 3600, patch: { "fx.taskBox": true } },
      { at: 4800, patch: { "fx.examples": true } },
    ],
  },

  {
    id: "cta",
    duration: 0,
    steps: [
      { at: 200, patch: { "fx.ctaTitle": true } },
      { at: 1200, patch: { "fx.ctaActions": true } },
      { at: 1900, patch: { "fx.examples": true } },
    ],
  },
];
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial && node yousenwebview/tests/test_onboarding_motion_timeline.js
```

预期：两行 OK 都打印。

- [ ] **Step 5: 提交（窄域）**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial \
  && git add yousenwebview/packageDeeptutor/pages/onboarding/motion-script.js yousenwebview/tests/test_onboarding_motion_timeline.js \
  && git commit -m "feat(onboarding): 六幕 motion 步序脚本 + 契约测试"
```

---

### Task 3: onboarding.js 接线

**Files:**
- Modify(重写): `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.js`

- [ ] **Step 1: 用以下完整内容覆盖 onboarding.js**

（SLIDES 文案原样保留，零改动；新增 HOOK_WORDS / ACT_SLIDE / timeline 接线 / 滑动手势；删除旧的 setActiveIndex/motionTick 翻页逻辑。）

```js
var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var runtime = require("../../utils/runtime");
var motion = require("../../utils/motion-timeline");
var SCENES = require("./motion-script");

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

// 幕 1 文字 Hook（kinetic typography 用，逐词渲染）
var HOOK_WORDS = [
  { t: "一建实务案例题，" },
  { t: "到底" },
  { t: "怎么拿分", accent: true },
  { t: "？" },
];

// 幕 id → 背景 slide 下标（决定 accent 配色与 stage/example 内容）
var ACT_SLIDE = { wave: 0, hook: 0, diagnosis: 0, grade: 1, loop: 2, cta: 2 };

var PILL_ACT_IDS = SCENES.slice(1).map(function (s) {
  return s.id;
});

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    slides: SLIDES,
    hookWords: HOOK_WORDS,
    pills: PILL_ACT_IDS,
    actId: "wave",
    actIndex: 0,
    activeIndex: 0,
    activeSlide: SLIDES[0],
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
          activeIndex: slideIndex,
          activeSlide: SLIDES[slideIndex],
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

  // —— 出口（行为与改造前一致）——
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
```

- [ ] **Step 2: 跑既有测试确认无回归**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial && node yousenwebview/tests/test_onboarding_motion_timeline.js
```

预期：两行 OK。（onboarding.js 本身无 Node 单测——页面壳依赖 wx 全局，由 Task 7 DevTools 验收。）

- [ ] **Step 3: 暂不提交**（与 Task 4/5 的 WXML/WXSS 同属一个原子变更，Task 5 末尾一起提交。）

---

### Task 4: onboarding.wxml 六幕结构

**Files:**
- Modify(重写): `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxml`

- [ ] **Step 1: 用以下完整内容覆盖 onboarding.wxml**

要点：根节点挂滑动手势；新增 wave-overlay / hook-stage / cta-stage；幕 2–4 沿用原 stage 结构但加 fx 门控 class；「跳过」改为跳到 CTA 幕（不直接离开）。

```xml
<view
  class="onboarding-page slide-{{activeSlide.accent}}"
  bindtouchstart="onPageTouchStart"
  bindtouchend="onPageTouchEnd"
>
  <view class="pastel-field"></view>
  <view class="grid-bg"></view>
  <view class="wave-overlay {{actId !== 'wave' ? 'recede' : ''}}"></view>

  <view class="page-shell" style="padding-top: {{statusBarHeight}}px; padding-bottom: {{safeBottom + 22}}px">
    <view class="topbar">
      <view class="brand-lockup">
        <image class="brand-mark" src="../../images/logo-mark-white.png" mode="aspectFit" />
        <view>
          <text class="brand-title">鲁班智考</text>
          <text class="brand-sub">先体验导学</text>
        </view>
      </view>
      <view class="skip-btn" bindtap="skipToCta" aria-role="button" aria-label="跳过导学">
        <text class="skip-text">跳过</text>
      </view>
    </view>

    <view class="progress-row">
      <view
        class="progress-pill {{actIndex - 1 >= index ? 'on' : ''}} {{actIndex - 1 === index ? 'current' : ''}}"
        wx:for="{{pills}}"
        wx:key="*this"
        data-index="{{index}}"
        bindtap="jumpTo"
      ></view>
      <text class="progress-label">{{actIndex > 0 ? actIndex : 1}} / {{pills.length}}</text>
    </view>

    <!-- 幕 1: 文字 Hook（wave 幕期间预渲染，色浪退潮直接露出） -->
    <view
      class="hook-stage {{fx.hookPlay ? 'play' : ''}} {{fx.hookAccent ? 'accent-on' : ''}}"
      wx:if="{{actId === 'wave' || actId === 'hook'}}"
    >
      <view class="hook-line">
        <text
          wx:for="{{hookWords}}"
          wx:key="index"
          class="hook-word {{item.accent ? 'is-accent' : ''}}"
          style="animation-delay: {{index * 110}}ms"
        >{{item.t}}</text>
      </view>
      <text class="hook-sub">先看 30 秒，鲁班怎么帮你把分挣回来</text>
    </view>

    <!-- 幕 2-4: 诊断 / 判分 / 错因（原三幕结构 + fx 门控） -->
    <block wx:if="{{actId === 'diagnosis' || actId === 'grade' || actId === 'loop'}}">
      <view class="story-copy {{fx.copyIn ? '' : 'fx-hold'}}">
        <text class="scene-kicker">{{activeSlide.kicker}}</text>
        <text class="scene-title">{{activeSlide.title}}</text>
        <text class="scene-desc">{{activeSlide.desc}}</text>
      </view>

      <view class="product-stage {{fx.stageIn ? '' : 'fx-hold'}}" wx:if="{{activeSlide.id === 'diagnosis'}}">
        <view class="product-head">
          <text class="product-title">鲁班正在判断</text>
          <text class="product-state">导学开始</text>
        </view>
        <view class="chat-bubble me fx-pop {{fx.bubbleMe ? 'on' : ''}}">
          <text>我题刷了不少，建筑实务还是不涨分，先查哪里？</text>
        </view>
        <view class="chat-bubble ai fx-pop {{fx.bubbleAi ? 'on' : ''}}">
          <text>先别继续盲刷。</text>
          <text class="ai-line2 fx-pop {{fx.bubbleAi2 ? 'on' : ''}}">我会先看你卡在考点、题型，还是答案不得分。</text>
          <text class="typing-caret" wx:if="{{fx.bubbleAi && !fx.bullets}}"></text>
        </view>
        <view class="mini-steps fx-pop {{fx.bullets ? 'on' : ''}}">
          <view wx:for="{{activeSlide.bullets}}" wx:key="*this"><text>{{item}}</text></view>
        </view>
        <view class="keyboard-preview">
          <view></view><view></view><view></view><view></view><view></view><view></view>
        </view>
      </view>

      <view class="product-stage score-stage {{fx.stageIn ? '' : 'fx-hold'}}" wx:elif="{{activeSlide.id === 'grade'}}">
        <view class="product-head">
          <text class="product-title">AI 批改结果</text>
          <text class="score-pill {{fx.scoreOn ? 'pop' : ''}}">{{fx.scoreRoll || 0}} / 20</text>
        </view>
        <view class="answer-paper fx-pop {{fx.paper ? 'on' : ''}} {{fx.scan ? 'scan' : ''}}">
          <text>命中 </text>
          <text class="mark" style="animation-delay: 0ms">专项方案</text>
          <text> 和 </text>
          <text class="mark" style="animation-delay: 260ms">技术交底</text>
          <text>，漏了 </text>
          <text class="miss" style="animation-delay: 540ms">验收程序</text>
          <text>，表达过泛。</text>
        </view>
        <view class="point-row hit {{fx.rows >= 1 ? '' : 'fx-hold'}}">
          <text class="point-tag">得</text>
          <text class="point-text">命中 2 个采分点</text>
          <text class="point-score">+6</text>
        </view>
        <view class="point-row warn {{fx.rows >= 2 ? '' : 'fx-hold'}}">
          <text class="point-tag">漏</text>
          <text class="point-text">漏写责任人与验收</text>
          <text class="point-score">-5</text>
        </view>
        <view class="point-row warn {{fx.rows >= 3 ? '' : 'fx-hold'}}">
          <text class="point-tag">改</text>
          <text class="point-text">口号改成具体措施</text>
          <text class="point-score">改写</text>
        </view>
      </view>

      <view class="product-stage train-stage {{fx.stageIn ? '' : 'fx-hold'}}" wx:else>
        <view class="product-head">
          <text class="product-title">下一步训练</text>
          <text class="product-state">已生成</text>
        </view>
        <view class="weak-item {{fx.bars >= index + 1 ? '' : 'fx-hold'}}" wx:for="{{activeSlide.weakRows}}" wx:key="title">
          <text class="weak-title">{{item.title}}</text>
          <view class="weak-bar"><view style="width: {{item.progress}}%"></view></view>
        </view>
        <view class="task-box fx-pop {{fx.taskBox ? 'on' : ''}}">
          <text class="task-label">建议现在做</text>
          <text class="task-title">同类案例题 3 道，先练“验收程序 + 责任人”</text>
        </view>
      </view>
    </block>

    <!-- 幕 5: CTA 收束 -->
    <view class="cta-stage" wx:if="{{actId === 'cta'}}">
      <view class="cta-head fx-pop {{fx.ctaTitle ? 'on' : ''}}">
        <text class="cta-kicker">先体验导学 · 30 秒看完一轮</text>
        <text class="cta-title">让每一分</text>
        <text class="cta-title cta-title-accent">都有据可依</text>
      </view>
      <text class="cta-sub fx-pop {{fx.ctaActions ? 'on' : ''}}">答题 → 判分 → 错因 → 下一题。现在轮到你。</text>
    </view>

    <view
      class="example-panel {{fx.examples ? '' : 'fx-hold'}}"
      wx:if="{{actId !== 'wave' && actId !== 'hook'}}"
    >
      <view class="example-head">
        <text class="example-title">你可以直接这样问</text>
        <text class="example-note">点一下进入对话</text>
      </view>
      <view
        class="example-item"
        wx:for="{{activeSlide.examples}}"
        wx:key="*this"
        data-query="{{item}}"
        bindtap="tryExample"
        aria-role="button"
        aria-label="使用示例问题 {{item}}"
      >
        <text class="example-text">{{item}}</text>
        <text class="example-arrow">›</text>
      </view>
    </view>

    <view class="bottom-actions">
      <view class="back-btn {{actIndex <= 1 ? 'muted' : ''}}" bindtap="goPrev" aria-role="button" aria-label="上一幕">
        <text class="back-text">{{actIndex <= 1 ? '先浏览' : '上一步'}}</text>
      </view>
      <view class="primary-btn" wx:if="{{actId !== 'cta'}}" bindtap="goNext" aria-role="button" aria-label="下一幕">
        <text class="primary-text">下一步</text>
      </view>
      <view class="primary-btn" wx:else bindtap="startExperience" aria-role="button" aria-label="开始体验">
        <text class="primary-text">开始体验</text>
      </view>
    </view>

    <view class="login-link" wx:if="{{actId === 'cta'}}" bindtap="quickLogin" aria-role="button" aria-label="快速登录">
      <text class="login-link-text">已有学习记录？快速登录</text>
    </view>
  </view>
</view>
```

- [ ] **Step 2: 暂不提交**（Task 5 末尾一起提交。）

---

### Task 5: onboarding.wxss 门控规则与新 keyframes

**Files:**
- Modify: `yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxss`（**只在文件末尾追加**，不改既有规则）

- [ ] **Step 1: 在 onboarding.wxss 文件末尾追加以下内容**

```css
/* ============================================================
   Motion 升级追加段（六幕自动播放）
   门控模式约定：
   - .fx-hold：移除即播——对带既有入场动画的块，hold 期间杀动画并隐藏，
     class 移除后原动画从头播放。
   - .fx-pop + .on：添加即播——对新增动画的元素，.on 到位才挂 keyframes。
   只用 transform/opacity（小面积文字高亮的背景色动画除外）。
   ============================================================ */

/* —— 通用门控 —— */
.fx-pop {
  opacity: 0;
}

.story-copy.fx-hold .scene-kicker,
.story-copy.fx-hold .scene-title,
.story-copy.fx-hold .scene-desc {
  animation: none;
  opacity: 0;
}

.product-stage.fx-hold {
  animation: none;
  opacity: 0;
}

.point-row.fx-hold {
  animation: none;
  opacity: 0;
}

.point-row.fx-hold .point-score {
  animation: none;
}

.weak-item.fx-hold {
  animation: none;
  opacity: 0;
}

.weak-item.fx-hold .weak-bar view {
  animation: none;
  width: 0 !important;
}

.example-panel {
  animation: copyIn 520ms ease both;
}

.example-panel.fx-hold {
  animation: none;
  opacity: 0;
}

.example-panel.fx-hold .example-item {
  animation: none;
  opacity: 0;
}

/* —— 转场色浪（与登录页 guest-wave 同一渐变语言）—— */
.wave-overlay {
  position: fixed;
  left: 0;
  right: 0;
  top: -6%;
  bottom: -6%;
  z-index: 60;
  pointer-events: none;
  background: linear-gradient(180deg, #f7c96b 0%, #5aa2ff 38%, #2a63ff 72%, #0b2a66 100%);
}

.wave-overlay.recede {
  animation: waveOff 680ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

@keyframes waveOff {
  to {
    transform: translateY(-112%);
  }
}

/* —— 幕 1: 文字 Hook —— */
.hook-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding-bottom: 140rpx;
}

.hook-line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
}

.hook-word {
  opacity: 0;
  color: #07192e;
  font-size: 74rpx;
  line-height: 1.2;
  font-weight: 940;
  letter-spacing: 0.01em;
}

.hook-stage.play .hook-word {
  animation: hookWordIn 640ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes hookWordIn {
  from {
    opacity: 0;
    transform: translateY(36rpx) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.hook-word.is-accent {
  transition: color 420ms ease, transform 420ms ease;
}

.hook-stage.accent-on .hook-word.is-accent {
  color: #d78a11;
  transform: scale(1.04);
}

.hook-sub {
  display: block;
  margin-top: 28rpx;
  opacity: 0;
  color: rgba(8, 31, 58, 0.55);
  font-size: 27rpx;
  font-weight: 760;
}

.hook-stage.play .hook-sub {
  animation: copyIn 560ms ease 1200ms both;
}

/* —— 幕 2: 诊断对话 —— */
.chat-bubble.fx-pop.on {
  animation: bubbleIn 520ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes bubbleIn {
  from {
    opacity: 0;
    transform: translateY(22rpx) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.ai-line2.fx-pop.on {
  animation: copyIn 460ms ease both;
}

.mini-steps.fx-pop view {
  opacity: 0;
}

.mini-steps.fx-pop.on {
  opacity: 1;
}

.mini-steps.fx-pop.on view {
  animation: rowIn 460ms ease both;
}

.mini-steps.fx-pop.on view:nth-child(2) {
  animation-delay: 110ms;
}

.mini-steps.fx-pop.on view:nth-child(3) {
  animation-delay: 220ms;
}

/* —— 幕 3: 判分揭晓 —— */
.answer-paper.fx-pop.on {
  animation: copyIn 480ms ease both;
}

/* 扫描前采分点/漏分点高亮归零，scan 到位后逐个点亮（inline animation-delay 控节奏） */
.answer-paper.fx-pop .mark,
.answer-paper.fx-pop .miss {
  color: inherit;
  background: transparent;
}

.answer-paper.fx-pop.scan .mark {
  animation: markIn 460ms ease both;
}

.answer-paper.fx-pop.scan .miss {
  animation: missIn 460ms ease both;
}

@keyframes markIn {
  to {
    color: #07584e;
    background: rgba(0, 168, 148, 0.16);
  }
}

@keyframes missIn {
  to {
    color: #8a3b00;
    background: rgba(242, 184, 73, 0.24);
  }
}

/* 行点亮时分数从行内弹出（飘分） */
.score-stage .point-row .point-score {
  animation: scorePop 560ms cubic-bezier(0.16, 1, 0.3, 1) 240ms both;
}

@keyframes scorePop {
  from {
    opacity: 0;
    transform: translateY(18rpx) scale(1.32);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.score-pill.pop {
  animation: scorePop 480ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

/* —— 幕 4: 错因沉淀 —— */
.task-box.fx-pop.on {
  animation: bubbleIn 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

/* —— 幕 5: CTA 收束 —— */
.cta-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding-bottom: 40rpx;
}

.cta-head.fx-pop.on {
  animation: hookWordIn 680ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.cta-kicker {
  display: block;
  color: rgba(8, 31, 58, 0.5);
  font-size: 23rpx;
  font-weight: 860;
  letter-spacing: 0.04em;
}

.cta-title {
  display: block;
  margin-top: 14rpx;
  color: #07192e;
  font-size: 78rpx;
  line-height: 1.12;
  font-weight: 940;
}

.cta-title-accent {
  margin-top: 4rpx;
  color: #d78a11;
}

.cta-sub {
  display: block;
  margin-top: 26rpx;
  color: rgba(8, 31, 58, 0.58);
  font-size: 27rpx;
  font-weight: 760;
}

.cta-sub.fx-pop.on {
  animation: copyIn 560ms ease both;
}
```

- [ ] **Step 2: 跑测试 + 提交（Task 3/4/5 原子提交，窄域）**

```bash
cd /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial \
  && node yousenwebview/tests/test_onboarding_motion_timeline.js \
  && git add yousenwebview/packageDeeptutor/pages/onboarding/onboarding.js \
       yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxml \
       yousenwebview/packageDeeptutor/pages/onboarding/onboarding.wxss \
  && git commit -m "feat(onboarding): 六幕自动播放 motion 叙事（文字Hook/打字机/采分点点亮/飘分/CTA）"
```

预期：测试 OK 后提交成功，`git show --stat HEAD` 只含 3 个 onboarding 文件。

---

### Task 6: 登录页 guest-entry 色浪出场（**改完不提交**）

**Files:**
- Modify: `yousenwebview/packageDeeptutor/pages/login/login.js`（`handleGuestPreview` 函数）
- Modify: `yousenwebview/packageDeeptutor/pages/login/login.wxml`（根节点末尾加 overlay）
- Modify: `yousenwebview/packageDeeptutor/pages/login/login.wxss`（末尾追加）

> ⚠️ 这三个文件上有并行 paywall 工作的未提交 diff（guest-entry 按钮即出自它）。
> 本任务的改动**叠加其上、不提交**，完成后向用户报告，由用户决定提交归属与顺序。

- [ ] **Step 1: login.js — 替换 `handleGuestPreview` 函数体**

找到（并行工作已添加的）：

```js
  handleGuestPreview: function () {
    var source = this.data.entrySource || "guest_preview";
    wx.reLaunch({
      url: route.onboarding({ entry_source: source }),
    });
  },
```

替换为：

```js
  handleGuestPreview: function () {
    if (this._guestNavigating) return;
    this._guestNavigating = true;
    var that = this;
    var source = this.data.entrySource || "guest_preview";
    // 色浪先冲刷覆盖屏幕，再切页面；onboarding 侧 wave-overlay 同渐变续接退潮
    this.setData({ guestWaveActive: true });
    setTimeout(function () {
      wx.reLaunch({
        url: route.onboarding({ entry_source: source }),
        complete: function () {
          that._guestNavigating = false;
        },
      });
    }, 430);
  },
```

- [ ] **Step 2: login.js — data 中加初始值**

在 `Page({ data: {` 对象里加一行（与其他键并列）：

```js
    guestWaveActive: false,
```

- [ ] **Step 3: login.wxml — 根 `<view class="scene">` 闭合标签前加 overlay**

```xml
  <view class="guest-wave {{guestWaveActive ? 'play' : ''}}"></view>
```

- [ ] **Step 4: login.wxss — 文件末尾追加**

```css
/* —— 先体验导学：色浪出场转场（与 onboarding wave-overlay 同渐变语言）—— */
.guest-wave {
  position: fixed;
  left: 0;
  right: 0;
  top: -6%;
  bottom: -6%;
  z-index: 90;
  pointer-events: none;
  transform: translateY(104%);
  background: linear-gradient(0deg, #f7c96b 0%, #5aa2ff 44%, #2a63ff 80%, #0b2a66 100%);
}

.guest-wave.play {
  animation: guestWaveUp 460ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}

@keyframes guestWaveUp {
  to {
    transform: translateY(0);
  }
}
```

- [ ] **Step 5: 不提交，向用户报告**

`git status --short yousenwebview/packageDeeptutor/pages/login/` 确认三个文件为 M 状态即可。**不执行 git add/commit。**

---

### Task 7: DevTools 真实入口验收

**Files:** 无代码改动。

- [ ] **Step 1: 用微信开发者工具 CLI 打开项目根**

```bash
WX_DEVTOOLS_CLI="/Applications/wechatwebdevtools.app/Contents/MacOS/cli"
"$WX_DEVTOOLS_CLI" open --project /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-wechat-paywall-trial/yousenwebview --lang zh
```

注意：`--project` 必须指向 `yousenwebview` 项目根（AGENTS 硬门槛），不得指向 `packageDeeptutor`。

- [ ] **Step 2: 验收清单（在编译器/模拟器中逐项确认）**

1. 登录页点「先体验导学」→ 色浪从底部冲刷覆盖 → 进入 onboarding → 色浪向上退潮露出文字 Hook 幕。
2. Hook 幕：「一建实务案例题，到底怎么拿分？」逐词浮现，「怎么拿分」1.7s 时变琥珀色微弹。
3. 诊断幕：标题入场 → 样机落地 → 我方气泡 → AI 气泡两句先后打出（带光标）→ 三个 bullet 点亮 → 示例问题浮入。
4. 判分幕：答卷文字浮现 → 「专项方案」「技术交底」逐个亮绿、「验收程序」亮琥珀 → 三行采分点逐条点亮且分数弹出 → 分数从 0 滚到 12/20。
5. 错因幕：三条弱项进度条依次生长 → 任务卡弹入。
6. CTA 幕：大字收束 + 「开始体验」/「快速登录」/示例问题可点。
7. 手动接管：任意时刻上滑→下一幕、下滑→上一幕、点进度点跳幕，跳后该幕动效重放、不再自动推进。
8. 「跳过」→ 直达 CTA 幕（不是离开页面）。
9. 出口回归：「开始体验」→ chat（preview=1）；示例问题→ chat 且预填问题；「快速登录」→ 登录页。
10. 切后台再回前台：动画从暂停点继续，无错乱。
11. Network 面板：onboarding 页全程零网络请求。

- [ ] **Step 3: 真机预览**

DevTools 生成预览二维码，真机扫码确认动效流畅无可感知掉帧（请用户协助或用 `auto --auto-port 9420` 截图留证）。

- [ ] **Step 4: 验收证据归档**

把验收结论（逐项 pass/fail + 截图/录屏路径）写入 `artifacts/onboarding_motion_qa_20260612/QA_NOTES.md`（新建目录，写在主 repo 不写临时 worktree——QA artifacts 纪律）。

---

## Self-Review 核对（计划作者已跑）

- 设计 spec 六幕 ↔ motion-script 六场景一一对应；手动接管/跳过/出口回归/零网络/transform-opacity 红线均有任务落点。
- 类型一致性：`fx.*` 键在 motion-script、WXML、WXSS 三处一致（hookPlay/hookAccent/copyIn/stageIn/bubbleMe/bubbleAi/bubbleAi2/bullets/paper/scan/rows/scoreOn/scoreRoll/bars/taskBox/ctaTitle/ctaActions/examples）。
- `createTimeline` 接口签名在 Task 1 实现与 Task 3 调用一致（scenes, hooks, timers 可选）。
- 已知取舍：`markIn/missIn` 动画背景色（非合成属性）——小面积内联文字，可接受；`point-row` 既有 nth-child 90/180ms 延迟会叠加在步进点亮之后，方向一致可接受。
