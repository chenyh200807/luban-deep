// 学情统一快照的唯一组装权威:raw 服务端三元组(learning report / home dashboard /
// luban lessons)→ report-cache envelope 内的 snapshot 形状(schema 不变,沿用 v2)。
// report 页与 learn 页是仅有的两个合法写者,都必须经本 builder 组装后交给
// report-cache.write,防止两页各长一套快照形状(第二 authority)。
// canonical truth 仍在服务端;这里只是投影组装,不发明数据。
var taxonomy = require("./taxonomy");

function isLearningReportPayload(value) {
  var authority = value && value.authority;
  var schemaVersion = Number(value && value.schema_version);
  return Boolean(
    value &&
      typeof value === "object" &&
      (schemaVersion === 1 || schemaVersion === 2) &&
      authority &&
      authority.read_model === "learning-report-read-model" &&
      value.overview &&
      typeof value.overview === "object" &&
      value.freshness &&
      typeof value.freshness === "object" &&
      value.learning_brain &&
      typeof value.learning_brain === "object",
  );
}

function learningReportDegradedSources(report) {
  var sources = Array.isArray(report && report.degraded_sources)
    ? report.degraded_sources.slice()
    : [];
  if (report && report.freshness && report.freshness.window_truncated) {
    sources.push("learning_report_window");
  }
  return sources.filter(function (item, index) {
    return item && sources.indexOf(item) === index;
  });
}

function chapterMasteryFromRadar(dimensions) {
  var mastery = {};
  (Array.isArray(dimensions) ? dimensions : []).forEach(function (item) {
    var name = taxonomy.displayChapterName(
      item && (item.name || item.label || item.key),
      "未归类能力",
    );
    var value = Number(item && item.value);
    mastery[name] = {
      name: name,
      mastery: Math.round((Number.isFinite(value) ? value : 0) * 100),
    };
  });
  return mastery;
}

function _objectWithKeys(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return Object.keys(value).length > 0 ? value : null;
}

function buildUnifiedReportSnapshot(input) {
  var report = input && input.report;
  if (!isLearningReportPayload(report)) return null;
  // 空对象归一化为 null:learn 的 settle() 会把失败源映成 {},若原样入快照,
  // 消费页会把"缺失"误当"有数据"渲染出半残模块。null=统一的"缺失"语义。
  var homeDashboard = _objectWithKeys(input && input.homeDashboard);
  var lessons = _objectWithKeys(input && input.lessons);
  var overview = report.overview || {};
  var mastery = report.mastery || {};
  var weakNodes = ((report.learning_brain || {}).weak_points || []).map(
    function (item) {
      return {
        name: item.display_title || item.claim || item.concept_id || "薄弱点",
        mastery: 0,
      };
    },
  );
  var degradedSources = learningReportDegradedSources(report);
  return {
    report: report,
    homeDashboard: homeDashboard,
    degraded: Boolean(report.degraded) || degradedSources.length > 0,
    degradedSources: degradedSources,
    sourceStatus: report.source_status || {},
    progress: {
      today_done: overview.today_done || 0,
      daily_target: overview.daily_target || 0,
      streak_days: overview.streak_days || 0,
    },
    home: {
      review: { due_today: overview.due_today_count || 0 },
      mastery: {
        weak_nodes: weakNodes.slice(
          0,
          overview.weak_node_count || weakNodes.length || 0,
        ),
      },
      today: { hint: overview.focus_hint || "" },
      today_focus: { title: overview.focus_hint || "" },
      study_plan: report.study_plan || null,
      progress_feedback: report.progress_feedback || null,
    },
    assessment: {
      level: overview.learner_level || "",
      chapter_mastery: chapterMasteryFromRadar(report.radar_dimensions || []),
      diagnostic_feedback: {
        learner_profile: { study_tip: overview.study_tip || "" },
      },
    },
    mastery: mastery,
    learningBrain: report.learning_brain || {},
    learnerFacing: report.learner_facing || {},
    lessons: lessons,
  };
}

module.exports = {
  isLearningReportPayload: isLearningReportPayload,
  learningReportDegradedSources: learningReportDegradedSources,
  chapterMasteryFromRadar: chapterMasteryFromRadar,
  buildUnifiedReportSnapshot: buildUnifiedReportSnapshot,
};
