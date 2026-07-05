// review-view-model.js — 复习 tab(第10轮 10c 回炉屏)纯函数视图模型
//
// 输入: 后端 read model 原始响应(lessons / reviewDue / mistakeBook 视图模型输出)
// 输出: 复习页 setData 形状。全程降级——任一字段缺(后端旗标关/未部署)不抛、
//       给诚实空态, 整页不崩。
//
// 单一权威边界(双轮 §6 / contracts/learner-state.md Review Due Projection):
// - 到期语义唯一权威 = 服务端 /api/v1/luban/review-due(revalidation_queue 投影),
//   前端零探测零调度零自算间隔。
// - retest_available=false 的站 fail-closed 隐藏「换皮」承诺句(现状仅 2 变体池,
//   禁对无池站承诺换皮复测), 回炉动作降级为回站重看。
// - 错因聚合 = 云端错题集 read model(mistake-book-view-model), 禁第二套错因分类。
// - 点亮语义: 绿灯(published)只是可学≠点亮(learned)。点亮真值 = report.pack_lifecycle,
//   判定复用 learn-view-model 的 isLitLifecycleState(与学习页同一权威, 禁第二套判定);
//   lifecycle 不可用时不造数——既不标已点亮也不标未点亮。
// - 文案铁律: 只用「帮你变强」基调, 禁审视揭短词(测试钉死禁词表)。
var isLitLifecycleState = require("./learn-view-model").isLitLifecycleState;

function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _safeArr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v);
}

// 换皮承诺句只许出现在 retest_available=true 的条目上(fail-closed)
var PROMISE_SUB = "换皮复测 · 数字主体换了皮，判别逻辑没变";
var FALLBACK_SUB = "已到期 · 变体准备中，先回站里再看一眼";

function _dueEntry(item) {
  var o = _safeObj(item);
  var packId = _str(o.pack_id).toUpperCase();
  var retestAvailable = o.retest_available === true;
  return {
    packId: packId,
    title: _str(o.title) || packId,
    dueAt: _str(o.due_at),
    retestAvailable: retestAvailable,
    // action 由 vm 定死: 前端页面只按此路由, 不再各处判一次(单一判定点)
    action: retestAvailable ? "retest" : "station",
    sub: retestAvailable ? PROMISE_SUB : FALLBACK_SUB,
  };
}

// 检索行(按母题)文案: 点亮态来自 lifecycle, lifecycle 缺失时诚实中性(不造数)
var LIT_SUB = "已点亮 · 回站重看";
var UNLIT_SUB = "还没点亮 · 去站里过一遍";
var UNKNOWN_SUB = "回站重看";

/**
 * 组装复习页 data。
 * @param {object} args {lessons, reviewDue, mistakeBook, report, conceptCards}
 *   lessons    = GET /api/v1/luban/lessons 响应 body
 *   reviewDue  = GET /api/v1/luban/review-due 响应 body
 *   mistakeBook= mistake-book-view-model.buildMistakeBookViewModel 输出(可空)
 *   report     = GET /api/v1/learning/report 响应 body(pack_lifecycle 点亮真值,可空降级)
 *   conceptCards = GET /api/v1/luban/concept-cards 响应 body(可空降级——
 *                  张数真值=signed 卡池投影; 拿不到/旗标关/零签发池一律回
 *                  「即将开通」占位, 前端绝不自造卡数)
 * @returns {object} setData payload
 */
function buildReviewViewModel(args) {
  var a = _safeObj(args);
  var lessonsBody = _safeObj(a.lessons);
  var dueBody = _safeObj(a.reviewDue);
  var mistake = _safeObj(a.mistakeBook);
  var conceptCards = _safeObj(a.conceptCards);
  var conceptCardTotal =
    Number(conceptCards.total) > 0 ? Math.round(Number(conceptCards.total)) : 0;
  var lifecyclePacks = _safeObj(_safeObj(_safeObj(a.report).pack_lifecycle).packs);
  // lifecycle 供给可用才敢断言点亮/未点亮; 缺失(旧后端/请求失败)= unknown 不造数
  var litKnown = Object.keys(lifecyclePacks).length > 0;

  var lessons = _safeArr(lessonsBody.lessons).map(function (l) {
    var o = _safeObj(l);
    var packId = _str(o.pack_id).toUpperCase();
    var lit = litKnown && isLitLifecycleState(_safeObj(lifecyclePacks[packId]).lifecycle_state);
    return {
      pack_id: packId,
      title: _str(o.title),
      lit: lit,
      sub: lit ? LIT_SUB : litKnown ? UNLIT_SUB : UNKNOWN_SUB,
      linkText: lit || !litKnown ? "回看" : "去学",
    };
  });

  var dueEntries = _safeArr(dueBody.due).map(_dueEntry);
  var learnedCount = Number(dueBody.learned_count) > 0 ? Math.round(Number(dueBody.learned_count)) : 0;
  var dueCount = dueEntries.length;
  var firstDue = dueCount ? dueEntries[0] : null;

  return {
    lessons: lessons,
    dueEntries: dueEntries,
    dueCount: dueCount,
    learnedCount: learnedCount,
    duePercent: learnedCount ? Math.round((dueCount / learnedCount) * 100) : 0,
    firstDue: firstDue,
    // 昨天的约定卡 = 换皮复测的兑现——只有真有变体池才渲染(fail-closed)
    showPact: !!(firstDue && firstDue.retestAvailable),
    // 空态: 一站未点亮(D1 铁律, 深链学习)
    isEmpty: !lessons.length,
    // -1 = 计数未取到(错因银行入口降级为无计数, 不造数)
    mistakeActiveCount:
      typeof mistake.activeCount === "number" && mistake.activeCount >= 0
        ? mistake.activeCount
        : -1,
    errorBars: _safeArr(mistake.errorBars),
    // 考点卡库入口(单一判定点): 只有 signed 卡池真有卡才开门,
    // 其余(旗标关/请求失败/零签发)一律回「即将开通」占位——fail-closed。
    conceptCardsAvailable: conceptCardTotal > 0,
    conceptCardTotal: conceptCardTotal,
  };
}

module.exports = { buildReviewViewModel: buildReviewViewModel };
