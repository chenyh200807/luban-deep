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

// 站点卡简称(显示层):卡片名用简称保清爽,title 全名不变(详情页/下一站卡仍用全名)
var _shortNames = require("./pack-short-names");

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
    // summary = 后端签发考点卡首卡 front(路线卡副标题真源);缺则 ""(fail-closed 留空)
    // retest = signed 变体池真值(list_green_lessons.retest_available;缺字段=false 保守降级)
    if (id) idx[id] = { title: _str(o.title), sha: _str(o.content_sha256), green: true, summary: _str(o.summary), retest: o.retest_available === true };
  });
  return idx;
}

// 点亮判定唯一权威(学习页/复习页共用, 禁第二套判定):
// 点亮 = 练过及以上(practiced/mastered/dormant)。exposed(只看过讲懂)是
// M0 蓝环接触态, 不算点亮——与 pack_lifecycle_projection 掌握轨口径一致。
function isLitLifecycleState(state) {
  var s = _str(state);
  return s === "practiced" || s === "mastered" || s === "dormant";
}

// lifecycle_state -> 海报三态(墨已学 / 朱推荐 / 纸未学)
function _posterState(state, isRecommended, isGreen) {
  if (isRecommended) return "red";
  if (isLitLifecycleState(state)) return "ink";
  return "paper"; // unlearned / 未知 → 纸(未学);非绿灯叠锁
}

function _litCount(packs) {
  var n = 0;
  Object.keys(packs).forEach(function (k) {
    if (isLitLifecycleState(_safeObj(packs[k]).lifecycle_state)) n += 1;
  });
  return n;
}

// 海报竖排书法名:单列容量 6 字(84×112 海报 / stations 210×280 实测上限),
// 超长截断防溢出——live 绿灯站 26/28 标题 >6 字,不截会折出第二竖列压住 slot 徽标。
// 设计稿(10a)用的是 4 字精选短名;后端无 short_title 字段(对账表已标缺口),
// 截断是显示层止血,不改 title 本身(下一站卡/详情仍用全名)。
var POSTER_NAME_MAX = 6;
function _posterName(title) {
  var t = _str(title);
  return t.length > POSTER_NAME_MAX ? t.slice(0, POSTER_NAME_MAX) : t;
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
    var meta = titleIdx[up] || { title: "", green: false, summary: "" };
    var isRec = up === _str(recommendedId).toUpperCase();
    rows.push({
      pack_id: up,
      title: meta.title || "即将开通",
      name: _shortNames.shortName(up, _posterName(meta.title || "即将开通")),
      slot: up,
      green: !!meta.green,
      state: _posterState(state, isRec, !!meta.green),
      recommended: isRec,
      locked: !meta.green,
      // 副标题:后端 summary(概念卡首卡 front)优先,否则用前端显示层 map(safe-topical)
      subtitle: _shortNames.subtitle(up, meta.summary),
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

// 今日主任务 = 针对推荐薄弱考点的 2 分钟轻练(PRD v1.3 §0.0 / §12.2 TodayMainTaskCard)。
// 前端只投递路由意图,由学习页 handler 按 practice_kind 路由;不判分、不造第二套答题 authority。
// practice_kind = 按签发供给真值路由(承诺宽度收窄,不对空池站渲染练不了的按钮):
//   "seethrough"(该站有签发看穿包) > "retest"(有 signed 变体池 → retest?mode=forward) > "none"(降级)
function _lightPracticeTask(concept, packId, reason, practiceKind) {
  var c = _str(concept) || "你的薄弱点";
  var kind = practiceKind === "seethrough" || practiceKind === "retest" ? practiceKind : "none";
  return {
    title: c + " · 2 分钟轻练",
    reason: _str(reason),
    // primary_cta: 无供给站不渲染主按钮(cta 空 = WXML 隐藏),诚实降级为 supplyNote
    cta: kind === "none" ? "" : "开始 2 分钟轻练",
    secondaryCta: "换轻练",        // secondary_cta:换成更广的综合摸底
    supplyNote: kind === "none" ? "这一站的轻练正在教研签发中 · 先看讲解打底" : "",
    task_type: "light_practice",
    practice_kind: kind,
    estimated_minutes: 2,
    concept: c,
    pack_id: _str(packId).toUpperCase(),
    mode: "topic",                 // assessment 专题模式(聚焦推荐考点)
  };
}

// 看穿库总览 → 有签发看穿包的 pack_id 集合(缺响应/旗标关 = 空集,保守降级)
function _seethroughSet(libraryResp) {
  var set = {};
  _safeArr(_safeObj(libraryResp).packs).forEach(function (p) {
    var id = _str(_safeObj(p).pack_id).toUpperCase();
    if (id) set[id] = true;
  });
  return set;
}

// 供给真值 → practice_kind 单一裁决点(禁在页面层再判一次)
function _practiceKindFor(packId, titleIdx, seethroughSet) {
  var id = _str(packId).toUpperCase();
  if (seethroughSet[id]) return "seethrough";
  if (_safeObj(titleIdx[id]).retest === true) return "retest";
  return "none";
}

/**
 * 组装学习页 data。
 * @param {object} args {homeDashboard, report, lessons, seethroughLibrary}
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

  // ── day-0 兜底(设计 §3 fallback 臂:next_step 缺时落 registry 首个绿灯站)──
  // 让宣纸舞台/下一站卡始终显示(不因无 next_step 塌成空态);诚实=真实绿灯站+群体理由。
  var fallbackUsed = false;
  if (!nextStation) {
    var greenIds = Object.keys(titleIdx);
    if (greenIds.length) {
      var firstGreen = greenIds.sort()[0];
      nextStation = {
        pack_id: firstGreen,
        title: titleIdx[firstGreen].title || "即将开通",
        reason: "从这一站开始 · 点亮你的提分路线",
        mode: "learn_fallback",
        green: true,
        card_sha: titleIdx[firstGreen].sha || "",
      };
      fallbackUsed = true;
    }
  }

  // ── 路线 X/40 ──
  var lit = _litCount(packs);

  // ── 课程架海报(推荐站=nextStation → 朱红) ──
  var posters = _posters(packs, titleIdx, nextStation ? nextStation.pack_id : "");

  // ── 首页路线预览:固定三态(已学完墨 / 匹配薄弱朱 / 会员解锁纸)= 参考设计视觉恒显。
  //    owner 拍板(2026-07-06):黑卡恒显整体更美观;真实每站学习态在「完整路线」地图。
  //    真站名+副标题不变,仅覆盖 state/recommended/locked 供首页 3 卡展示。 ──
  var routePreview = posters.slice(0, 3).map(function (p, i) {
    var st = i === 0 ? "ink" : i === 1 ? "red" : "paper";
    return Object.assign({}, p, { state: st, recommended: st === "red", locked: st === "paper" });
  });

  // ── 复习到期(revalidation_queue items) ──
  var reval = _safeObj(report.revalidation_queue);
  var dueCount = _safeArr(reval.items).length;

  // ── 今日任务(PRD v1.3 §0.0 重心收口:头牌 = 2 分钟 MCQ 轻练,非案例题批改) ──
  // task_type=light_practice + mode=topic:前端只投递路由意图(→ assessment 专题模式),
  // 复用既有 MCQ 摸底流,不判分、不造第二套答题入口、不带案例批改 prompt。
  // 案例题批改按 v1.3 降级为深度护城河层,不再当今日任务默认。
  var seethroughSet = _seethroughSet(a.seethroughLibrary);
  var todayTask = null;
  if (nextStep.mode === "practice_active" && nsRef) {
    todayTask = _lightPracticeTask(
      nsMeta.title || "你的薄弱点",
      nsRef,
      _str(nextStep.reason),
      _practiceKindFor(nsRef, titleIdx, seethroughSet),
    );
  } else if (nextStation) {
    // 有站可学即给通用今日任务(设计始终显示此卡);诚实=针对该站的 2 分钟轻练
    todayTask = _lightPracticeTask(
      nextStation.title || "你的薄弱点",
      nextStation.pack_id,
      "先用一组 2 分钟选择题定位薄弱采分点,答完当场看盲点和教材章节定位。",
      _practiceKindFor(nextStation.pack_id, titleIdx, seethroughSet),
    );
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
    posters: posters,                  // [] → 课程架空态(完整地图/stations 用真实态)
    routePreview: routePreview,        // 首页 3 卡固定三态预览(恒显黑卡)
    dueCount: dueCount,                // 0 → 隐藏复习条
    todayTask: todayTask,              // null → 隐藏今日任务卡
    stats: stats,
    // 供给面可用性(全空 = 后端未部署/无数据,页面走降级但不崩)
    hasSupply: !!(nextStation || posters.length || dueCount || overallMastery),
  };
}

module.exports = {
  buildLearnViewModel: buildLearnViewModel,
  isLitLifecycleState: isLitLifecycleState,
  PACK_UNIVERSE: PACK_UNIVERSE,
};
