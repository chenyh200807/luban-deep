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

// 灰点分语义:未就绪步骤的服务端 reason → 一句暖提示,让"等我做/等系统/还没到期"
// 可区分。纯 reason→文案映射(零业务推导);未识别 reason 一律 fail-quiet 不猜。
// reason 词汇表权威 = station_journey_projection.py(只读)。文案红线:禁看穿/识破/
// 揭穿/露馅等审视语气,基调=帮你变强、暖。current/completed 步不需要提示(已有主态)。
function _journeyStepHint(status, reason) {
  var r = _str(reason);
  // 等系统:错因讲评内容尚未生成
  if (r === "feedback_unavailable") return "讲评生成中 · 稍后回来看";
  // 并入到期验证:确认供给未开但到期验证已在轨——错后加分项由第 5 步验证卷兜底,
  // 不是"没开发完"。暖基调,给学员确定性("会考到"),禁审视语气。
  if (r === "confirm_covered_by_due_validation") return "本轮已并入到期验证 · 验证卷会考到";
  // 等系统:本站确认练习供给未开 / 供给投影降级
  if (r === "safe_confirm_unavailable" || r === "confirm_supply_projection_unavailable") {
    return "本站确认练习准备中";
  }
  // 复习模块暂不可用(到期验证/后续抽查降级):记录不丢,别让灰点像"永远不来"
  if (r === "review_projection_unavailable") return "复习安排稍后恢复 · 记录已保留";
  // 还没到期:服务端 scheduled 排期步无 reason。双信息=到期自动出现 + 现在不被挡,
  // 可以直接继续学下一站(每站独立并行调度,后两格灰点不阻塞学下一站)。
  if (_str(status) === "scheduled") return "到期自动出现 · 现在可以继续学下一站";
  return "";
}

// 六条 hint 不堆叠:只投一条对学员最有行动意义的。优先当前步自身提示(如排期中),
// 否则按步序取首个非空提示(讲评/确认/复习等待)。
function _pickJourneyHint(steps, currentIndex) {
  var current = currentIndex > 0 ? _safeObj(steps[currentIndex - 1]) : {};
  if (_str(current.hint)) return _str(current.hint);
  for (var i = 0; i < steps.length; i += 1) {
    var h = _str(_safeObj(steps[i]).hint);
    if (h) return h;
  }
  return "";
}

function unknownJourney() {
  return {
    available: false,
    statusText: "进度暂不可用 · 下拉重试",
    currentStepId: "",
    journeyState: "unavailable",
    currentIndex: 0,
    total: JOURNEY_STEPS.length,
    hint: "",
    steps: JOURNEY_STEPS.map(function (step) {
      return { id: step.id, label: step.label, status: "unknown", state: "future", hint: "" };
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
  // active 一致性对齐服务端合同:current_step_id = 步序第一个 current|scheduled。
  // 服务端合法形状允许多个 actionable 并存(如 轻练确认 current + 到期验证
  // scheduled/current 同在,后者到期自动接棒);仅周期未开时(当前步是
  // 动画讲懂/训练 5 题)actionable 必须唯一——后段步骤伪造 current 仍 fail-closed。
  var firstActionableId = actionableSteps.length
    ? _str(_safeObj(actionableSteps[0]).id)
    : "";
  if (
    (journeyState === "active" &&
      (currentIndex <= 0 ||
        firstActionableId !== currentStepId ||
        (currentIndex <= 2 && actionableSteps.length !== 1) ||
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
  var mappedSteps = rawSteps.map(function (raw, index) {
    var status = _str(raw.status);
    var mapped = {
      id: JOURNEY_STEPS[index].id,
      label: JOURNEY_STEPS[index].label,
      status: status,
      state: JOURNEY_STATUSES[status],
      note: status === "not_applicable" ? "无需" : status === "unavailable" ? "暂不可用" : "",
      // 灰点分语义:completed 步不给提示(已是明确态),其余步按服务端 reason 映射
      hint: status === "completed" ? "" : _journeyStepHint(status, raw.reason),
      blocking: raw.blocking === true,
    };
    // 「并入到期验证」reason(status 仍 unavailable)覆写呈现:用现有 not-needed
    // 轻量态而非 unavailable 灰态,note 从「暂不可用」改「并入验证」。纯 reason→呈现
    // 映射,不新造状态机(status/blocking 不动,一致性校验仍以 raw.status 为准)。
    if (_str(raw.reason) === "confirm_covered_by_due_validation") {
      mapped.state = JOURNEY_STATUSES.not_applicable;
      mapped.note = "并入验证";
    }
    // 轻练确认重入口只读透传:仅 current+safe_confirm_available 且服务端两字段
    // 齐全时携带(facts 非空字符串数组 + anchor 非空)。任何缺失/其他状态一律不
    // 带字段 → 消费端(学情全景 CTA)fail-closed 不亮不猜。零客户端推导。
    if (
      mapped.id === "immediate_confirm" &&
      status === "current" &&
      _str(raw.reason) === "safe_confirm_available"
    ) {
      var confirmFacts = _safeArr(raw.confirm_facts)
        .map(function (fact) { return _str(fact).trim(); })
        .filter(function (fact) { return !!fact; });
      var confirmAnchor = _str(raw.confirm_anchor).trim();
      if (confirmFacts.length && confirmAnchor) {
        mapped.confirmFacts = confirmFacts;
        mapped.confirmAnchor = confirmAnchor;
      }
    }
    return mapped;
  });
  return {
    available: true,
    statusText: statusText,
    currentStepId: currentStepId,
    currentIndex: journeyState === "completed" ? JOURNEY_STEPS.length : currentIndex,
    journeyState: journeyState,
    total: JOURNEY_STEPS.length,
    hint: _pickJourneyHint(mappedSteps, currentIndex),
    steps: mappedSteps,
  };
}

module.exports = {
  JOURNEY_STEPS: JOURNEY_STEPS,
  JOURNEY_STATUSES: JOURNEY_STATUSES,
  unknownJourney: unknownJourney,
  stationJourneyFor: stationJourneyFor,
};
