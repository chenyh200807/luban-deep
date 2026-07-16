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

var PACK_UNIVERSE = 40; // 仅兼容尚未返回 pack_universe 的旧后端；正式值来自 lessons API。

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
function _packUniverse(lessonsResp) {
  var n = _int(_safeObj(lessonsResp).pack_universe);
  return n > 0 ? n : PACK_UNIVERSE;
}

// pack_id -> title,来自绿灯 lessons(H3:只有绿灯是可学的真站)
function _titleIndex(lessonsResp) {
  var idx = {};
  _safeArr(_safeObj(lessonsResp).lessons).forEach(function (l) {
    var o = _safeObj(l);
    var id = _str(o.pack_id).toUpperCase();
    // summary = 后端签发考点卡首卡 front(路线卡副标题真源);缺则 ""(fail-closed 留空)
    // retest = 签发供给 + rollout 双闸后的可完成真值；缺字段=false 保守降级。
    if (id) idx[id] = {
      title: _str(o.title),
      sha: _str(o.content_sha256),
      green: true,
      // 三态供给真值：true/false 来自新 lessons API；null 表示旧 API 未签发该字段。
      // 未知不能被前端擅自降成 false，最终由详情接口 card_url 裁决。
      card_hosted: o.card_hosted === true ? true : (o.card_hosted === false ? false : null),
      summary: _str(o.summary),
      retest: o.light_practice_available === true,
    };
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
    var meta = titleIdx[up] || { title: "", green: false, card_hosted: false, summary: "" };
    var isRec = up === _str(recommendedId).toUpperCase();
    rows.push({
      pack_id: up,
      title: meta.title || "即将开通",
      name: _shortNames.shortName(up, _posterName(meta.title || "即将开通")),
      slot: up,
      green: !!meta.green,
      card_hosted: meta.card_hosted === true ? true : (meta.card_hosted === false ? false : null),
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

// ── 站点旅程轨道(10a改):步骤集合硬编码这 6 步,禁出现不存在的步骤 ──
// 状态派生只用现有可得信号(next_step.mode = 是否有未完成 forward / due probe),
// 不新增后端调用;拿不准的步保守显示为空心(future),不造假。
// promise 步(明日验证/3 日抽查)= 系统的承诺,未到点用竹青虚环。
var JOURNEY_STEPS = ["动画讲懂", "训练 5 题", "错因讲评", "轻练确认", "明日验证", "3 日抽查"];
var JOURNEY_PROMISE_FROM = 4; // steps[4], steps[5] 为承诺步

function _journeyFor(taskState) {
  // 当前步(1-based)单点裁决:
  // learn_next → 1(动画讲懂);practice_active(有未完成 forward)→ 2(训练);
  // review_due(有 due probe = 站内旅程已走完并进入承诺兑现)→ 5(明日验证)。
  var current = taskState === "review_due" ? 5 : taskState === "practice_active" ? 2 : 1;
  // done 只标有观测依据的步:due probe 只在站完成信号后签发 → 1-3(讲评随训练)可信;
  // 轻练确认(4)无独立完成信号 → 保守留空心。
  var doneUpTo = taskState === "review_due" ? 3 : taskState === "practice_active" ? 1 : 0;
  var steps = JOURNEY_STEPS.map(function (label, i) {
    var n = i + 1;
    var state =
      n <= doneUpTo ? "done" : n === current ? "current" : i >= JOURNEY_PROMISE_FROM ? "promise" : "future";
    return { label: label, state: state };
  });
  return {
    steps: steps,
    currentIndex: current,
    total: JOURNEY_STEPS.length,
    // 轨道已走线占比(节点心到节点心共 5 段);环形进度 = 当前步/6。均为事实计数,非掌握度。
    progressRatio: Math.round(((current - 1) / (JOURNEY_STEPS.length - 1)) * 100) / 100,
    // 已走线宽度(相对整条 track 容器):首尾各留 100%/12 到节点心,可走满幅 = 83.34%。
    // 预算成纯百分数,避免 wxml 内插 calc 的兼容风险(既有惯例=width: {{x}}%)。
    lineFillPercent:
      Math.round(((current - 1) / (JOURNEY_STEPS.length - 1)) * 83.34 * 100) / 100,
    ringPercent: Math.round((current / JOURNEY_STEPS.length) * 100),
  };
}

// 今日任务只投影一个动作。到期验证与课后练共用 retest 内核；前端不判断
// 掌握、不重算到期，也不把任何 Pack 专属 spike 提升成首页 authority。
function _retestTask(concept, packId, reason, practiceKind, taskState) {
  var c = _str(concept) || "你的薄弱点";
  var kind = practiceKind === "retest" ? "retest" : "none";
  var reviewDue = taskState === "review_due";
  return {
    // 「训练 5 题」只在 retest 池真可用时承诺(供给真值门,禁空头题量)
    title: c + (reviewDue ? " · 到期验证" : kind === "retest" ? " · 训练 5 题" : " · 课后检验"),
    reason: _str(reason),
    cta: kind === "none"
      ? ""
      : reviewDue
      ? "用 2 分钟验证昨天的盲点"
      : "完成刚学内容的 5 题检验",
    // 主按钮短文案随任务类型;无供给不给按钮(禁 dead click)
    ctaLabel: kind === "none" ? "" : reviewDue ? "开始验证" : "开始训练",
    supplyNote: kind === "none"
      ? reviewDue
        ? "这次验证暂时没有安全题；学习记录仍会保留"
        : "这一站的课后题正在教研签发中 · 先看讲解打底"
      : "",
    task_type: reviewDue ? "review_due" : "light_practice",
    task_state: reviewDue ? "review_due" : "practice_active",
    action_kind: "retest",
    practice_kind: kind,
    estimated_minutes: 2,
    concept: c,
    pack_id: _str(packId).toUpperCase(),
    training_intent_id: "",
    probe_id: "",
    mode: reviewDue ? "review" : "forward",
  };
}

// 供给真值 → practice_kind 单一裁决点(禁在页面层再判一次)
function _practiceKindFor(packId, titleIdx) {
  var id = _str(packId).toUpperCase();
  if (_safeObj(titleIdx[id]).retest === true) return "retest";
  return "none";
}

function _lessonTask(station) {
  var s = _safeObj(station);
  var available = s.green === true && s.card_hosted !== false;
  return {
    title: _str(s.title) || "最需要提分的考点",
    reason: _str(s.reason) || "先学懂这一小节，再用五题确认",
    cta: available ? "学这一小节，随后做 5 题" : "",
    ctaLabel: available ? "继续学习" : "",
    supplyNote: available ? "" : "这一节微课正在制作中",
    task_type: "microlesson",
    task_state: "learn_next",
    action_kind: "lesson",
    practice_kind: "",
    estimated_minutes: 5,
    concept: _str(s.title),
    pack_id: _str(s.pack_id).toUpperCase(),
    training_intent_id: "",
    probe_id: "",
    mode: "learn",
  };
}

// homeDashboard.next_step 是学习首页唯一任务 authority。本函数只做协议到
// 展示动作的翻译；lessons 仅回答该任务的内容/题目供给是否已签发，不能在
// next_step 缺失时自行补一个“推荐任务”。学习页与学情页必须共用本函数。
function buildCanonicalLearningTask(args) {
  var a = _safeObj(args);
  var dash = _safeObj(a.homeDashboard);
  var nextStep = _safeObj(dash.next_step);
  var mode = _str(nextStep.mode);
  var titleIdx = _titleIndex(a.lessons);
  var sourceRef = _str(nextStep.source_ref);
  var packId = _str(
    mode === "practice_active" || mode === "review_due"
      ? nextStep.target_pack_id
      : nextStep.source_ref,
  ).toUpperCase();
  if (!packId) return null;
  var pack = _safeObj(titleIdx[packId]);

  // 任务级公共派生:旅程轨道(6 步硬编码)+ 轻练旁按钮供给真值。
  // 轻练供给唯一裁决点仍是 _practiceKindFor(禁页面层再判一次)。
  function _decorate(task) {
    if (!task) return task;
    task.journey = _journeyFor(task.task_state);
    task.light_practice_available = _practiceKindFor(packId, titleIdx) === "retest";
    return task;
  }

  if (mode === "review_due") {
    var reviewTask = _retestTask(
      pack.title || "你的薄弱点",
      packId,
      _str(nextStep.reason),
      _practiceKindFor(packId, titleIdx),
      "review_due",
    );
    reviewTask.probe_id = sourceRef;
    return _decorate(reviewTask);
  }
  if (mode === "practice_active") {
    var practiceTask = _retestTask(
      pack.title || "刚学内容",
      packId,
      _str(nextStep.reason),
      _practiceKindFor(packId, titleIdx),
      "practice_active",
    );
    practiceTask.training_intent_id = sourceRef;
    return _decorate(practiceTask);
  }
  if (mode !== "learn_next") return null;
  return _decorate(_lessonTask({
    pack_id: packId,
    title: pack.title || "即将开通",
    reason: _str(nextStep.reason),
    green: pack.green === true,
    card_hosted: pack.card_hosted,
  }));
}

// ── 复习卡(10a改):只是到期状态视图,不是第二任务源 ──
// 单一权威红线:任务卡内容由 home_next_step_projection 唯一裁决——有到期时
// next_step 自动是验证任务;本卡只在该裁决已落地(todayTask=review_due 且
// retest 可路由)时把到期计数可视化,点击走与任务卡完全相同的路由(页面绑
// goTodayTask,零第二套路由/优先级)。authority 不明或降级一律隐藏(fail-closed)。
function _buildReviewCard(report, todayTask) {
  var packReview = _safeObj(_safeObj(report).pack_review);
  var authorityKnown =
    packReview.enabled === true &&
    packReview.degraded !== true &&
    _str(packReview.authority) === "revalidation_queue";
  if (!authorityKnown) return null;
  var dueCount = _safeArr(packReview.due).length;
  if (dueCount <= 0) return null;
  var task = _safeObj(todayTask);
  // next_step 没裁决为到期验证 → 不渲染(禁自算优先级);
  // 验证任务无可路由 retest 供给 → 不渲染(禁 dead click)。
  if (task.task_state !== "review_due" || task.practice_kind !== "retest") return null;
  return {
    dueCount: dueCount,
    title: "复习 · 昨天的 " + dueCount + " 个点到期",
    sub: "换题验证 · 约 2 分钟 · 通过即亮「已验证」",
    cta: "去验证",
  };
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
  var universe = _packUniverse(a.lessons);

  // ── 下一站卡(next_step 呈现仲裁,H3 只认真实 pack) ──
  var nextStep = _safeObj(dash.next_step);
  var sourceRef = _str(nextStep.source_ref);
  var nsRef = _str(
    nextStep.mode === "practice_active" || nextStep.mode === "review_due"
      ? nextStep.target_pack_id
      : nextStep.source_ref,
  ).toUpperCase();
  var nsMeta = titleIdx[nsRef] || {};
  var greenIds = Object.keys(titleIdx).sort();
  var hostedIds = greenIds.filter(function (id) { return titleIdx[id].card_hosted; });
  var nextStation = null;
  if (nextStep.mode && nextStep.mode !== "unavailable" && nsRef) {
    nextStation = {
      pack_id: nsRef,
      title: nsMeta.title || "即将开通",
      reason: _str(nextStep.reason),
      mode: _str(nextStep.mode),
      green: !!nsMeta.green,
      card_hosted: nsMeta.card_hosted === true ? true : (nsMeta.card_hosted === false ? false : null),
      card_sha: _str(nsMeta.sha),
      evidenceBacked: _safeArr(nextStep.evidence_refs).length > 0,
    };
  }

  // 学习页头牌承担“点开即学”的承诺：个性化 next_step 若暂未托管微课，
  // 仍留在完整路线/今日任务中，但头牌降级推荐一节真实可播放微课。
  // card_hosted 只来自 lessons manifest 投影，前端不靠 URL/pack_id 猜供给。
  if (nextStation && nextStation.card_hosted === false && hostedIds.length) {
    var firstHosted = hostedIds[0];
    nextStation = {
      pack_id: firstHosted,
      title: titleIdx[firstHosted].title || "即将开通",
      reason: "推荐先看这节可播放微课 · 点亮你的提分路线",
      mode: "hosted_fallback",
      green: true,
      card_hosted: true,
      card_sha: titleIdx[firstHosted].sha || "",
      evidenceBacked: false,
    };
  }

  // ── day-0 兜底(设计 §3 fallback 臂:next_step 缺时落 registry 首个绿灯站)──
  // 让宣纸舞台/下一站卡始终显示(不因无 next_step 塌成空态);诚实=真实绿灯站+群体理由。
  var fallbackUsed = false;
  if (!nextStation) {
    // day-0 入口优先选择真实已有动画卡；无卡绿灯站仍保留在路线中。
    if (greenIds.length) {
      var unknownIds = greenIds.filter(function (id) { return titleIdx[id].card_hosted === null; });
      var firstGreen = hostedIds[0] || unknownIds[0] || greenIds[0];
      nextStation = {
        pack_id: firstGreen,
        title: titleIdx[firstGreen].title || "即将开通",
        reason: "从这一站开始 · 点亮你的提分路线",
        mode: "learn_fallback",
        green: true,
        card_hosted: titleIdx[firstGreen].card_hosted,
        card_sha: titleIdx[firstGreen].sha || "",
        evidenceBacked: false,
      };
      fallbackUsed = true;
    }
  }

  // ── 路线 X/40 ──
  var lit = _litCount(packs);

  // ── 课程架海报(推荐站=nextStation → 朱红) ──
  var posters = _posters(packs, titleIdx, nextStation ? nextStation.pack_id : "");

  // 首页预览只裁切真实投影，禁止为视觉效果覆写已学/推荐/锁定状态。
  var routePreview = posters.slice(0, 3);

  // ── 今日唯一任务：直接投影 server next_step，不在前端重排优先级 ──
  // next_step 的 review_due 已由 home_next_step_projection 读取 canonical
  // revalidation queue 后裁决；本层只把状态翻译成对应动作。
  var todayTask = buildCanonicalLearningTask({
    homeDashboard: a.homeDashboard,
    lessons: a.lessons,
  });

  // ── 复习卡:到期状态视图(数据=pack_review 投影;裁决权仍在 next_step) ──
  var reviewCard = _buildReviewCard(report, todayTask);

  // ── 行为指标只透传事实计数；首页不呈现或解释 mastery 百分比 ──
  var overview = _safeObj(report.overview);
  var learnerSettings = _safeObj(dash.learner_settings);
  var stats = {
    recent_practice: _int(overview.recent_three_done),
    pending_errors: _int(overview.weak_point_count != null ? overview.weak_point_count : overview.pending_error_count),
  };
  var dailyTarget = _int(overview.daily_target || learnerSettings.daily_target);
  var todayDone = _int(overview.today_done);

  return {
    litCount: lit,
    packUniverse: universe,
    nextStation: nextStation,          // null → 显示"内容即将上线"空态卡
    posters: posters,                  // [] → 课程架空态(完整地图/stations 用真实态)
    routePreview: routePreview,        // 首页 3 卡真实状态预览
    todayTask: todayTask,              // null → 隐藏今日任务卡
    reviewCard: reviewCard,            // null → 隐藏复习卡(到期 0 / 权威不明 / 未裁决到期)
    stats: stats,
    examDate: _str(learnerSettings.exam_date),
    todayProgress: {
      done: todayDone,
      target: dailyTarget,
      percent: dailyTarget ? Math.min(100, Math.round((todayDone / dailyTarget) * 100)) : 0,
    },
    // 供给面可用性(全空 = 后端未部署/无数据,页面走降级但不崩)
    hasSupply: !!(nextStation || posters.length || todayTask),
  };
}

module.exports = {
  buildLearnViewModel: buildLearnViewModel,
  buildCanonicalLearningTask: buildCanonicalLearningTask,
  isLitLifecycleState: isLitLifecycleState,
  PACK_UNIVERSE: PACK_UNIVERSE,
};
