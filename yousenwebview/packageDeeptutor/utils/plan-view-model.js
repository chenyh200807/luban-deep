// 计划页(跑道视图)视图模型 —— AI 学习计划体系 P0 / 首页跑道反转 §2。
// 单一权威红线(跑道计划 §2.2,零新排序):
// - 任务与顺序 = exam_prep_plan_projection(服务端 composition root),本层只读渲染,
//   禁自算优先级、禁自补任务、禁重排;
// - 任务→动作翻译 = 复用 learn-view-model 的 buildCanonicalLearningTask
//   (计划任务信封与 next_step 同协议:mode/source_ref/target_pack_id/reason),
//   禁自写第二套路由映射;URL 派发与 learn.js goTodayTask 逐字段同语义;
// - 分数带 = 后端透传的 pass_readiness 报告值,禁日级重估、禁"照此节奏预计"话术;
//   无报告 → 「先做一次过线体检」引导(不造数);
// - 今日包完成态 = 后端任务级 completed 字段(全 completed 才算),前端不自算;
//   后端未给字段 = 不显示完成态(数据没有就不显示);
// - 未来天复习任务不给点击动作(到期兑付走 exact-match,未到期路由必被拒
//   → 禁 dead click),display-only + 诚实说明。
var learnViewModel = require("./learn-view-model");
var route = require("./route");

function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _safeArr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v).trim();
}

var _FAMILY_META = {
  review_probe: { label: "复验", icon: "review" },
  practice_retest: { label: "复测", icon: "practice" },
  learn_station: { label: "新课", icon: "learn" },
};

var _RISK_LABELS = { high: "高风险", medium: "中风险", low: "低风险" };

// 站点标题索引(显示用途;供给/路由真值仍由翻译器单点裁决,此处不判供给)。
function _titleIndex(lessons) {
  var idx = {};
  _safeArr(_safeObj(lessons).lessons).forEach(function (l) {
    var o = _safeObj(l);
    var id = _str(o.pack_id).toUpperCase();
    if (id) idx[id] = _str(o.title);
  });
  return idx;
}

function _dayLabel(dayOffset, date) {
  if (dayOffset === 0) return "今天";
  if (dayOffset === 1) return "明天";
  var d = _str(date);
  if (d.length >= 10) return d.slice(5, 7) + "月" + d.slice(8, 10) + "日";
  return "第 " + (dayOffset + 1) + " 天";
}

// URL 派发:只消费 buildCanonicalLearningTask 的输出字段,与 learn.js
// goTodayTask 逐字段同语义(action_kind/practice_kind/mode/ids)。无动作 = ""。
function taskRoute(task) {
  var t = _safeObj(task);
  var packId = _str(t.pack_id);
  if (!packId) return "";
  if (t.action_kind === "lesson") return route.lubanStation(packId);
  if (t.action_kind === "retest" && t.practice_kind === "retest") {
    return (
      "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
      encodeURIComponent(packId) +
      "&mode=" +
      (t.mode === "review" ? "review" : "forward") +
      "&training_intent_id=" +
      encodeURIComponent(_str(t.training_intent_id)) +
      "&probe_id=" +
      encodeURIComponent(_str(t.probe_id))
    );
  }
  return "";
}

function _viewTask(task, args) {
  var t = _safeObj(task);
  var family = _str(t.task);
  var meta = _FAMILY_META[family] || { label: "任务", icon: "learn" };
  var packId = _str(t.target_pack_id).toUpperCase();
  var title = args.titles[packId] || _str(t.reason) || packId || "学习任务";
  var deferred = _str(t.status) === "deferred";
  var view = {
    key: family + ":" + _str(t.source_ref) + ":" + packId,
    family: family,
    familyLabel: meta.label,
    familyIcon: meta.icon,
    title: title,
    why: _str(t.why),
    expectedMinutes: Number(t.expected_time) || 0,
    packId: packId,
    sourceRef: _str(t.source_ref),
    mode: _str(t.mode),
    deferred: deferred,
    pinned: t.pinned === true,
    consequence: _str(t.consequence),
    // 完成态来自后端字段(投影/writeback 侧),前端不自算;缺失 = 未完成显示。
    completed: t.completed === true,
    actionUrl: "",
    ctaLabel: "",
    supplyNote: "",
    // defer 手柄:仅复习任务与 learn 任务(计划 §3.3),且只对今天、未推迟的任务。
    canDefer:
      args.isToday && !deferred && (family === "review_probe" || family === "learn_station"),
    deferProbeId: family === "review_probe" ? _str(t.source_ref) : "",
  };
  if (args.isToday && !deferred) {
    // 翻译器是任务→动作的唯一权威;translated=null(如 learn_fallback / 非正式
    // pack)→ display-only,禁自补路由。
    var translated = learnViewModel.buildCanonicalLearningTask({
      homeDashboard: { next_step: t },
      lessons: args.lessons,
      report: args.report,
    });
    if (translated) {
      view.ctaLabel = _str(translated.ctaLabel);
      view.supplyNote = _str(translated.supplyNote);
      view.actionUrl = view.ctaLabel ? taskRoute(translated) : "";
    }
  } else if (!args.isToday && family === "review_probe") {
    // 未来复验:到期才能兑付(exact-match),提前点必被拒 → 不给按钮,给确定性。
    view.supplyNote = "到期当天会出现在今日包";
  }
  return view;
}

/**
 * 组装计划页 data。
 * @param {object} args {planResp, lessons, report}
 * @returns {object} setData payload;planResp.enabled !== true → {enabled:false}
 */
function buildPlanViewModel(args) {
  var a = _safeObj(args);
  var plan = _safeObj(a.planResp);
  if (plan.enabled !== true) return { enabled: false };
  var titles = _titleIndex(a.lessons);
  var sourceStatus = _safeObj(plan.source_status);

  // ── 收敛条:只显示报告值(诚实红线:禁日级跳动、禁预测话术) ──
  var readiness = plan.pass_readiness && typeof plan.pass_readiness === "object" ? plan.pass_readiness : null;
  var countdown =
    typeof plan.exam_countdown_days === "number" && isFinite(plan.exam_countdown_days)
      ? plan.exam_countdown_days
      : null;
  var header = {
    hasReadiness: !!readiness,
    scoreBand: readiness ? _str(readiness.estimated_score_band) : "",
    passLine: readiness && readiness.pass_line != null ? String(readiness.pass_line) : "",
    riskLabel: readiness ? _RISK_LABELS[_str(readiness.risk_band)] || "" : "",
    generatedDate: readiness ? _str(readiness.generated_at).slice(0, 10) : "",
    examCountdownDays: countdown !== null && countdown >= 0 ? countdown : null,
  };

  // ── 7 天列表:只读渲染服务端顺序 ──
  var days = _safeArr(plan.days).map(function (day) {
    var d = _safeObj(day);
    var offset = Number(d.day_offset) || 0;
    var isToday = offset === 0;
    var tasks = _safeArr(d.tasks).map(function (task) {
      return _viewTask(task, {
        isToday: isToday,
        titles: titles,
        lessons: a.lessons,
        report: a.report,
      });
    });
    return {
      date: _str(d.date),
      dayOffset: offset,
      dayLabel: _dayLabel(offset, d.date),
      isToday: isToday,
      plannedMinutes: Number(d.planned_minutes) || 0,
      tasks: tasks,
      isEmpty: tasks.length === 0,
    };
  });

  // ── 今日包完成态:全 completed(后端字段)才算;字段缺失 = 不显示完成态 ──
  var today = days.length ? days[0] : { tasks: [], plannedMinutes: 0 };
  var todayTasks = _safeArr(today.tasks);
  var todayComplete =
    todayTasks.length > 0 &&
    todayTasks.every(function (t) {
      return t.completed === true;
    });

  // ── 日级正面证据文案位:后端有数才显示,没有就整块不渲染(禁造数) ──
  var evidenceCount = sourceStatus.today_positive_evidence_count;
  var todayEvidenceNote =
    typeof evidenceCount === "number" && evidenceCount > 0
      ? "今日新增 " + evidenceCount + " 条正面证据"
      : "";

  return {
    enabled: true,
    header: header,
    days: days,
    todayComplete: todayComplete,
    todayEvidenceNote: todayEvidenceNote,
    planPolicyVersion: _str(plan.plan_policy_version),
    supplyGapCount: _safeArr(plan.supply_gaps).length,
    unscheduledCount: Number(sourceStatus.unscheduled_count) || 0,
    reviewDueUnavailable: sourceStatus.review_due_unavailable === true,
    isEmpty: days.every(function (d) {
      return d.isEmpty;
    }),
  };
}

module.exports = {
  buildPlanViewModel: buildPlanViewModel,
  taskRoute: taskRoute,
};
