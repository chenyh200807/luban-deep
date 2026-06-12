// motion-script.js — 「先体验导学」步序数据（纯数据，无逻辑）
// Fuse 式结构：wave(色浪) → hook(词轮播) → p1/p2/p3(三页文案，光场逐页换色温)
//             → cta(收束)。patch 的 key 是页 data 路径；全部幂等（手动跳幕整幕重放）。
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
    id: "p1",
    duration: 4200,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 1300, patch: { "fx.descIn": true } },
      { at: 2200, patch: { "fx.tags": true } },
    ],
  },

  {
    id: "p2",
    duration: 7000,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 1100, patch: { "fx.descIn": true } },
      { at: 1800, patch: { "fx.tags": true } },
      { at: 2500, patch: { "fx.stageIn": true } },
      { at: 3300, patch: { "fx.scan": true } },
      { at: 4000, patch: { "fx.rows": 1 } },
      { at: 4500, patch: { "fx.rows": 2 } },
      { at: 5100, patch: { "fx.scoreOn": true, "fx.scoreRoll": 5 } },
      { at: 5350, patch: { "fx.scoreRoll": 9 } },
      { at: 5600, patch: { "fx.scoreRoll": 12 } },
    ],
  },

  {
    id: "p3",
    duration: 5800,
    steps: [
      { at: 200, patch: { "fx.copyIn": true } },
      { at: 1100, patch: { "fx.descIn": true } },
      { at: 1800, patch: { "fx.tags": true } },
      { at: 2500, patch: { "fx.stageIn": true } },
      { at: 3800, patch: { "fx.taskBox": true } },
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
