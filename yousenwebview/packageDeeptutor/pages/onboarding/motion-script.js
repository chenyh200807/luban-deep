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
