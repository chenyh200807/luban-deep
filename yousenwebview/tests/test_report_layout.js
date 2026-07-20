// test_report_layout.js — regression checks for the hosted learner-facing report page
// (10e 诊断单版式:第 10 轮定稿 + round11 增量①④ + IA Brief「学情=照镜子」)
// Run: node yousenwebview/tests/test_report_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxml"),
  "utf8",
);
var reportWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxss"),
  "utf8",
);
var reportSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
  "utf8",
);
var viewModelSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/learning-report-view-model.js"),
  "utf8",
);
var attemptDetailSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/attempt-detail/attempt-detail.js"),
  "utf8",
);
var attemptDetailWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/attempt-detail/attempt-detail.wxml"),
  "utf8",
);
var mistakeBookWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.wxml"),
  "utf8",
);
var mistakeBookWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.wxss"),
  "utf8",
);
var mistakeBookSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.js"),
  "utf8",
);
var appConfig = fs.readFileSync(path.join(__dirname, "../app.json"), "utf8");

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function assertIncludes(source, needle, message) {
  assert(source.indexOf(needle) >= 0, message);
}

function assertNotIncludes(source, needle, message) {
  assert(source.indexOf(needle) < 0, message);
}

function countOccurrences(source, needle) {
  return source.split(needle).length - 1;
}

// home block slice: 10e 诊断单区(评估「照镜子」约束只看主面,不看深入页)
var homeStart = reportWxml.indexOf("10e 诊断单");
var homeEnd = reportWxml.indexOf("reportDetailView == 'evidence'");
assert(
  homeStart >= 0 && homeEnd > homeStart,
  "report home surface should be the 10e diagnosis sheet block before the evidence detail",
);
var homeBlock = reportWxml.slice(homeStart, homeEnd);

// ── ① 轻量诊断卡:风险档位词,非精确百分比 ─────────────────────
assertIncludes(homeBlock, "{{riskGearLabel}}", "diagnosis card should bind the risk gear word from the read model status");
assertIncludes(homeBlock, "综合风险", "diagnosis card should label the gear as overall risk");
assertNotIncludes(homeBlock, "{{overallMastery}}%", "10e home surface must not show a precise mastery percentage");
assertIncludes(homeBlock, "主要差距", "diagnosis card should lead with the main gap narrative");
assertIncludes(homeBlock, "{{trendNarrative}}", "diagnosis/trend narrative must come from the read model directional projection");
assertIncludes(homeBlock, "lr-diag-fold", "diagnosis card should use the collapsible fold layout");
assertIncludes(homeBlock, 'bindtap="toggleDiagFold"', "diagnosis fold should toggle locally");
assertIncludes(homeBlock, "完整诊断报告", "diagnosis card should keep the full-report (evidence chain) entry");
assertIncludes(reportSource, "toggleDiagFold", "report page should implement the local fold toggle");
assertIncludes(viewModelSource, "riskGearFromStatus", "risk gear word must be a pure translation of backend _score_status — no frontend re-scoring");

// ── ② 掌握地图:40 格全景,四态 + 蓝环第五态 ──────────────────
assertIncludes(homeBlock, "掌握地图", "home should render the mastery map panorama");
assertIncludes(homeBlock, "lr-map-grid", "mastery map should render the 40-cell grid");
assertIncludes(homeBlock, 'wx:for="{{masteryMap.cells}}"', "grid cells must come from the pack_lifecycle read-model projection");
assertIncludes(homeBlock, 'bindtap="openMasteryCell"', "each cell should deep-link back to the learn station");
assertIncludes(reportSource, "/packageDeeptutor/pages/luban/station/station?pack_id=", "cell deep link should target the luban station page");
assertIncludes(homeBlock, "稳了 {{masteryMap.counts.stable}}", "legend should show the stable state");
assertIncludes(homeBlock, "再看一眼 {{masteryMap.counts.watch}}", "legend should show the watch state");
assertIncludes(homeBlock, "待复验 {{masteryMap.counts.reverify}}", "legend should show the reverify state");
assertIncludes(homeBlock, "未学 {{masteryMap.counts.unlearned}}", "legend should show the unlearned state (fourth state must not be folded away)");
// 蓝环第五态:另一条轨,永带"待验证",不进掌握色阶
assertIncludes(homeBlock, "已学·待验证 {{masteryMap.counts.blue}}", "blue-ring legend must exist and always carry 待验证");
assertIncludes(homeBlock, "lr-map-legend-blue", "blue-ring legend must be a separate row, not mixed into the mastery ladder legend");
assertIncludes(reportWxss, ".lr-cell--blue", "blue-ring cell style must exist");
var blueRule = reportWxss.slice(
  reportWxss.indexOf(".lr-cell--blue"),
  reportWxss.indexOf(".lr-cell-bluecheck"),
);
assert(
  blueRule.indexOf("--pk-grn") < 0 &&
    blueRule.indexOf("--pk-warn") < 0 &&
    blueRule.indexOf("--pk-red") < 0,
  "blue-ring visual must never enter the red/yellow/green mastery ladder",
);
assertIncludes(blueRule, "border", "blue-ring cell should be gray base + blue outline");
assertIncludes(homeBlock, "lr-cell-bluecheck", "blue-ring cell should carry the blue check mark");
assertIncludes(viewModelSource, "buildPackMasteryMap", "pack lifecycle map must be a pure view-model projection");
assertIncludes(viewModelSource, 'exposed: { key: "blue", label: "已学·待验证" }', "exposed lifecycle state must map to the blue contact track with 待验证 copy");
// 降级不造数
assertIncludes(homeBlock, "masteryMap.available", "map should render only when the read model provides packs");
assertIncludes(homeBlock, "完成一次学习或作答后", "map empty state should explain instead of faking cells");

// ── 四态修正:observed 不再被折掉(radar/章节) ────────────────
assertIncludes(reportWxml, "{{observedCount}}", "detail views should surface the fourth (observed/未学) state count");
assertIncludes(reportSource, "observedCount", "report radar view model should count observed separately");
assertIncludes(viewModelSource, "observedCount", "shared view model should count observed separately");
assert(
  reportSource.indexOf('pct > 0 ? "weak" : "observed"') >= 0,
  "score-0 dimensions must classify as observed (未学), not weak — no red wall for the unlearned",
);
assertIncludes(reportWxml, "lr-fill-{{ch.status}}", "chapter bars should use backend four-state status classes, not backend hex colors");
// 禁红灯墙:掌握色阶不允许出现亮红/黄硬编码
assertNotIncludes(reportWxss, "#f87171", "mastery ladder must not use alarm red (红灯墙)");
assertNotIncludes(reportWxss, "#fb7185", "mastery ladder must not use alarm red (红灯墙)");

// ── ③ 产品宣言落位(页脚) ────────────────────────────────────
assertIncludes(homeBlock, "我们不给你假绿——考过换皮变体才算数。", "product manifesto must land on the 10e footer verbatim");

// ── ④ 四周趋势:降级为方向性描述,不画假曲线 ────────────────
assertIncludes(homeBlock, "最近趋势", "home should keep a trend card");
assertNotIncludes(homeBlock, "polyline", "no fake trend curve — backend has no numeric time series");
assertNotIncludes(homeBlock, "canvas", "no chart canvas on the 10e home surface");
assertIncludes(viewModelSource, "trend_direction", "trend narrative must derive from long_term_analytics.progression_summary");

// ── ⑤ 分数账本:后端无路线级聚合 → 一行轻占位 ────────────────
assertIncludes(homeBlock, "分数账本", "score ledger placeholder should exist");
assertIncludes(homeBlock, "即将开通", "score ledger must be an honest coming-soon line, not fabricated numbers");
assert(
  homeBlock.indexOf("lr-ledger-line") >= 0 &&
    countOccurrences(homeBlock, "lr-ledger-line") <= 2,
  "score ledger should stay a single quiet line",
);

// ── ⑥ 全页唯一行动键 ────────────────────────────────────────
assert(
  countOccurrences(homeBlock, "去提分路线查看诊断建议") === 1,
  "the honest diagnosis route must be the single action key on the page",
);
assertIncludes(homeBlock, 'bindtap="absorbDiagnosisIntoPlan"', "action key should have a concrete handler");
assertIncludes(reportSource, "route.lubanStations()", "action key must deep-link into the learn tab (weekly plan)");
// 照镜子:主面不做题
assertNotIncludes(homeBlock, "goPractice", "10e home must not offer practice CTAs (照镜子只诊断不做题)");
assertNotIncludes(homeBlock, "去练", "10e home must not offer 去练 buttons");
assertNotIncludes(homeBlock, "开始定向训练", "10e home must not restart the old training hero");
// 学情页零写入:新增 10e 交互只读/深链
assertNotIncludes(homeBlock, "api.save", "10e home surface adds no write paths");

// ── ⑦ 错题本/证据链入口保留,文案禁审视词 ───────────────────
assertIncludes(homeBlock, "错因结构", "home should keep the error-structure card");
assertIncludes(homeBlock, 'bindtap="openMistakeBook"', "error card should deep-link to the mistake book");
assertIncludes(reportSource, "route.mistakeBook()", "report mistake-book action should use the package route helper");
var forbiddenWords = ["看穿", "识破", "揭穿", "露馅"];
forbiddenWords.forEach(function (word) {
  assertNotIncludes(reportWxml, word, "report copy must not use the auditing word " + word);
  assertNotIncludes(reportSource, word, "report source copy must not use the auditing word " + word);
  assertNotIncludes(viewModelSource, word, "view model copy must not use the auditing word " + word);
});

// ── 数据读取:复用既有 API,pack_lifecycle 全景接入 ───────────
assertIncludes(reportSource, "api.getLubanLessons", "map deep-link metadata should reuse the existing lessons API");
assertIncludes(reportSource, "buildPackMasteryMap", "report page should hydrate the mastery map from the shared projection");
assertIncludes(reportSource, "openMasteryCell", "report page should implement the cell tap → six-step panorama");
// 点格 → 内联展开该站六步进展全景(单一权威 stationJourneyFor 校验);
// 深链降级为面板内的绿灯专属 CTA,non-green 由 panel.green 门拦住,绝不产生死链。
assertIncludes(reportSource, "buildStationJourneyPanorama", "cell tap must consume the shared per-station six-step derivation");
assertIncludes(reportSource, "stationJourneyPanel", "cell tap must open the inline six-step panorama panel");
assertIncludes(reportSource, "panel.green", "station deep-link must be gated on green so non-green never yields a broken link");
assertIncludes(reportWxml, "lr-sjp-steps", "report wxml must render the inline six-step track");
assertIncludes(viewModelSource, "正在核对服务端学习记录", "missing/degraded projection must derive a neutral placeholder, never a guessed stage");
assertIncludes(reportWxml, "{{stationJourneyPanel.placeholder}}", "wxml must render the neutral placeholder when the panorama is not ready");

// ── 保留的深入页与证据链契约(旧断言仍然成立的部分) ─────────
assertIncludes(reportWxml, "真实作答证据", "attempt evidence cards should stay in the evidence detail");
assertIncludes(reportWxml, 'class="attempt-card attempt-{{item.tone}}"', "attempt cards should keep a dedicated visual surface");
assertIncludes(reportWxml, 'bindtap="openAttemptDetail"', "attempt card should open detail on tap");
assertIncludes(appConfig, "pages/attempt-detail/attempt-detail", "host attempt detail page should be registered");
assertIncludes(reportSource, "wx.navigateTo", "host attempt detail action should navigate to a full page");
assertIncludes(reportSource, "/packageDeeptutor/pages/attempt-detail/attempt-detail", "host attempt detail action should target the full detail page");
assert(
  reportSource.indexOf("wx.showModal") < 0,
  "host attempt detail should not use a modal because long conversations and explanations get clipped",
);
assertIncludes(attemptDetailSource, "api.getLearningAttemptDetail", "host attempt detail page should call the mobile attempt-detail authority");
assertNotIncludes(attemptDetailWxml, "当时对话", "host attempt detail page should not duplicate the previous conversation transcript below the structured review");
assertNotIncludes(attemptDetailWxml, "detail.turns", "host attempt detail page should not render raw conversation turns after the structured explanation");
assertIncludes(attemptDetailWxml, 'bindtap="goBack"', "host attempt detail page should provide an explicit back button");
assertIncludes(reportWxml, "{{item.timeLabel}}", "attempt card should show time");
assertIncludes(reportWxml, "{{item.resultLabel}}", "attempt card should show result");
assertIncludes(reportWxml, "{{item.answerLine}}", "attempt card should show user/correct answer line from read model");
assertIncludes(reportWxml, "{{item.diagnosisDetail || item.diagnosis}}", "attempt card should show one-line diagnosis from read model");
assertIncludes(reportWxml, "查看解析", "attempt card should expose analysis detail action");
assertIncludes(reportWxml, 'wx:if="{{item.isBookmarked}}"', "attempt card should render cloud bookmark state from read model");
assertIncludes(reportWxml, "{{item.bookmarkLabel || '已加入错题'}}", "attempt card should use backend bookmark label");
assertIncludes(reportWxml, 'wx:elif="{{item.collectable}}"', "attempt card should only expose save action when not already bookmarked");
assertIncludes(reportWxml, "收藏错题", "attempt card should expose mistake-book action without local inference");
assertIncludes(reportSource, "api.saveMistakeBookItem", "mistake-book action should call the cloud mistake-book authority");
assertIncludes(reportWxml, "保存学习卡", "attempt card should expose the P0A source-linked notebook-card save action");
assertIncludes(reportWxml, "我其实会，测一下", "diagnosis challenge should route to a retest instead of writing mastery");
assertIncludes(reportSource, "api.saveNotebookCard", "notebook-card action should call the existing notebook add_record authority");
assertIncludes(reportSource, "note_card_saved", "notebook-card save should emit product behavior through surface-events");
assertIncludes(reportSource, "learner_challenge_mastery", "diagnosis challenge should be a retest intent, not a mastery write");
assertIncludes(appConfig, "pages/mistake-book/mistake-book", "host mistake-book page should be registered");
assertIncludes(mistakeBookSource, "api.getMistakeBook", "mistake-book page should read the cloud mistake-book authority");
assertIncludes(mistakeBookSource, "api.recordMistakeBookItemReview", "mistake-book page should support review recording");
assertIncludes(mistakeBookSource, "api.markMistakeBookItemMastered", "mistake-book page should support mastered state");
assertIncludes(mistakeBookSource, "api.removeMistakeBookItem", "mistake-book page should support removing items");
assertIncludes(mistakeBookWxml, "AI分析", "mistake-book page should expose AI analysis");
assertIncludes(mistakeBookWxml, "高频知识点", "mistake-book page should render concept distribution");
assertIncludes(mistakeBookWxml, "常见错因", "mistake-book page should render error distribution");
assertIncludes(mistakeBookWxml, "看解析", "mistake-book items should deep-link to attempt detail");
assertIncludes(mistakeBookWxss, ".chart-fill", "mistake-book page should include chart styling");
assertIncludes(reportWxml, "{{degradedHint}}", "report page should show degraded/cached summary hint when the network path is unavailable");
assertIncludes(reportWxml, "完成一次案例题批改", "empty state should explain how to generate learning facts");
assert(
  reportWxml.indexOf("eventId") < 0 && reportWxml.indexOf("attemptRef") < 0,
  "host report page should not render raw ids in learner-facing UI",
);
assert(
  reportWxss.indexOf(".level-L1_repeated") >= 0 &&
    reportWxss.indexOf(".level-L2_confirmed") >= 0 &&
    reportWxss.indexOf(".chain-not-improved") >= 0,
  "host report styles should distinguish L1/L2 Learning Brain evidence levels and training outcomes",
);
assert(
  reportWxss.indexOf(".dim-list") >= 0 && reportWxss.indexOf(".dim-bar") >= 0,
  "host report page should include styles for the diagnosis dimension list",
);
assert(
  reportWxss.indexOf(".attempt-card") >= 0 &&
    reportWxss.indexOf(".primary-training-cta") >= 0 &&
    reportWxss.indexOf(".degraded-hint") >= 0,
  "host report styles should cover attempt cards, restrained CTA, and degraded hints",
);
assert(
  reportWxss.indexOf("width: 280px") < 0 && reportWxss.indexOf("height: 280px") < 0,
  "host report radar should not use a fixed px size that can clip on small screens",
);
// 纸墨朱竹 token 落地
assertIncludes(reportWxss, '@import "/packageDeeptutor/styles/paper-ink.wxss"', "10e surface must use the paper-ink token sheet");
assertIncludes(reportWxml, 'class="report-page paper', "report page root must opt into the --pk-* token scope");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
