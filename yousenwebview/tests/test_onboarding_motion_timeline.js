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
  {
    id: "a",
    duration: 100,
    steps: [
      { at: 10, patch: { x: 1 } },
      { at: 60, patch: { y: 2 } },
    ],
  },
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

// 6. at:0 步骤在 start() 与 jumpTo() 都必须触发（resume 边界除外）
(function () {
  var T3 = [
    {
      id: "a",
      duration: 50,
      steps: [
        { at: 0, patch: { zero: 1 } },
        { at: 30, patch: { mid: 1 } },
      ],
    },
    { id: "b", duration: 0, steps: [{ at: 0, patch: { bzero: 1 } }] },
  ];
  var h = harness(T3);
  h.tl.start();
  h.timers.tick(200);
  assert.deepStrictEqual(h.events, [
    "scene:a",
    "step:zero",
    "step:mid",
    "scene:b",
    "step:bzero",
  ]);
  h.tl.jumpTo(0);
  h.timers.tick(100);
  assert.deepStrictEqual(h.events.slice(5), [
    "scene:a",
    "step:zero",
    "step:mid",
  ]);
})();

console.log("OK test_onboarding_motion_timeline (scheduler)");

// 7. motion-script 契约：六幕、id 顺序、步序时间合法、patch 形状
var SCENES = require("../packageDeeptutor/pages/onboarding/motion-script");

(function () {
  assert.strictEqual(SCENES.length, 5);
  assert.deepStrictEqual(
    SCENES.map(function (s) {
      return s.id;
    }),
    ["wave", "hook", "p1", "p2", "p3"],
  );
  assert.ok(
    SCENES[SCENES.length - 1].duration > 0,
    "终幕 p3 自动播完触发 onFinish 出场，duration 必须 > 0",
  );
  for (var i = 0; i < SCENES.length; i++) {
    var s = SCENES[i];
    assert.ok(s.duration >= 0);
    var prevAt = -1;
    var steps = s.steps || [];
    for (var j = 0; j < steps.length; j++) {
      var step = steps[j];
      assert.ok(step.at >= 0 && step.at > prevAt, s.id + " 步序必须严格递增");
      if (s.duration > 0)
        assert.ok(step.at <= s.duration, s.id + " 步序不得超出幕长");
      assert.ok(
        step.patch &&
          typeof step.patch === "object" &&
          Object.keys(step.patch).length > 0,
        s.id + " patch 必须是非空对象",
      );
      prevAt = step.at;
    }
  }
})();

console.log("OK test_onboarding_motion_timeline (script contract)");
