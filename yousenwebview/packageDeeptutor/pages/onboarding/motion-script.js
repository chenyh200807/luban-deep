// motion-script.js — 「先体验导学」步序数据（纯数据，无逻辑）
// Less is more 版：wave(转场) → hook(文字钩子) → grade(判分时刻)
//                → loop(错因闭环) → cta(收束)，全程 ~11s。
// patch 的 key 是 onboarding 页 data 路径；全部幂等（手动跳幕会整幕重放）。
"use strict";

module.exports = [
  { id: "wave", duration: 600, steps: [] },

  {
    id: "hook",
    duration: 3800,
    steps: [
      { at: 120, patch: { "fx.hookPlay": true } },
      { at: 1000, patch: { "fx.roll": 1 } },
      { at: 1800, patch: { "fx.roll": 2 } },
      { at: 2600, patch: { "fx.roll": 3 } },
    ],
  },

  {
    id: "grade",
    duration: 4600,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 700, patch: { "fx.stageIn": true } },
      { at: 1300, patch: { "fx.scan": true } },
      { at: 2000, patch: { "fx.rows": 1 } },
      { at: 2600, patch: { "fx.rows": 2 } },
      { at: 3200, patch: { "fx.scoreOn": true, "fx.scoreRoll": 5 } },
      { at: 3450, patch: { "fx.scoreRoll": 9 } },
      { at: 3700, patch: { "fx.scoreRoll": 12 } },
    ],
  },

  {
    id: "loop",
    duration: 3200,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 800, patch: { "fx.stageIn": true } },
      { at: 1900, patch: { "fx.taskBox": true } },
    ],
  },

  {
    id: "cta",
    duration: 0,
    steps: [
      { at: 150, patch: { "fx.ctaTitle": true } },
      { at: 900, patch: { "fx.ctaActions": true } },
    ],
  },
];
