// motion-timeline.js — onboarding motion 纯函数时间轴调度器
// 与 wx API 解耦：定时器/时钟可注入，Node 单测直接跑。
//
// createTimeline(scenes, hooks, timers) → {start, pause, resume, jumpTo, skipSceneRest, destroy, getState}
//   scenes: [{ id, duration, steps: [{ at, patch }] }]
//     duration <= 0 表示终幕：步骤照常调度，但不自动推进、不触发 onFinish。
//   hooks: { onSceneStart(index, scene), onStep(patch, ctx), onFinish() }
//   timers: { setTimeout, clearTimeout, now }（缺省用全局实现）
//
// 手动接管语义：jumpTo() 之后 autoAdvance 永久关闭（手动一票接管），
// 目标幕步骤从头重放（patch 必须幂等）。
// 轻点快进语义：skipSceneRest() 把当前幕未触发的 step 立即补到终态，短停留后
// 推进（保持 autoAdvance 原值）；当前幕已冲刷过则再次调用立即进下一幕。
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
  var currentSceneElapsed = 0;
  var sceneFlushed = false; // 当前幕是否已被 skipSceneRest 冲刷到终态

  function clearPending() {
    for (var i = 0; i < pendingIds.length; i++) clearT(pendingIds[i]);
    pendingIds = [];
  }

  function scheduleScene(index, offsetMs) {
    var scene = scenes[index];
    if (!scene) return;
    state.sceneIndex = index;
    state.status = "playing";
    currentSceneElapsed = offsetMs;
    sceneStartedAt = now();
    sceneFlushed = false;

    if (offsetMs === 0 && hooks && hooks.onSceneStart) {
      hooks.onSceneStart(index, scene);
    }

    var steps = scene.steps || [];
    for (var i = 0; i < steps.length; i++) {
      (function (step) {
        var delay = step.at - offsetMs;
        // resume(offsetMs>0) 时跳过已发/正好到达边界的步骤；
        // start/jumpTo(offsetMs=0) 时 at:0 是合法步骤，必须照发。
        if (offsetMs > 0 && delay <= 0) return;
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
    currentSceneElapsed = 0;
    scheduleScene(next, 0);
  }

  return {
    start: function () {
      if (state.status !== "idle") return;
      scheduleScene(0, 0);
    },
    pause: function () {
      if (state.status !== "playing") return;
      currentSceneElapsed += now() - sceneStartedAt;
      clearPending();
      state.status = "paused";
    },
    resume: function () {
      if (state.status !== "paused") return;
      scheduleScene(state.sceneIndex, currentSceneElapsed);
    },
    jumpTo: function (index) {
      if (state.status === "destroyed") return;
      if (!scenes[index]) return;
      state.autoAdvance = false; // 手动一票接管
      clearPending();
      scheduleScene(index, 0);
    },
    skipSceneRest: function (shortEndMs) {
      // 轻点快进：把当前幕未触发的 step 立即补到终态；当前幕已冲刷过则直接进下一幕。
      if (state.status !== "playing") return;
      var scene = scenes[state.sceneIndex];
      if (!scene) return;
      if (sceneFlushed) {
        advance();
        return;
      }
      var elapsedNow = currentSceneElapsed + (now() - sceneStartedAt);
      clearPending();
      // 把当前幕所有未触发 step 合并成一次 onStep——轻点瞬间只过一次 bridge，
      // 而非连发多次 setData（patch 幂等，合并后即该幕终态）。
      var steps = scene.steps || [];
      var merged = {};
      var hasMerged = false;
      for (var i = 0; i < steps.length; i++) {
        if (steps[i].at > elapsedNow) {
          var patch = steps[i].patch;
          for (var k in patch) {
            if (Object.prototype.hasOwnProperty.call(patch, k)) {
              merged[k] = patch[k];
              hasMerged = true;
            }
          }
        }
      }
      if (hasMerged && hooks && hooks.onStep) {
        hooks.onStep(merged, { sceneIndex: state.sceneIndex });
      }
      sceneFlushed = true;
      currentSceneElapsed = scene.duration > 0 ? scene.duration : elapsedNow;
      sceneStartedAt = now();
      var endMs =
        typeof shortEndMs === "number" && shortEndMs >= 0 ? shortEndMs : 450;
      pendingIds.push(setT(advance, endMs));
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
