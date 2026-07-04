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
// - 文案铁律: 只用「帮你变强」基调, 禁审视揭短词(测试钉死禁词表)。

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

/**
 * 组装复习页 data。
 * @param {object} args {lessons, reviewDue, mistakeBook}
 *   lessons    = GET /api/v1/luban/lessons 响应 body
 *   reviewDue  = GET /api/v1/luban/review-due 响应 body
 *   mistakeBook= mistake-book-view-model.buildMistakeBookViewModel 输出(可空)
 * @returns {object} setData payload
 */
function buildReviewViewModel(args) {
  var a = _safeObj(args);
  var lessonsBody = _safeObj(a.lessons);
  var dueBody = _safeObj(a.reviewDue);
  var mistake = _safeObj(a.mistakeBook);

  var lessons = _safeArr(lessonsBody.lessons).map(function (l) {
    var o = _safeObj(l);
    return { pack_id: _str(o.pack_id).toUpperCase(), title: _str(o.title) };
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
  };
}

module.exports = { buildReviewViewModel: buildReviewViewModel };
