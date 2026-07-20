// station-journey.js — 站点六步旅程 read model 唯一消费/校验器
//
// 单一权威边界：learn 页(下一站旅程条)与学情页(掌握地图每站全景)共用此
// 校验。station_journey_projection 的 authority/schema_version/degraded/6步
// id 顺序/状态合法性/completed·unavailable·active 一致性检查只此一份，禁第二套。
// 校验不过一律 fail-closed 为 unknown 空态——绝不猜阶段、不显伪 0/6。
//
// 六步 id 顺序固定（对应服务端 station_journey_projection.read_model
// schema_version=1）：lesson/practice/diagnosis/immediate_confirm/
// due_validation/followup。中文：动画讲懂/训练5题/错因讲评/轻练确认/到期验证/后续抽查。

function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _safeArr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v);
}

var JOURNEY_STEPS = [
  { id: "lesson", label: "动画讲懂" },
  { id: "practice", label: "训练 5 题" },
  { id: "diagnosis", label: "错因讲评" },
  { id: "immediate_confirm", label: "轻练确认" },
  { id: "due_validation", label: "到期验证" },
  { id: "followup", label: "后续抽查" },
];
var JOURNEY_STATUSES = {
  completed: "done",
  current: "current",
  scheduled: "promise",
  not_applicable: "not-needed",
  unavailable: "unavailable",
  available: "future",
  upcoming: "future",
  future: "future",
};

function unknownJourney() {
  return {
    available: false,
    statusText: "进度暂不可用 · 下拉重试",
    currentStepId: "",
    journeyState: "unavailable",
    currentIndex: 0,
    total: JOURNEY_STEPS.length,
    steps: JOURNEY_STEPS.map(function (step) {
      return { id: step.id, label: step.label, status: "unknown", state: "future" };
    }),
  };
}

// 六步只读服务端 station_journey_projection。next_step 是 CTA 处方，永不参与
// 完成态推断；缺字段/authority/schema/pack 不匹配均 fail-closed 为 unknown。
function stationJourneyFor(report, packId) {
  var projection = _safeObj(_safeObj(report).station_journey);
  var normalizedPack = _str(packId).toUpperCase();
  if (
    projection.authority !== "station_journey_projection.read_model" ||
    projection.schema_version !== 1 ||
    projection.degraded === true ||
    !normalizedPack
  ) return unknownJourney();
  var pack = _safeObj(_safeObj(projection.packs)[normalizedPack]);
  var rawSteps = _safeArr(pack.steps);
  var journeyState = _str(pack.journey_state);
  if (
    _str(pack.pack_id).toUpperCase() !== normalizedPack ||
    ["active", "completed", "unavailable"].indexOf(journeyState) < 0 ||
    rawSteps.length !== JOURNEY_STEPS.length
  ) {
    return unknownJourney();
  }
  var valid = rawSteps.every(function (raw, index) {
    return _str(_safeObj(raw).id) === JOURNEY_STEPS[index].id && !!JOURNEY_STATUSES[_str(_safeObj(raw).status)];
  });
  if (!valid) return unknownJourney();
  var currentStepId = _str(pack.current_step_id);
  var currentIndex = JOURNEY_STEPS.findIndex(function (step) { return step.id === currentStepId; }) + 1;
  var currentRaw = currentIndex > 0 ? _safeObj(rawSteps[currentIndex - 1]) : {};
  var actionableSteps = rawSteps.filter(function (raw) {
    return ["current", "scheduled"].indexOf(_str(_safeObj(raw).status)) >= 0;
  });
  var followupStatus = _str(_safeObj(rawSteps[rawSteps.length - 1]).status);
  var completedHasOpenStep = rawSteps.some(function (raw) {
    return ["current", "scheduled", "available", "upcoming", "future"].indexOf(
      _str(_safeObj(raw).status),
    ) >= 0;
  });
  var unavailableCount = rawSteps.filter(function (raw) {
    return _str(_safeObj(raw).status) === "unavailable";
  }).length;
  if (
    (journeyState === "active" &&
      (currentIndex <= 0 ||
        actionableSteps.length !== 1 ||
        ["current", "scheduled"].indexOf(_str(currentRaw.status)) < 0)) ||
    (journeyState !== "active" && currentStepId) ||
    (journeyState === "completed" &&
      (completedHasOpenStep || followupStatus !== "completed")) ||
    (journeyState === "unavailable" &&
      (actionableSteps.length > 0 || unavailableCount === 0))
  ) return unknownJourney();
  var statusText = journeyState === "completed"
    ? "本轮六步已完成"
    : journeyState === "unavailable"
    ? "后续排期暂不可用"
    : _str(currentRaw.status) === "scheduled"
    ? "下一步：" + JOURNEY_STEPS[currentIndex - 1].label + " · 待排期"
    : "当前：" + JOURNEY_STEPS[currentIndex - 1].label;
  return {
    available: true,
    statusText: statusText,
    currentStepId: currentStepId,
    currentIndex: journeyState === "completed" ? JOURNEY_STEPS.length : currentIndex,
    journeyState: journeyState,
    total: JOURNEY_STEPS.length,
    steps: rawSteps.map(function (raw, index) {
      var status = _str(raw.status);
      return {
        id: JOURNEY_STEPS[index].id,
        label: JOURNEY_STEPS[index].label,
        status: status,
        state: JOURNEY_STATUSES[status],
        note: status === "not_applicable" ? "无需" : status === "unavailable" ? "暂不可用" : "",
        blocking: raw.blocking === true,
      };
    }),
  };
}

module.exports = {
  JOURNEY_STEPS: JOURNEY_STEPS,
  JOURNEY_STATUSES: JOURNEY_STATUSES,
  unknownJourney: unknownJourney,
  stationJourneyFor: stationJourneyFor,
};
