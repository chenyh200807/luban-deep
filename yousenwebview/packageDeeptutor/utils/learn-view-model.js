// learn-view-model.js — 学习 tab(纸墨朱竹宣纸驾驶舱)纯函数视图模型
//
// 输入: 后端 read model 原始响应(homeDashboard / report / lessons)
// 输出: 学习页 setData 形状。全程 optional-chaining 降级——任一字段缺
//       (= test2 后端未部署时的常态)不抛、给合理空态,整页不崩。
//
// 单一权威边界(融合计划 §8 / 五模块 Brief H1/H3/H5):
// - 前端不算分/不算掌握——只投影 read model 字段,零推断。
// - 母题绑 manifest pack_id(lessons/pack_lifecycle 真实 pack),禁硬编码 F/S 站;
//   非绿灯 pack 一律"即将开通"(H3)。
// - 掌握态只读 lifecycle_state,不发明判分语义(H5)。

var PACK_UNIVERSE = 40; // 60-slot 注册表 40 pack(融合计划 §1.1)

function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _safeArr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v);
}
function _int(v) {
  var n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : 0;
}

// pack_id -> title,来自绿灯 lessons(H3:只有绿灯是可学的真站)
function _titleIndex(lessonsResp) {
  var idx = {};
  _safeArr(_safeObj(lessonsResp).lessons).forEach(function (l) {
    var o = _safeObj(l);
    var id = _str(o.pack_id).toUpperCase();
    if (id) idx[id] = { title: _str(o.title), sha: _str(o.content_sha256), green: true };
  });
  return idx;
}

// lifecycle_state -> 海报三态(墨已学 / 朱推荐 / 纸未学)
function _posterState(state, isRecommended, isGreen) {
  if (isRecommended) return "red";
  if (state === "mastered" || state === "practiced" || state === "dormant") return "ink";
  return "paper"; // unlearned / 未知 → 纸(未学);非绿灯叠锁
}

function _litCount(packs) {
  var n = 0;
  Object.keys(packs).forEach(function (k) {
    var s = _str(_safeObj(packs[k]).lifecycle_state);
    if (s === "practiced" || s === "mastered" || s === "dormant") n += 1;
  });
  return n;
}

// 课程架/路线图海报:推荐站置顶,再已学,再未学;并入绿灯 lessons
// (无 lifecycle 时 test2 仍显真实绿灯站,不空)。标题来自绿灯 lessons,缺则占位。
function _posters(packs, titleIdx, recommendedId) {
  var rows = [];
  var seen = {};
  function push(id, state) {
    var up = _str(id).toUpperCase();
    if (!up || seen[up]) return;
    seen[up] = true;
    var meta = titleIdx[up] || { title: "", green: false };
    var isRec = up === _str(recommendedId).toUpperCase();
    rows.push({
      pack_id: up,
      title: meta.title || "即将开通",
      slot: up,
      green: !!meta.green,
      state: _posterState(state, isRec, !!meta.green),
      recommended: isRec,
      locked: !meta.green,
    });
  }
  // 推荐站先
  if (recommendedId) push(recommendedId, _str(_safeObj(packs[_str(recommendedId).toUpperCase()]).lifecycle_state));
  // 已学(墨)
  Object.keys(packs).forEach(function (k) {
    var s = _str(_safeObj(packs[k]).lifecycle_state);
    if (s === "practiced" || s === "mastered" || s === "dormant") push(k, s);
  });
  // lifecycle 其余(未学/纸)
  Object.keys(packs).forEach(function (k) {
    push(k, _str(_safeObj(packs[k]).lifecycle_state));
  });
  // 并入绿灯 lessons(lifecycle 缺失时的真实站源;已 seen 的跳过)
  Object.keys(titleIdx).forEach(function (id) {
    push(id, _str(_safeObj(packs[id]).lifecycle_state));
  });
  return rows;
}

/**
 * 组装学习页 data。
 * @param {object} args {homeDashboard, report, lessons}
 * @returns {object} setData payload
 */
function buildLearnViewModel(args) {
  var a = _safeObj(args);
  var dash = _safeObj(a.homeDashboard);
  var report = _safeObj(a.report);
  var titleIdx = _titleIndex(a.lessons);

  var lifecycle = _safeObj(report.pack_lifecycle);
  var packs = _safeObj(lifecycle.packs);
  var universe = _safeArr(lifecycle.state_machine).length ? PACK_UNIVERSE : PACK_UNIVERSE;

  // ── 下一站卡(next_step 呈现仲裁,H3 只认真实 pack) ──
  var nextStep = _safeObj(dash.next_step);
  var nsRef = _str(nextStep.source_ref).toUpperCase();
  var nsMeta = titleIdx[nsRef] || {};
  var nextStation = null;
  if (nextStep.mode && nextStep.mode !== "unavailable" && nsRef) {
    nextStation = {
      pack_id: nsRef,
      title: nsMeta.title || "即将开通",
      reason: _str(nextStep.reason),
      mode: _str(nextStep.mode),
      green: !!nsMeta.green,
      card_sha: _str(nsMeta.sha),
    };
  }

  // ── 路线 X/40 ──
  var lit = _litCount(packs);

  // ── 课程架海报 ──
  var posters = _posters(packs, titleIdx, nextStation ? nextStation.pack_id : "");

  // ── 复习到期(revalidation_queue items) ──
  var reval = _safeObj(report.revalidation_queue);
  var dueCount = _safeArr(reval.items).length;

  // ── 今日任务(next_step practice 臂 / 处方;降级隐藏) ──
  var todayTask = null;
  if (nextStep.mode === "practice_active" && nsRef) {
    todayTask = {
      title: (nsMeta.title || "薄弱点") + " · 半写训练",
      reason: _str(nextStep.reason),
      cta: "开始半写训练",
    };
  }

  // ── 指标卡(report stats,尽力读+降级) ──
  var overview = _safeObj(report.overview);
  var mastery = _safeObj(report.mastery);
  var overallMastery = _int(
    (mastery.overall_mastery && mastery.overall_mastery.score) != null
      ? mastery.overall_mastery.score
      : overview.overall_mastery
  );
  var stats = {
    recent_practice: _int(overview.recent_three_done),
    pending_errors: _int(overview.weak_point_count != null ? overview.weak_point_count : overview.pending_error_count),
    mastery_trend: overallMastery,
  };

  return {
    litCount: lit,
    packUniverse: universe,
    nextStation: nextStation,          // null → 显示"内容即将上线"空态卡
    posters: posters,                  // [] → 课程架空态
    dueCount: dueCount,                // 0 → 隐藏复习条
    todayTask: todayTask,              // null → 隐藏今日任务卡
    stats: stats,
    // 供给面可用性(全空 = 后端未部署/无数据,页面走降级但不崩)
    hasSupply: !!(nextStation || posters.length || dueCount || overallMastery),
  };
}

module.exports = { buildLearnViewModel: buildLearnViewModel, PACK_UNIVERSE: PACK_UNIVERSE };
