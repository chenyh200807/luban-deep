// 题给面板(figure)渲染合同 —— 2026-07-21 视觉信息恢复战役。
// 断言: ①无 figure 整块不渲(fail-closed, 前端零臆造);②viewmodel 是纯几何
// 缩放(签发字段→样式, 不产生内容);③挂载点=签发投影 item.figure;④缩放行为
// (提取 _figureViewModel 源做行为测试, 同 parseConfirmFacts 先例)。
var fs = require("fs");
var path = require("path");
var assert = require("assert");

var retest = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf-8",
);
var retestWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.wxml"),
  "utf-8",
);
var retestWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.wxss"),
  "utf-8",
);

// ① 整块 wx:if 守卫 + label/caption 各自条件渲染
assert.ok(
  retestWxml.indexOf('<view class="rt-fig" wx:if="{{items[currentIndex].figure}}">') >= 0,
  "fig board must be fully hidden when the issued projection has no figure",
);
assert.ok(
  retestWxml.indexOf('wx:if="{{items[currentIndex].figure.label}}"') >= 0 &&
    retestWxml.indexOf('wx:if="{{items[currentIndex].figure.caption}}"') >= 0,
  "fig label/caption must render only when issued",
);
// 元素循环消费 viewmodel 的 style/lab, 不在模板里拼内容
assert.ok(
  retestWxml.indexOf('wx:for="{{items[currentIndex].figure.els}}"') >= 0 &&
    retestWxml.indexOf('style="{{el.style}}"') >= 0 &&
    retestWxml.indexOf("{{el.lab}}") >= 0,
  "fig elements must consume precomputed style/lab verbatim",
);

// ② 挂载点 = 签发投影 item.figure(载入映射), 且 viewmodel 模块级可测
assert.ok(
  retest.indexOf("figure: _figureViewModel(item.figure)") >= 0,
  "figure viewmodel must be built from the issued projection field at load",
);

// ③ 样式类存在(纸墨外框 + 绝对定位画板)
["rt-fig", "rt-fig-board", "rt-fig-el", "rt-fig-label", "rt-fig-caption"].forEach(
  function (cls) {
    assert.ok(retestWxss.indexOf("." + cls) >= 0, "missing style class: " + cls);
  },
);

// ④ 行为: vm sandbox 全模块执行后导出(同 parseConfirmFacts 先例, 零字符串拼函数)
var vmod = require("vm");
var harness = retest + "\n;module.exports.__figureViewModel = _figureViewModel;\n";
var sandbox = { module: { exports: {} }, require: function () { return {}; }, Page: function () {}, console: console };
sandbox.exports = sandbox.module.exports;
vmod.runInNewContext(harness, sandbox, { filename: "retest.js" });
var _figureViewModel = sandbox.module.exports.__figureViewModel;
assert.strictEqual(typeof _figureViewModel, "function", "_figureViewModel must be module-scoped for behavioral test");

assert.strictEqual(_figureViewModel(null), null, "no figure → null");
assert.strictEqual(_figureViewModel({ els: [] }), null, "empty els → null");

var vm = _figureViewModel({
  label: "题给:示例",
  caption: "看图",
  bg: "#23282b",
  h: 100,
  w: 334,
  els: [
    { x: 8, top: 8, w: 100, h: 34, bg: "#2f6db0", r: 8, fg: "#fff", fs: 13, fw: "800", lab: "石材" },
    { x: 0, top: 82, w: 334, h: 12, fg: "#8b9398", fs: 10, lab: "尾注" },
  ],
});
assert.ok(vm && vm.els.length === 2, "viewmodel must project every issued element");
assert.strictEqual(vm.bg, "#23282b", "board bg must pass through verbatim");
// 缩放 = FIG_BOARD_RPX/334; 全宽元素(334px)必须铺满画板
assert.ok(vm.els[1].style.indexOf("width:594rpx") >= 0, "full-width element must span the board");
assert.ok(vm.els[0].style.indexOf("background:#2f6db0") >= 0, "chip bg must pass through verbatim");
assert.strictEqual(vm.els[0].lab, "石材", "labels must be issued text verbatim");
assert.ok(vm.height === Math.round(100 * (594 / 334)), "board height must scale with the same factor");

console.log("PASS test_retest_fig_board.js");
