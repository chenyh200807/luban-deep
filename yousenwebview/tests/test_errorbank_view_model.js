// Run: node yousenwebview/tests/test_errorbank_view_model.js
// 错因银行(复习二期二级页)域测试:
// 1. error_code → 人话标签只做呈现层镜像(权威=deeptutor/contracts/error_codes.py);
// 2. R8 解药 fail-closed: 无供给降级为「解药整理中」+ 解析深链, 数据位形状钉死;
// 3. 换皮复测 CTA fail-closed: pack 归属不明/无 canonical due probe → 不承诺换皮;
// 4. 已标记只认服务端 mastered 旗标;复测结果不得在本地摊销单题(源码钉死);
// 5. 文案铁律: 禁审视揭短词; WXML 标签平衡; 页面/路由注册。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(__dirname, "../packageDeeptutor/utils/errorbank-view-model.js");
var vm = require(vmPath);

// ── 1. 错因码人话化(呈现层镜像, 非二次归因) ───────────────────
assert.deepStrictEqual(vm.humanizeErrorLabel("E03"), { label: "关键词缺失", code: "E03" });
assert.deepStrictEqual(vm.humanizeErrorLabel("错因 E06"), { label: "程序顺序错误", code: "E06" });
assert.deepStrictEqual(vm.humanizeErrorLabel("M04"), { label: "选项陷阱", code: "M04" });
assert.deepStrictEqual(vm.humanizeErrorLabel("unknown_error"), { label: "未归因错误", code: "unknown_error" });
// 判分内核给的人话 diagnosis 若整句=注册标签 → 逆映射回码(2026-07-12 契约更新:
// 同一注册表双向镜像, 非二次归因——解锁解药/复测的 (pack, code) 查询键)
assert.deepStrictEqual(vm.humanizeErrorLabel("采分点遗漏"), { label: "采分点遗漏", code: "E02" });
// 非注册表文本仍不硬造码
assert.deepStrictEqual(vm.humanizeErrorLabel("一段自由诊断文本"), { label: "一段自由诊断文本", code: "" });
assert.deepStrictEqual(vm.humanizeErrorLabel(""), { label: "待归因错因", code: "" });

// ── 2. pack 归属诚实匹配(fail-closed: 对不上=空串, 不猜) ───────
var lessons = { lessons: [{ pack_id: "F16", title: "屋面防水" }, { pack_id: "N01", title: "双代号网络计划" }] };
assert.strictEqual(vm.deriveRetestPackId({ concept_label: "屋面防水" }, lessons), "F16");
assert.strictEqual(vm.deriveRetestPackId({ question_id: "n01_case_q3" }, lessons), "N01");
assert.strictEqual(vm.deriveRetestPackId({ tags: ["case", "F16"] }, lessons), "F16");
assert.strictEqual(vm.deriveRetestPackId({ concept_label: "索赔程序" }, lessons), "", "对不上鲁班站→空串, 禁猜归属");
assert.strictEqual(vm.deriveRetestPackId({ concept_label: "屋面防水" }, {}), "", "lessons 缺失→fail-closed");

// ── 3. 列表投影: 待还/已标记分账, 忽略本地影子销账 ────────────
var NOW = Date.parse("2026-07-05T10:00:00+08:00");
var built = vm.buildErrorbankViewModel({
  mistakeBook: {
    items: [
      {
        event_id: "ev1",
        attempt_ref: "ref1",
        title: "屋面防水细部构造 · 案例第 3 问",
        concept_label: "屋面防水",
        error_label: "E03",
        saved_at: "2026-06-28T09:00:00+08:00",
        review_due_at: "2026-07-05T08:00:00+08:00",
      },
      {
        event_id: "ev2",
        attempt_ref: "ref2",
        title: "索赔事件识别",
        concept_label: "索赔程序识别",
        error_label: "计算不完整",
        saved_at: "2026-07-01T09:00:00+08:00",
      },
      {
        event_id: "ev3",
        attempt_ref: "ref3",
        title: "同点再错一笔",
        concept_label: "屋面防水",
        error_label: "E03",
        saved_at: "2026-07-02T09:00:00+08:00",
      },
      {
        event_id: "ev4",
        attempt_ref: "ref4",
        title: "已手动标记的一笔",
        concept_label: "索赔程序",
        error_label: "E05",
        saved_at: "2026-06-20T09:00:00+08:00",
        mastered_at: "2026-06-30T09:00:00+08:00",
      },
      {
        event_id: "ev5",
        attempt_ref: "ref5",
        title: "复测通过的一笔",
        concept_label: "屋面防水",
        error_label: "E06",
        saved_at: "2026-06-21T09:00:00+08:00",
      },
    ],
  },
  lessons: lessons,
  settledLocal: { ev5: { at: Date.parse("2026-07-03T09:00:00+08:00"), packId: "F16" } },
  nowMs: NOW,
});
assert.strictEqual(built.pendingCount, 4, "旧版 settledLocal 输入不得再影响 canonical 列表");
assert.strictEqual(built.settledCount, 1);
assert.strictEqual(built.allClear, false);
assert.strictEqual(built.isEmpty, false);
assert.strictEqual(built.settledPercent, 20, "账本环只认服务端已标记/总数");
assert.ok(built.heroTitle.indexOf("待处理 4 笔") >= 0 && built.heroTitle.indexOf("已标记 1 笔") >= 0);

// 到期在前排序 + 到期 chip
assert.strictEqual(built.pendingEntries[0].key, "ev1", "到期条目排最前");
assert.ok(built.pendingEntries[0].dueChip && built.pendingEntries[0].dueChip.text === "今天到期");
assert.strictEqual(built.pendingEntries[1].dueChip, null, "无到期时间不硬造 chip");

// 错因码人话化落到条目 + 同点已错聚合(呈现层)
assert.strictEqual(built.pendingEntries[0].errorLabel, "关键词缺失");
assert.strictEqual(built.pendingEntries[0].errorCode, "E03");
assert.strictEqual(built.pendingEntries[0].repeatCount, 2);
assert.ok(built.pendingEntries[0].repeatLine.indexOf("已错 2 次") >= 0);
assert.strictEqual(built.pendingEntries[1].repeatLine, "", "单笔不渲染同点提示");

// 复测结果不能在本机把整包结果摊成单题销账;只呈现服务端手动标记。
var retestPending = built.pendingEntries.filter(function (e) { return e.key === "ev5"; })[0];
var manualSettled = built.settledEntries.filter(function (e) { return e.key === "ev4"; })[0];
assert.ok(retestPending, "本地复测镜像不得改变错题服务端状态");
assert.ok(manualSettled && manualSettled.settledLine.indexOf("服务端已标记") >= 0);
assert.strictEqual(manualSettled.settledVia, "manual");

// 空态(待还 0)与全空
var allClear = vm.buildErrorbankViewModel({
  mistakeBook: { items: [{ event_id: "a", attempt_ref: "r", title: "t", mastered_at: "2026-07-01T00:00:00+08:00" }] },
  nowMs: NOW,
});
assert.strictEqual(allClear.allClear, true);
assert.strictEqual(allClear.isEmpty, false, "有已销账时空态仍保留账本(赢过的证据)");
var empty = vm.buildErrorbankViewModel({});
assert.strictEqual(empty.isEmpty, true);
assert.strictEqual(empty.allClear, true);
assert.strictEqual(empty.settledPercent, 0);

// ── 4. 详情四段瀑布: R8 解药 fail-closed + 数据位形状 ─────────
var entry = built.pendingEntries[0];
var detailNoSupply = vm.buildErrorbankDetail(entry, {
  antidote: null,
  retestProbe: null,
  position: { index: 1, total: 3 },
});
assert.strictEqual(detailNoSupply.antidote.state, "pending", "无解药供给→降级态, 禁造讲解");
assert.ok(detailNoSupply.antidote.title.indexOf("解药整理中") >= 0);
assert.ok(detailNoSupply.antidote.desc.indexOf("解析") >= 0, "降级卡导向既有解析");
// 解药 bank 查询键形状钉死: (pack_id, error_code) — 供给上线后按此接入
assert.deepStrictEqual(detailNoSupply.antidoteQuery, { pack_id: "F16", error_code: "E03" });
assert.strictEqual(detailNoSupply.positionLabel, "错因银行 · 第 1 / 3 笔");
assert.strictEqual(detailNoSupply.errorCodeChip, "错因码 E03 · 判分内核直出");

// 供给到位即亮(同一数据位, 不改页面)
var detailSupplied = vm.buildErrorbankDetail(entry, {
  antidote: { mental_model: "按部位找词给分", textbook_ref: "防水工程章节" },
  retestProbe: { available: true, probeId: "probe-f16" },
});
assert.strictEqual(detailSupplied.antidote.state, "ready");
assert.strictEqual(detailSupplied.antidote.text, "按部位找词给分");
assert.strictEqual(detailSupplied.antidote.textbookRef, "防水工程章节");

// 人话 diagnosis 无错因码 → 不硬造码 chip
var noCodeDetail = vm.buildErrorbankDetail(built.pendingEntries[1], { antidote: null });
assert.strictEqual(noCodeDetail.errorCodeChip, "", "无注册表错因码时禁硬造「判分内核直出」chip");

// ── 5. 换皮复测 CTA fail-closed ───────────────────────────────
assert.strictEqual(detailSupplied.retest.ready, true);
assert.strictEqual(detailSupplied.retest.probeId, "probe-f16");
assert.ok(detailSupplied.retest.ctaText.indexOf("换个皮再试一次") >= 0);
assert.strictEqual(
  vm.buildErrorbankDetail(entry, { retestProbe: null }).retest.ready,
  false,
  "变体池未探明→不承诺换皮",
);
assert.strictEqual(
  vm.buildErrorbankDetail(entry, { retestProbe: { available: false } }).retest.ready,
  false,
  "变体池空→不承诺换皮",
);
assert.strictEqual(
  vm.buildErrorbankDetail(entry, { retestProbe: { available: true, probeId: "" } }).retest.ready,
  false,
  "无 canonical probe→不承诺销账复测",
);
var noPackEntry = built.pendingEntries.filter(function (e) { return !e.packId; })[0];
assert.ok(noPackEntry, "样例应含无 pack 归属条目");
assert.strictEqual(
  vm.buildErrorbankDetail(noPackEntry, { retestProbe: { available: true, probeId: "probe-x" } }).retest.ready,
  false,
  "pack 归属不明→即使探测通过也不承诺换皮",
);

// ── 6. 红线源码钉死: 零第二学情权威 ───────────────────────────
var pageDir = path.join(__dirname, "../packageDeeptutor/pages/luban/errorbank");
var pageJs = fs.readFileSync(path.join(pageDir, "errorbank.js"), "utf8");
var pageWxml = fs.readFileSync(path.join(pageDir, "errorbank.wxml"), "utf8");
var pageWxss = fs.readFileSync(path.join(pageDir, "errorbank.wxss"), "utf8");
var vmSource = fs.readFileSync(vmPath, "utf8");
assert.strictEqual(pageJs.indexOf("markMistakeBookItemMastered"), -1, "错因银行禁前端写 mastered 旗标");
assert.strictEqual(pageJs.indexOf("saveMistakeBookItem"), -1, "错因银行禁前端造记账(记账真值=判分内核 writeback)");
assert.strictEqual(pageJs.indexOf("postStationCompleted"), -1, "错因银行只呈现, 信号归 retest 链路");
assert.ok(pageJs.indexOf("getLubanReviewDue") >= 0, "错因银行销账入口只消费 canonical review-due");
assert.strictEqual(pageJs.indexOf("getLubanRetestItems"), -1, "错因银行禁用题池存在性推断到期");
assert.ok(pageJs.indexOf("&mode=review&probe_id=") >= 0, "销账复测必须透传 review mode + probe");
assert.strictEqual(pageJs.indexOf("luban_errorbank_settled_v1"), -1, "禁本地错题销账账本");
assert.strictEqual(pageJs.indexOf("settledLocal"), -1, "禁向视图模型注入本地销账镜像");
var retestPageJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf8",
);
assert.strictEqual(retestPageJs.indexOf("luban_retest_last:"), -1, "复测结果只认服务端 terminal receipt");
assert.strictEqual(vmSource.indexOf("settledLocal"), -1, "视图模型禁读取本地销账镜像");
// R8 解药接线: 详情页按 {pack_id, error_code} 取 signed 解药, 供给后点亮占位。
assert.ok(pageJs.indexOf("getLubanAntidote") >= 0, "错因银行详情须接 R8 解药 GET(供给后点亮)");
var apiSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/api.js"),
  "utf8",
);
assert.ok(
  apiSource.indexOf("/api/v1/luban/antidotes/") >= 0,
  "api.js 须收录 R8 解药只读投影端点(错因银行 detail 消费)",
);

// ── 7. 文案铁律: 禁审视揭短词 ─────────────────────────────────
var FORBIDDEN = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
[
  ["errorbank-view-model.js", vmSource],
  ["errorbank.js", pageJs],
  ["errorbank.wxml", pageWxml],
  ["errorbank.wxss", pageWxss],
].forEach(function (pair) {
  FORBIDDEN.forEach(function (word) {
    assert.strictEqual(pair[1].indexOf(word), -1, pair[0] + " 含禁词「" + word + "」");
  });
});

// ── 8. WXML 标签平衡(自闭合感知) ─────────────────────────────
function checkWxmlBalance(source) {
  var src = source.replace(/<!--[\s\S]*?-->/g, "").replace(/<wxs[\s\S]*?<\/wxs>/g, "");
  var re = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^><"'])*)>/g;
  var stack = [];
  var match;
  while ((match = re.exec(src))) {
    var closing = match[1] === "/";
    var name = match[2];
    var attrs = match[3] || "";
    if (attrs.replace(/\s+$/, "").slice(-1) === "/") continue;
    if (closing) {
      if (!stack.length || stack[stack.length - 1] !== name) {
        return "mismatched </" + name + ">";
      }
      stack.pop();
    } else {
      stack.push(name);
    }
  }
  return stack.length ? "unclosed: " + stack.join(",") : "";
}
assert.strictEqual(checkWxmlBalance(pageWxml), "", "errorbank.wxml 标签必须平衡: " + checkWxmlBalance(pageWxml));

// ── 9. 注册与接线: app.json / route / 复习页入口 ──────────────
var appConfig = fs.readFileSync(path.join(__dirname, "../app.json"), "utf8");
assert.ok(appConfig.indexOf("pages/luban/errorbank/errorbank") >= 0, "app.json 须注册错因银行页");
var routeSource = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/utils/route.js"), "utf8");
assert.ok(routeSource.indexOf("pages/luban/errorbank/errorbank") >= 0, "route.js 须收录错因银行(登录回跳白名单)");
var reviewJs = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.js"), "utf8");
assert.ok(reviewJs.indexOf("route.lubanErrorbank()") >= 0, "复习页错因银行入口卡须指向新列表页");

// ── 暖处方按错因码分文案(呈现层镜像, 全站禁再共用同一句) ──────
// entry(E03) → E03 专属处方; 未收录码/无码 → default 通用句
assert.ok(detailNoSupply.warmLine.indexOf("阅卷认的那几个词") >= 0, "E03 须走关键词缺失专属处方");
var entryNoCode = Object.assign({}, entry, { errorCode: "" });
var detailNoCode = vm.buildErrorbankDetail(entryNoCode, { antidote: null, retestProbe: null });
assert.ok(detailNoCode.warmLine.indexOf("不是不会做") >= 0, "无码走 default 通用句");
var entryE06 = Object.assign({}, entry, { errorCode: "E06" });
var detailE06 = vm.buildErrorbankDetail(entryE06, { antidote: null, retestProbe: null });
assert.notStrictEqual(detailE06.warmLine, detailNoSupply.warmLine, "不同错因码文案必须不同");
// 语气纪律: 全部处方无审视词(禁 看穿/识破/揭穿/露馅)
var vmSource = fs.readFileSync(vmPath, "utf8");
["看穿", "识破", "揭穿", "露馅"].forEach(function (w) {
  assert.ok(vmSource.indexOf(w) === -1, "处方文案禁审视词: " + w);
});

console.log("PASS test_errorbank_view_model.js");

// ── 2026-07-12: 人话标签逆映射 + 解药签发全字段消费 ──
(function () {
  var vm = require("../packageDeeptutor/utils/errorbank-view-model.js");
  // 逆映射: 整句标签/前缀标签 → 注册码(解锁解药查询键)
  var h1 = vm.humanizeErrorLabel("关键词缺失");
  if (h1.code !== "E03") throw new Error("整句标签应逆映射 E03, got " + h1.code);
  var h2 = vm.humanizeErrorLabel("程序顺序错误：层级写反了");
  if (h2.code !== "E06") throw new Error("前缀标签应逆映射 E06, got " + h2.code);
  if (h2.label !== "程序顺序错误：层级写反了") throw new Error("label 保留原句");
  var h3 = vm.humanizeErrorLabel("答案要点没踩到给分点");
  if (h3.code !== "") throw new Error("非注册标签不硬造码");

  // 解药 items 全字段渲染 + 旧形状向后兼容
  var d1 = vm.buildErrorbankDetail(
    { key: "k", errorCode: "E06", packId: "A01" },
    { antidote: { mental_model: "新地图", textbook_ref: "kc:x",
        items: [{ mental_model: "新地图", phenomenon: "现象句", wrong_model: "旧地图", textbook_ref: "kc:x" }] } },
  );
  if (d1.antidote.items.length !== 1) throw new Error("items 渲染");
  if (d1.antidote.items[0].phenomenon !== "现象句" || d1.antidote.items[0].wrongModel !== "旧地图")
    throw new Error("现象/旧地图字段消费");
  var d2 = vm.buildErrorbankDetail(
    { key: "k" },
    { antidote: { mental_model: "只有正文", textbook_ref: "" } },
  );
  if (d2.antidote.items.length !== 1 || d2.antidote.items[0].text !== "只有正文")
    throw new Error("旧形状向后兼容");

  // 早期无码记账的诚实说明
  var d3 = vm.buildErrorbankDetail({ key: "k", errorCode: "" }, {});
  if (!d3.thinNote) throw new Error("无码记账应有诚实说明行");
  var d4 = vm.buildErrorbankDetail({ key: "k", errorCode: "E06" }, {});
  if (d4.thinNote) throw new Error("有码不显说明行");
  // 空 note 不给 kicker
  if (d4.slice.noteKicker) throw new Error("空note不给kicker");
  console.log("PASS 逆映射+解药全字段 10 断言");
})();
