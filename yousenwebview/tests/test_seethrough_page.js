// node contract 测试:F16 看穿页核心逻辑(4选1本地判 / 选错取诊断干扰项 / Day4采分点自我核对)。
// 用真签发 _F16_seethrough_bank.v0.json 的 item 形状驱动,证逻辑正确 + 前端不自算掌握。
// 运行: node yousenwebview/tests/test_seethrough_page.js
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0, fail = 0, errors = [];
function assert(c, m) { if (c) { pass++; return; } fail++; errors.push("FAIL: " + m); }

// 载入真签发看穿包(前端要吃的真实数据形状)
var bank = JSON.parse(fs.readFileSync(
  path.join(__dirname, "../../docs/原始数据/考点原料/成品/_F16_seethrough_bank.v0.json"), "utf8"));
var days = bank.items.slice().sort(function (a, b) { return a.day - b.day; });

// 加载 seethrough.js,捕获 Page 配置
function loadPage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/luban/seethrough/seethrough.js"), "utf8");
  var captured = null;
  var sandbox = {
    require: function (r) {
      if (r.indexOf("api") >= 0) return { getLubanSeethrough: function () {}, unwrapResponse: function (x) { return x; }, describeRequestError: function () { return "e"; }, postStationCompleted: function () { return Promise.resolve(); } };
      if (r.indexOf("surface-telemetry") >= 0) return { trackProductBehavior: function () {} };
      return {};
    },
    Page: function (cfg) { captured = cfg; },
    wx: { getStorageSync: function () { return null; }, setStorageSync: function () {}, getSystemInfoSync: function () { return {}; } },
    console: console, Date: Date, Number: Number, Array: Array, String: String,
  };
  vm.runInNewContext(source, sandbox, { filename: "seethrough.js" });
  return captured;
}

var cfg = loadPage();
assert(cfg && cfg.data && typeof cfg.onOptionTap === "function", "Page 捕获 + onOptionTap 存在");

// 造一个 this 上下文(data + setData 合并)
function ctx(initData) {
  var self = { data: Object.assign({}, cfg.data, initData) };
  self.setData = function (patch) { Object.assign(self.data, patch); };
  // 绑定所有方法到 self
  Object.keys(cfg).forEach(function (k) { if (typeof cfg[k] === "function") self[k] = cfg[k].bind(self); });
  return self;
}

// ── 4选1 本地判:选对 → correct=true ──
(function () {
  var d1 = days[0]; // Day1 MCQ
  var self = ctx({ days: days, dayIndex: 0, answered: false });
  self.onOptionTap({ currentTarget: { dataset: { oid: d1.correct_option_id } } });
  assert(self.data.answered === true && self.data.correct === true, "选正确项 → correct=true");
  assert(self.data.pickedDistractor === null, "选对不取干扰项");
})();

// ── 4选1 本地判:选错 → 取该干扰项的诊断映射(误解+error_code∈E系) ──
(function () {
  var d1 = days[0];
  var wrong = d1.distractors[0]; // 一个诊断干扰项
  var self = ctx({ days: days, dayIndex: 0, answered: false });
  self.onOptionTap({ currentTarget: { dataset: { oid: wrong.option_id } } });
  assert(self.data.correct === false, "选干扰项 → correct=false");
  assert(self.data.pickedDistractor && self.data.pickedDistractor.error_code === wrong.error_code,
    "选错 → 取到该干扰项的 error_code=" + wrong.error_code);
  assert(/^[EM]/.test(self.data.pickedDistractor.error_code), "error_code ∈ E/M 系");
})();

// ── Day4 采分点自我核对:命中(含全部 required_terms)/ 漏点 ──
(function () {
  var d4 = days.find(function (x) { return x.day === 4; });
  assert(d4 && d4.answer_mode === "semi_write", "Day4 = 半写");
  var p10 = d4.scoring_points[0];
  // 作答含 P10 全部 required_terms → 命中 P10;不含 P11 → 漏 P11
  var answer = p10.required_terms.join("、");
  var self = ctx({ days: days, dayIndex: days.indexOf(d4), draft: answer });
  self.goSelfCheck();
  var sc = self.data.selfCheck;
  assert(sc && sc.total === d4.scoring_points.length, "自我核对覆盖全部采分点");
  var hitP10 = sc.points.find(function (p) { return p.point_id === "P10"; });
  var hitP11 = sc.points.find(function (p) { return p.point_id === "P11"; });
  assert(hitP10.hit === true, "含 P10 全关键词 → P10 命中");
  assert(hitP11.hit === false, "不含 P11 关键词 → P11 漏点");
  assert(sc.hitCount === 1, "命中计数=1");
})();

// ── 红线:页逻辑不产生掌握态字段(仅 correct/completedDays 呈现) ──
(function () {
  var self = ctx({ days: days, dayIndex: 0, answered: false });
  self.onOptionTap({ currentTarget: { dataset: { oid: days[0].correct_option_id } } });
  assert(!("mastery" in self.data) && !("mastered" in self.data), "页 data 无掌握态字段(不自算)");
})();

if (fail > 0) { console.error(errors.join("\n")); console.error("\nseethrough-page: " + pass + " passed, " + fail + " FAILED"); process.exit(1); }
console.log("seethrough-page: " + pass + " passed");
