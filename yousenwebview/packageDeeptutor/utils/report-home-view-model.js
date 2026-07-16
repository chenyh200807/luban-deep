// report-home-view-model.js — 学情首页最小三件事纯投影
//
// 学习证据只来自 learning-report；下一步只来自已经由
// buildCanonicalLearningTask 翻译的 homeDashboard.next_step。这里不判分、
// 不推断“没有盲点”，也不另排任务优先级。

function _obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function _arr(value) {
  return Array.isArray(value) ? value : [];
}

function _text(value) {
  return value == null ? "" : String(value).trim();
}

function _nonNegativeInt(value) {
  var n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
}

function _hasEligibleLearningEvidence(report) {
  var body = _obj(report);
  var eventStatus = _obj(_obj(body.source_status).learner_events);
  var eventCount = _nonNegativeInt(_obj(body.freshness).event_count);
  return eventStatus.ok === true && eventCount > 0;
}

function _blindSpots(pageData, eligible) {
  if (!eligible) return [];
  return _arr(_obj(pageData).learningDiagnosisCards)
    .map(function (item, index) {
      var row = _obj(item);
      return {
        key: _text(row.key) || "blind-spot-" + index,
        title: _text(row.title),
        meta: _text(row.meta),
        detail: _text(row.detail),
      };
    })
    .filter(function (item) {
      return !!(item.title || item.detail);
    })
    .slice(0, 3);
}

function _nextTask(value) {
  var task = _obj(value);
  var actionKind = _text(task.action_kind);
  var packId = _text(task.pack_id).toUpperCase();
  if ((actionKind !== "lesson" && actionKind !== "retest") || !packId) return null;
  return Object.assign({}, task, { pack_id: packId });
}

function buildReportHomeViewModel(args) {
  var input = _obj(args);
  var report = _obj(input.report);
  var pageData = _obj(input.reportPageData);
  var eligible = _hasEligibleLearningEvidence(report);
  var recentDone = eligible
    ? _nonNegativeInt(_obj(report.overview).recent_three_done)
    : 0;
  var recentAvailable = eligible && recentDone > 0;
  var nextTask = _nextTask(input.nextTask);

  return {
    evidenceState: eligible ? "known" : "insufficient_evidence",
    recentProgress: {
      available: recentAvailable,
      title: recentAvailable ? "近 3 天完成 " + recentDone + " 道有效作答" : "",
      detail: recentAvailable ? _text(pageData.trendNarrative) : "",
    },
    blindSpots: _blindSpots(pageData, eligible),
    nextTask: nextTask,
    nextTaskAvailable: !!(nextTask && _text(nextTask.cta)),
  };
}

module.exports = {
  buildReportHomeViewModel: buildReportHomeViewModel,
};
