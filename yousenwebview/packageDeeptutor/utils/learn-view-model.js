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

// 已验证考点计数(10a 整页改版 · 三指标卡③):只数 mastered。
// pack_lifecycle_projection 中 mastered 只认显式正向信号 verified_concepts
// (terminal 证据),是"已验证"的唯一诚实口径;dormant 虽曾验证但已进入
// 会忘窗口,不计入(宁少勿虚)。纯投影计数,零前端掌握推断。
function _verifiedCount(packs) {
  var n = 0;
  Object.keys(packs).forEach(function (k) {
    if (_str(_safeObj(packs[k]).lifecycle_state) === "mastered") n += 1;
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

// ── 站点旅程轨道(红队 A1 收口):流程说明,不是进度账本 ──
// 前端没有任何逐步完成证据(next_step.mode 是处方,不是完成观测):
// practice_active 只证明存在未 verified 的 training_intent,不证明动画讲懂已完成;
// review_due 只证明有 due probe,周期(次日/3 日/稳定期)由服务端 due 裁决。
// 因此本轨道:禁 done/勾;只标 current(= CTA 对应步,唯一诚实声称)+
// future(空心)+ promise(竹青虚环,不承诺具体日程);不画跨未完成节点的进度线。
// 后端逐步状态 read-model 上线前,禁在前端伪造完成态。
var JOURNEY_STEPS = ["动画讲懂", "训练 5 题", "错因讲评", "轻练确认", "到期验证", "后续抽查"];
var JOURNEY_PROMISE_FROM = 4; // steps[4], steps[5] 为承诺步

function _journeyFor(taskState) {
  // 当前步(1-based)只由 next_step.mode 派生(CTA 对应步):
  // learn_next → 1(动画讲懂);practice_active → 2(训练);review_due → 5(到期验证)。
  var current = taskState === "review_due" ? 5 : taskState === "practice_active" ? 2 : 1;
  var steps = JOURNEY_STEPS.map(function (label, i) {
    var n = i + 1;
    var state = n === current ? "current" : i >= JOURNEY_PROMISE_FROM ? "promise" : "future";
    return { label: label, state: state };
  });
  return {
    steps: steps,
    currentIndex: current,
    total: JOURNEY_STEPS.length,
    // 环形指示 = 当前步位置/6(位置事实,非完成度、非掌握度)。
    // 禁 progressRatio/lineFillPercent:没有完成证据就没有可画的已走线。
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
    // 复习周期(次日/3 日/稳定期)由服务端 due 裁决,前端不得声称"昨天/明日"
    cta: kind === "none"
      ? ""
      : reviewDue
      ? "用 2 分钟完成到期验证"
      : "完成刚学内容的 5 题检验",
    // 主按钮短文案随任务类型;无供给不给按钮(禁 dead click)
    // owner 2026-07-18:练题优先重排——练习类主按钮统一「集中练习」;
    // review_due「开始验证」不动(到期验证语义独立,不并入练习动作)。
    ctaLabel: kind === "none" ? "" : reviewDue ? "开始验证" : "集中练习",
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

// 供给真值 → practice_kind 单一裁决点(禁在页面层再判一次)。
// 注意作用域(二轮红队 A5):本旗标来自 lessons manifest 的
// light_practice_available,受 LUBAN_LIGHT_PRACTICE_ENABLED 限制,是
// forward-only 供给真值;review(到期验证)的资格另走 _reviewDueEntry。
function _practiceKindFor(packId, titleIdx) {
  var id = _str(packId).toUpperCase();
  if (_safeObj(titleIdx[id]).retest === true) return "retest";
  return "none";
}

// ── review(mode=review)供给/身份唯一裁决点(二轮红队 A3+A5) ──
// 镜像服务端 exact resolver 的口径(review_due.py:要求 pack/probe 非空、
// retest_available is True,否则拒绝):
// - pack_review authority 必须已知且未降级(fail-closed);
// - 任务身份 pack_id/probe_id 必须非空(空串互等 = 旁路,服务端本来就拒空);
// - due 条目必须 exact-match 且 retest_available === true(缺失/null=未知,保守拒)。
// pack_review 缺失/降级时宁可少显示(诚实降级),不借用 forward-only 旗标造资格。
function _reviewDueEntry(report, packId, probeId) {
  var packReview = _safeObj(_safeObj(report).pack_review);
  var authorityKnown =
    packReview.enabled === true &&
    packReview.degraded !== true &&
    _str(packReview.authority) === "revalidation_queue";
  if (!authorityKnown) return null;
  var pid = _str(packId).toUpperCase();
  var prid = _str(probeId);
  if (!pid || !prid) return null;
  var rows = _safeArr(packReview.due);
  for (var i = 0; i < rows.length; i++) {
    var o = _safeObj(rows[i]);
    if (
      _str(o.pack_id).toUpperCase() === pid &&
      _str(o.probe_id) === prid &&
      o.retest_available === true
    ) {
      return o;
    }
  }
  return null;
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
// 展示动作的翻译；lessons 仅回答该任务的内容/forward 题目供给是否已签发，
// report.pack_review 仅回答 review(到期验证)供给是否已签发；不能在
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

  // 任务级公共派生:轻练旁按钮供给真值。
  // 轻练供给唯一裁决点仍是 _practiceKindFor(禁页面层再判一次)。
  // owner 2026-07-18 排版去重:旅程轨道不再挂在任务卡上——它叙述的是站点学习
  // 旅程,归视频学习卡(buildLearnViewModel 挂到 nextStation.journey);current
  // 步语义不变(CTA 对应步,由 taskCard.task_state 派生)。
  // 红队 A2 收口:轻练只复用当前任务的 fact 语境,不是第二处方——
  // review_due(到期验证优先)下按钮隐藏且不可用,禁 probe-less forward 旁路
  // (否则可绕开到期验证并重开 fresh cycle 清掉 canonical review streak)。
  function _decorate(task) {
    if (!task) return task;
    var reviewDue = task.task_state === "review_due";
    task.kicker = "今天最该完成"; // 真任务卡 kicker(browse 卡另有"从这里开始"口吻)
    task.light_practice_visible = !reviewDue;
    task.light_practice_available =
      !reviewDue && _practiceKindFor(packId, titleIdx) === "retest";
    return task;
  }

  if (mode === "review_due") {
    // 二轮红队 A5:review 资格消费 canonical due 条目(retest_available===true),
    // 不复用 forward-only 的 lessons 旗标——light flag 关闭时到期验证仍须可路由,
    // 反之 pack_review 降级/身份不匹配时也不得借 forward 旗标造资格。
    var reviewSupply = _reviewDueEntry(a.report, packId, sourceRef);
    var reviewTask = _retestTask(
      pack.title || "你的薄弱点",
      packId,
      _str(nextStep.reason),
      reviewSupply ? "retest" : "none",
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
  // owner 2026-07-18 拍板:学习主任务优先练教学视频后面的练习题
  // (retest forward,633 池),主按钮统一「集中练习」;仅当该站练习池
  // 未签发时才回落「进站看讲解」。供给真值仍由 _practiceKindFor 单点裁决,无第二处方。
  if (_practiceKindFor(packId, titleIdx) === "retest") {
    var learnPractice = _retestTask(
      pack.title || "最需要提分的考点",
      packId,
      _str(nextStep.reason),
      "retest",
      "learn_next",
    );
    learnPractice.cta = "练教学视频后面的 5 题，错了当场弄懂";
    learnPractice.ctaLabel = "集中练习";
    return _decorate(learnPractice);
  }
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
  var task = _safeObj(todayTask);
  // next_step 没裁决为到期验证 → 不渲染(禁自算优先级);
  // 验证任务无可路由 retest 供给 → 不渲染(禁 dead click)。
  if (task.task_state !== "review_due" || task.practice_kind !== "retest") return null;
  // 红队 A3 收口:dashboard 与 learning-report 是两个独立快照,可能跨快照漂移
  // (卡显示 S05 计数,点击却路由 N01 旧 probe → 被后端 exact-match 拒绝)。
  // 复用 _reviewDueEntry 单一裁决点:authority 已知 + 身份非空 exact-match +
  // retest_available === true;不匹配一律隐藏,禁自行改选另一条 due(那是第二处方)。
  var entry = _reviewDueEntry(report, task.pack_id, task.probe_id);
  if (!entry) return null;
  var dueCount = _safeArr(_safeObj(_safeObj(report).pack_review).due).length;
  return {
    dueCount: dueCount,
    // 周期由服务端 due 裁决,不声称"昨天"(可能是 3 日/稳定期抽查)
    title: "复习 · " + dueCount + " 个考点到期",
    sub: "换题验证 · 约 2 分钟 · 通过即亮「已验证」",
    cta: "去验证",
  };
}

// ── browse 兜底投影(owner 2026-07-17):todayTask 为 null(server next_step
//    缺失 / unavailable / day-0 冷启动)但已有可展示的 nextStation 时,产出与
//    今日任务卡视觉同构的 browse 卡——让学习页在任何状态都长成 10a 定稿的样子,
//    不退化成 hero+海报。红线(禁第二处方):
//    - browse 只在 todayTask 为 null 时出现,永不与 server next_step 竞争今日任务;
//    - browse 不声称"今日任务",kicker/文案用"从这里开始 / 推荐起点"口吻;
//    - review_due 由 next_step 唯一裁决,browse 不碰复习逻辑;
//    - 轻练与主按钮供给真值复用 _practiceKindFor 单点(禁页面层再判)。
function _buildBrowseTask(nextStation, titleIdx) {
  var s = _safeObj(nextStation);
  var packId = _str(s.pack_id).toUpperCase();
  if (!packId) return null;
  // 供给真值单点:练习池已签发 → 集中练习(retest forward);否则进站看讲解。
  var isRetest = _practiceKindFor(packId, titleIdx) === "retest";
  return {
    kicker: "从这里开始", // 推荐起点口吻,禁"今日任务"
    title: _str(s.title) || "最需要提分的考点",
    reason: _str(s.reason), // 群体理由(evidenceBacked=false),不伪装个性化证据
    cta: isRetest
      ? "从这一站的 5 题开始，错了当场弄懂"
      : "先看这一站的讲解，点亮你的提分路线",
    ctaLabel: isRetest ? "集中练习" : "进站学习",
    supplyNote: "",
    task_type: isRetest ? "light_practice" : "microlesson",
    task_state: "browse", // 非 review_due/practice_active:轻练走 probe-less forward
    action_kind: isRetest ? "retest" : "lesson",
    practice_kind: isRetest ? "retest" : "",
    estimated_minutes: isRetest ? 2 : 5,
    concept: _str(s.title),
    pack_id: packId,
    training_intent_id: "",
    probe_id: "",
    mode: isRetest ? "forward" : "learn",
    // 旅程条已随排版去重移到视频学习卡(nextStation.journey),browse 卡不再携带。
    // 轻练旁按钮:browse 永不 review_due → 可见;可用性=供给真值(retest)单点。
    light_practice_visible: true,
    light_practice_available: isRetest,
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
    report: a.report, // review 供给真值在 pack_review(A5),缺失时诚实降级
  });

  // ── browse 兜底卡:todayTask 缺席但有可展示 nextStation 时的同构卡 ──
  // 让 day-0 / 首跑未完成 / 后端未部署等态下,页面仍长成 10a 定稿(训练/轻练/
  // 旅程条不塌)。永不与 todayTask 竞争:仅在 todayTask===null 时产出。
  var browseTask = !todayTask && nextStation ? _buildBrowseTask(nextStation, titleIdx) : null;
  // 任务卡渲染入口 = 真任务优先,否则 browse 兜底(单一渲染源,禁 wxml 重算)。
  var taskCard = todayTask || browseTask;

  // ── 站点旅程条(owner 2026-07-18 排版去重):journey 叙述的是站点学习旅程,
  //    挂到视频学习卡(nextStation),不再挂任务卡。current 步语义与 10a 一致:
  //    仍由 taskCard.task_state 派生(CTA 对应步,处方非完成证据;红队 A1 约束
  //    不变——禁 done 勾/进度线/写死复习日程)。无 taskCard 时诚实落 step1。
  if (nextStation) {
    nextStation.journey = _journeyFor(taskCard ? _str(taskCard.task_state) : "learn_next");
  }

  // ── 复习卡:到期状态视图(数据=pack_review 投影;裁决权仍在 next_step) ──
  var reviewCard = _buildReviewCard(report, todayTask);

  // ── 行为指标只透传事实计数；首页不呈现或解释 mastery 百分比 ──
  var overview = _safeObj(report.overview);
  var learnerSettings = _safeObj(dash.learner_settings);
  var stats = {
    recent_practice: _int(overview.recent_three_done),
    pending_errors: _int(overview.weak_point_count != null ? overview.weak_point_count : overview.pending_error_count),
    // 已验证考点(mastered=显式 verified_concepts terminal 证据),事实计数非掌握度
    verified_stations: _verifiedCount(packs),
  };
  var dailyTarget = _int(overview.daily_target || learnerSettings.daily_target);
  var todayDone = _int(overview.today_done);

  return {
    litCount: lit,
    packUniverse: universe,
    nextStation: nextStation,          // null → 显示"内容即将上线"空态卡
    posters: posters,                  // [] → 课程架空态(完整地图/stations 用真实态)
    routePreview: routePreview,        // 首页 3 卡真实状态预览
    todayTask: todayTask,              // null → 无 server 裁决的今日任务(可能走 browse)
    browseTask: browseTask,            // todayTask 缺席时的同构 browse 兜底卡
    taskCard: taskCard,                // 任务卡唯一渲染源 = todayTask || browseTask
    reviewCard: reviewCard,            // null → 复习空态(诚实排期占位,不整块消失)
    stats: stats,
    examDate: _str(learnerSettings.exam_date),
    todayProgress: {
      done: todayDone,
      target: dailyTarget,
      percent: dailyTarget ? Math.min(100, Math.round((todayDone / dailyTarget) * 100)) : 0,
    },
    // 供给面可用性(全空 = 后端未部署/无数据,页面走降级但不崩)
    hasSupply: !!(nextStation || posters.length || todayTask || browseTask),
  };
}

module.exports = {
  buildLearnViewModel: buildLearnViewModel,
  buildCanonicalLearningTask: buildCanonicalLearningTask,
  isLitLifecycleState: isLitLifecycleState,
  PACK_UNIVERSE: PACK_UNIVERSE,
};
