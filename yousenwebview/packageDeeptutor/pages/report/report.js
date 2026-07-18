// pages/report/report.js — 学情页：诊断 + AI作战方案 + 进步反馈

const api = require("../../utils/api");
const surfaceTelemetry = require("../../utils/surface-telemetry");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");
const flags = require("../../utils/flags");
const auth = require("../../utils/auth");
const reportViewModel = require("../../utils/learning-report-view-model");
const { buildCanonicalLearningTask } = require("../../utils/learn-view-model");
const { buildReportHomeViewModel } = require("../../utils/report-home-view-model");
const reportCache = require("../../utils/report-cache");
// 快照组装唯一权威(生产运行时):utils/report-snapshot。缓存年龄阈值唯一权威:
// reportCache.SNAPSHOT_MAX_AGE_MS / FRESH_MAX_AGE_MS(本地常量副本已删)。
const reportSnapshot = require("../../utils/report-snapshot");
const taxonomy = require("../../utils/taxonomy");

const REPORT_UNIFIED_READ_TIMEOUT_MS = 8000;
const REPORT_MODULE_HINT_STORAGE_KEY = "deeptutor.report.moduleHint.v1";
const ASSESSMENT_PENDING_TRAINING_ACTION_KEY =
  "deeptutor.report.pendingTrainingAction";
const RADAR_SELF_SUBJECT = "self";
const LEVEL_NAMES = {
  beginner: "入门",
  intermediate: "中级",
  advanced: "进阶",
  expert: "精通",
};
const LEARNING_BRAIN_LEVEL_LABELS = {
  L0_observed: "单次观察",
  L1_repeated: "重复出现",
  L2_confirmed: "已确认",
  L3_mastery_signal: "改善信号",
  unclassified: "待确认",
};
const LEARNING_BRAIN_SUBJECT_LABELS = {
  construction_exam_learning_truth: "建筑实务学习事实",
};
const REPORT_DETAIL_TITLES = {
  home: "学情",
  evidence: "学情依据",
  map: "掌握地图",
  training: "训练安排",
  progress: "进步反馈",
};

function _displayLevelName(value) {
  var key = String(value || "").trim();
  return LEVEL_NAMES[key] || key || "";
}

function _displayChapterName(value) {
  return taxonomy.displayChapterName(value, "未归类能力");
}

function _buildRadarSignature(dims) {
  return (dims || [])
    .map(function (d) {
      var name = String(d && d.name ? d.name : "").trim();
      var value = Math.round((Number(d && d.value) || 0) * 1000);
      return name + ":" + value;
    })
    .join("|");
}

function _buildRadarDimensionsFromAssessment(data) {
  var profile = data || {};
  var chapterMastery = profile.chapter_mastery || {};
  return Object.keys(chapterMastery).map(function (key) {
    var item = chapterMastery[key];
    var mastery = Number(typeof item === "object" ? item.mastery : item);
    var normalizedMastery = Number.isFinite(mastery) ? mastery : 0;
    return {
      name: _displayChapterName(
        (typeof item === "object" ? item.name : key) || key,
      ),
      value: normalizedMastery / 100,
      status:
        normalizedMastery >= 70
          ? "strong"
          : normalizedMastery > 0
            ? "normal"
            : "weak",
    };
  });
}

function _hasPositiveRadarSignal(dims) {
  return (dims || []).some(function (item) {
    return Number(item && item.value) > 0;
  });
}

function _normalizeRadarDimensions(radarData) {
  return ((radarData && radarData.dimensions) || []).map(function (item) {
    var score = Number(item.score);
    var value =
      typeof item.value === "number"
        ? item.value
        : Number.isFinite(score)
          ? score / 100
          : 0;
    return {
      name: _displayChapterName(item.label || item.name || item.key || ""),
      value: value || 0,
    };
  });
}

function _compactLearningBrainId(value) {
  var text = String(value || "").trim();
  if (!text) return "";
  return text.length > 18 ? text.slice(0, 8) + "..." + text.slice(-4) : text;
}

function _asLearningBrainList(value) {
  return Array.isArray(value) ? value : [];
}

function _asLearningBrainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function _asLearningBrainNumber(value, fallback) {
  var num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function _hasExplicitNumericValue(value) {
  return (
    value !== undefined &&
    value !== null &&
    value !== "" &&
    Number.isFinite(Number(value))
  );
}

function _learningBrainEventIds(ids) {
  return _asLearningBrainList(ids)
    .map(function (_id, index) {
      return _learningBrainEvidenceLabel(index);
    })
    .filter(Boolean)
    .slice(0, 3);
}

function _learningBrainEventLabels(labels, ids) {
  var readable = _asLearningBrainList(labels).filter(Boolean).slice(0, 3);
  return readable.length ? readable : _learningBrainEventIds(ids);
}

function _learningBrainEvidenceLabel(index) {
  if (index === 0) return "最近一次批改";
  if (index === 1) return "上一次批改";
  return "第 " + (index + 1) + " 条批改证据";
}

function _learningBrainNodeId(edge, side) {
  var node = _asLearningBrainObject(edge && edge[side]);
  return String(node.id || node.type || "").trim();
}

function _learningBrainLevelLabel(level) {
  var key = String(level || "").trim();
  return (
    LEARNING_BRAIN_LEVEL_LABELS[key] ||
    key ||
    LEARNING_BRAIN_LEVEL_LABELS.unclassified
  );
}

function _learningBrainSubjectLabel(subject) {
  var key = String(subject || "").trim();
  return LEARNING_BRAIN_SUBJECT_LABELS[key] || key || "";
}

function _learningBrainEdgeLabel(edgeType) {
  var key = String(edgeType || "").trim();
  return key ? "学习关系" : "";
}

// Display-only mirror of docs/contracts/error_code_registry.md for stale Learning Brain rows.
// Backend registry remains the scoring/write authority; this client fallback only prevents raw
// M-codes from leaking into learner-facing copy when historical rows arrive without labels.
function _learningBrainErrorLabel(errorCode) {
  var code = String(errorCode || "").trim().toUpperCase();
  if (code === "M01") return "知识点不熟";
  if (code === "M02") return "关键词误读";
  if (code === "M03") return "概念混淆";
  if (code === "M04") return "选项陷阱";
  if (code === "M05") return "审题方向错误";
  if (code === "M06") return "多选漏选";
  if (code === "M07") return "多选错选";
  if (code === "M08") return "规范数字混淆";
  if (code === "M09") return "题干条件提取不完整";
  if (code === "M10") return "用常识替代规范判断";
  return code ? "错因" : "";
}

function _learningBrainConceptLabel(code, withCode) {
  var original = String(code || "").trim();
  if (!original) return "";
  var topic = original.match(/我想练习(.+?)相关的题目/);
  if (topic && topic[1]) return topic[1].trim();
  return "知识点";
}

function _learningBrainQuestionLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  if (/wechat-harness-case-\d+/i.test(text)) {
    return "案例题：" + text.replace(/^wechat-harness-case-/i, "专项训练 ");
  }
  if (/^case[-_:]?\d+/i.test(text)) {
    return "案例题：" + text.replace(/^case[-_:]?/i, "第 ") + " 题";
  }
  return "案例题：" + _compactLearningBrainId(text);
}

function _learningBrainRubricLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  var part = text.split(":").pop();
  return (
    "采分点：" +
    (part && /^r\d+$/i.test(part)
      ? part.toUpperCase()
      : _compactLearningBrainId(part || text))
  );
}

function _learningBrainTrainingLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  var parts = text.split(":");
  var focus = parts.length > 2 ? parts.slice(2).join(" / ") : "";
  if (focus) return "训练建议：" + focus;
  if (parts[0] && /^1A\d{6}$/i.test(parts[0])) {
    return "训练建议：" + _learningBrainConceptLabel(parts[0], false);
  }
  return "训练建议：" + _compactLearningBrainId(text);
}

function _learningBrainObjectLabel(rawId, rawType) {
  var id = String(rawId || "").trim();
  var type = String(rawType || "").trim();
  if (!id && !type) return "";
  if (id.indexOf(":") > 0) {
    var prefix = id.split(":")[0];
    if (
      /^(concept|error|question|rubric_item|submission|next_training|training|weak_point)$/.test(
        prefix,
      )
    ) {
      type = prefix;
      id = id.slice(prefix.length + 1);
    }
  }
  if (type === "concept" || /^1A\d{6}$/i.test(id)) {
    return "知识点：" + _learningBrainConceptLabel(id, true);
  }
  if (
    type === "error" ||
    /^1A\d{6}:[EM]\d{2}$/i.test(id) ||
    /^[EM]\d{2}$/i.test(id)
  ) {
    var parts = id.split(":");
    var concept = /^1A\d{6}$/i.test(parts[0])
      ? _learningBrainConceptLabel(parts[0], false)
      : "";
    var error = _learningBrainErrorLabel(parts[parts.length - 1]);
    return "错因：" + [concept, error].filter(Boolean).join(" / ");
  }
  if (type === "question") return _learningBrainQuestionLabel(id);
  if (type === "rubric_item") return _learningBrainRubricLabel(id);
  if (type === "next_training" || type === "training")
    return _learningBrainTrainingLabel(id);
  if (type === "submission") return "作答记录：" + _compactLearningBrainId(id);
  if (type === "weak_point") return "薄弱点";
  return "学习对象：" + _compactLearningBrainId(id || type);
}

function _humanizeLearningBrainText(value) {
  var text = String(value || "").trim();
  if (!text) return "";
  text = text.replace(
    /我想练习(.+?)相关的题目\s*请严格围绕.*?当前学习锚点出题/g,
    "$1",
  );
  text = text.replace(/concept:/g, "知识点：");
  text = text.replace(/rubric_item:/g, "采分点：");
  text = text.replace(/question:/g, "案例题：");
  text = text.replace(/error:/g, "错因：");
  text = text.replace(/\bpractice\s*\/\s*/gi, "训练建议：");
  text = text.replace(/\s*->\s*/g, " → ");
  text = text.replace(/\bq[-_:]?(\d+)\b/gi, "第 $1 题");
  text = text.replace(/1A\d{6}/gi, function (code) {
    return _learningBrainConceptLabel(code, false);
  });
  text = text.replace(/\b[EM]\d{2}\b/gi, function (code) {
    return _learningBrainErrorLabel(code);
  });
  text = text.replace(/\s*上出现\s*/g, "出现");
  text = text.replace(/\s*相关错因观察/g, "相关错因");
  text = text.replace(/\s*错因观察/g, "错因");
  text = text.replace(/\s{2,}/g, " ");
  return text;
}

function _learningBrainEdgePath(edge) {
  if (edge && edge.display_path) return String(edge.display_path);
  var from = _asLearningBrainObject(edge.from);
  var to = _asLearningBrainObject(edge.to);
  return [
    _learningBrainObjectLabel(from.id || from.type || "", from.type || ""),
    _learningBrainObjectLabel(to.id || to.type || "", to.type || ""),
  ]
    .filter(Boolean)
    .join(" → ");
}

function _learningBrainOutcomeText(edgeType) {
  if (edgeType === "training_improved_error") return "本次训练结果：已改善";
  if (edgeType === "training_not_improved_error") return "本次训练结果：未改善";
  return "已推荐训练题";
}

function _buildLearningBrainTrainingChains(graphChain) {
  var uses = _asLearningBrainList(graphChain.training_uses_question);
  var outcomes = _asLearningBrainList(
    graphChain.training_improved_error,
  ).concat(_asLearningBrainList(graphChain.training_not_improved_error));
  var usesByTraining = {};
  uses.forEach(function (edge) {
    var trainingId = _learningBrainNodeId(edge, "from");
    if (trainingId && !usesByTraining[trainingId]) {
      usesByTraining[trainingId] = edge;
    }
  });
  return outcomes
    .map(function (edge, index) {
      var trainingId = _learningBrainNodeId(edge, "from");
      var useEdge = usesByTraining[trainingId] || {};
      var questionId = String(
        edge.question_id || _learningBrainNodeId(useEdge, "to") || "",
      ).trim();
      var errorId = _learningBrainNodeId(edge, "to");
      var improved = edge.edge_type === "training_improved_error";
      return {
        key: "chain-" + index,
        tone: improved ? "improved" : "not-improved",
        title: _humanizeLearningBrainText(
          edge.display_meta ||
            _learningBrainObjectLabel(errorId, "error") ||
            "错因：待确认",
        ),
        training: _humanizeLearningBrainText(
          edge.display_path ||
            _learningBrainObjectLabel(trainingId, "next_training") ||
            "训练建议：围绕薄弱点做变式训练",
        ),
        question: _humanizeLearningBrainText(
          useEdge.display_path ||
            (questionId ? _learningBrainQuestionLabel(questionId) : ""),
        ),
        outcome: _learningBrainOutcomeText(edge.edge_type),
        eventId: "",
        eventLabel:
          edge.event_label ||
          (edge.reason_edge_event_id || edge.evidence_event_id
            ? "训练链证据"
            : ""),
      };
    })
    .slice(0, 4);
}

function _normalizeLearningBrainPayload(raw) {
  var body = api.unwrapResponse(raw) || {};
  var projection = _asLearningBrainObject(
    body.projection || body.learning_brain || body,
  );
  var compiled = _asLearningBrainObject(projection.compiled_objects);
  var weakPoints = _asLearningBrainList(projection.weak_points);
  var graph = _asLearningBrainObject(projection.typed_graph);
  var graphEdges = _asLearningBrainList(
    projection.typed_graph_edges || graph.edges,
  );
  var graphChain = _asLearningBrainObject(projection.graph_chain);
  var visible = _asLearningBrainObject(projection.visible_sections);
  var chainEdges = _asLearningBrainList(graphChain.training_uses_question)
    .concat(_asLearningBrainList(graphChain.training_improved_error))
    .concat(_asLearningBrainList(graphChain.training_not_improved_error));
  var trainingChains = _buildLearningBrainTrainingChains(graphChain);
  var gradingResults = _asLearningBrainList(projection.grading_results);
  var synthesisRun = _asLearningBrainObject(projection.synthesis_run);
  var truths = [];

  _asLearningBrainList(visible.current_truth).forEach(function (item, index) {
    var truth = _asLearningBrainObject(item);
    var level = truth.evidence_level || "";
    truths.push({
      key: "truth-" + index,
      title: _humanizeLearningBrainText(
        truth.display_title || truth.current_truth || truth.object_key || "",
      ),
      meta: _humanizeLearningBrainText(
        truth.display_meta || truth.display_label || "",
      ),
      level: level || "unclassified",
      levelLabel:
        truth.evidence_level_label ||
        _learningBrainLevelLabel(level || "unclassified"),
      eventIds: _learningBrainEventLabels(
        truth.supporting_event_labels,
        truth.supporting_event_ids,
      ),
    });
  });

  if (!truths.length)
    Object.keys(compiled).forEach(function (key) {
      var item = _asLearningBrainObject(compiled[key]);
      var level = item.evidence_level || "";
      var currentTruth =
        item.current_truth || item.claim || item.object_id || "";
      if (!currentTruth && !level) return;
      truths.push({
        key: key,
        title: _humanizeLearningBrainText(currentTruth || key),
        meta: _learningBrainObjectLabel(key, item.object_type || ""),
        level: level || "unclassified",
        levelLabel: _learningBrainLevelLabel(level || "unclassified"),
        eventIds: _learningBrainEventLabels(
          item.supporting_event_labels,
          item.supporting_event_ids,
        ),
      });
    });
  if (!truths.length)
    weakPoints.forEach(function (item, index) {
      var weak = _asLearningBrainObject(item);
      var concept = weak.concept_id || weak.concept || "";
      var error = weak.error_code || weak.error || "";
      var level = weak.evidence_level || "";
      var title =
        weak.current_truth || [concept, error].filter(Boolean).join(" / ");
      if (!title && !level) return;
      truths.push({
        key: "weak-" + index,
        title: _humanizeLearningBrainText(title || "薄弱点"),
        meta:
          [
            _learningBrainObjectLabel(concept, "concept"),
            _learningBrainObjectLabel(error, "error"),
          ]
            .filter(Boolean)
            .join("；") || "薄弱点",
        level: level || "unclassified",
        levelLabel: _learningBrainLevelLabel(level || "unclassified"),
        eventIds: _learningBrainEventLabels(
          weak.supporting_event_labels,
          weak.supporting_event_ids,
        ),
      });
    });

  var evidence = _asLearningBrainList(visible.evidence_flow)
    .map(function (item, index) {
      var flow = _asLearningBrainObject(item);
      var hasEvidence = !!(flow.event_label || flow.event_id);
      return {
        key: "visible-edge-" + index,
        type:
          _humanizeLearningBrainText(flow.display_title) ||
          flow.display_label ||
          _learningBrainEdgeLabel(flow.edge_type),
        path: _humanizeLearningBrainText(
          flow.display_path || flow.path || flow.display_meta || "",
        ),
        eventId: "",
        eventLabel:
          flow.event_label ||
          (hasEvidence ? _learningBrainEvidenceLabel(index) : ""),
      };
    })
    .filter(function (item) {
      return item.type || item.path || item.eventId;
    });
  if (!evidence.length)
    evidence = graphEdges
      .concat(chainEdges)
      .map(function (edge, index) {
        var hasEvidence = !!(
          edge.evidence_event_id ||
          edge.reason_edge_event_id ||
          edge.event_id
        );
        return {
          key: "edge-" + index,
          type:
            _humanizeLearningBrainText(edge.display_title) ||
            edge.display_label ||
            _learningBrainEdgeLabel(edge.edge_type),
          path: _humanizeLearningBrainText(
            edge.display_path || _learningBrainEdgePath(edge),
          ),
          eventId: "",
          eventLabel: hasEvidence ? _learningBrainEvidenceLabel(index) : "",
        };
      })
      .filter(function (item) {
        return item.type || item.path || item.eventId;
      });

  var training = _asLearningBrainList(visible.next_training)
    .map(function (item, index) {
      var plan = _asLearningBrainObject(item);
      return {
        key: "visible-training-" + index,
        title: _humanizeLearningBrainText(
          plan.display_title || plan.claim || "下一步训练",
        ),
        meta: _humanizeLearningBrainText(
          plan.display_meta || plan.display_label || "",
        ),
      };
    })
    .filter(function (item) {
      return item.title || item.meta;
    });
  var eventCount = Number(
    projection.event_count || synthesisRun.input_event_count || 0,
  );
  var createdClaimCount = Number(
    projection.created_claim_count || synthesisRun.created_claim_count || 0,
  );
  var typedGraphEdgeCount = Number(
    projection.typed_graph_edge_count ||
      graph.edge_count ||
      graphEdges.length ||
      0,
  );
  return {
    truths: truths.slice(0, 4),
    evidence: evidence.slice(0, 8),
    training: training.slice(0, 5),
    chains: trainingChains,
    stats: {
      eventCount: Number.isFinite(eventCount) ? eventCount : 0,
      createdClaimCount: Number.isFinite(createdClaimCount)
        ? createdClaimCount
        : 0,
      typedGraphEdgeCount: Number.isFinite(typedGraphEdgeCount)
        ? typedGraphEdgeCount
        : 0,
      projectionSubject:
        projection.projection_subject || projection.subject || "",
      projectionSubjectLabel: _learningBrainSubjectLabel(
        projection.projection_subject || projection.subject || "",
      ),
    },
  };
}

function _normalizeLearnerFacingPayload(raw) {
  var body = api.unwrapResponse(raw) || {};
  var summary = body.summary || {};
  var attempts = (body.recent_attempts || [])
    .map(function (item, index) {
      var card = item || {};
      var tone = String(card.tone || "").trim();
      var questionText = String(card.question_text || card.title || "").trim();
      var answerLine = String(card.answer_line || "").trim();
      var diagnosis = String(card.diagnosis || "").trim();
      var diagnosisDetail = String(card.diagnosis_detail || "").trim();
      var explanation = String(card.explanation || "").trim();
      return {
        key: String(card.key || "attempt-" + index),
        timeLabel: String(card.time_label || "最近"),
        title: String(card.title || questionText || "一次练习").trim(),
        questionText: questionText,
        concept: String(card.concept || "综合练习").trim(),
        resultLabel: String(card.result_label || "").trim(),
        tone: tone === "correct" ? "correct" : "wrong",
        answerLine: answerLine,
        diagnosis: diagnosis || (tone === "correct" ? "稳定答对" : "待归因"),
        diagnosisDetail: diagnosisDetail,
        explanation: explanation,
        evidenceLabel: String(card.evidence_label || "").trim(),
        collectable: Boolean(card.collectable),
        options: Array.isArray(card.options) ? card.options : [],
        detailLines: Array.isArray(card.detail_lines)
          ? card.detail_lines.filter(Boolean)
          : [answerLine, diagnosisDetail, explanation].filter(Boolean),
      };
    })
    .filter(function (item) {
      return item.title || item.answerLine || item.diagnosisDetail;
    });
  var diagnoses = (body.diagnoses || [])
    .map(function (item, index) {
      var card = item || {};
      return {
        key: String(card.key || "diagnosis-" + index),
        levelLabel: String(card.level_label || "").trim(),
        title: String(card.title || "").trim(),
        concept: String(card.concept || "").trim(),
        error: String(card.error || "").trim(),
        meta: String(card.meta || "").trim(),
        detail: String(card.detail || "").trim(),
        action: String(card.action || "").trim(),
        count: Number(card.count || 0),
      };
    })
    .filter(function (item) {
      return item.title || item.detail || item.action;
    });
  var loops = (body.training_loops || [])
    .map(function (item, index) {
      var card = item || {};
      return {
        key: String(card.key || "loop-" + index),
        title: String(card.title || "").trim(),
        from: String(card.from || "").trim(),
        training: String(card.training || "").trim(),
        outcome: String(card.outcome || "").trim(),
        tone: String(card.tone || "not-improved").trim(),
      };
    })
    .filter(function (item) {
      return item.title || item.training || item.outcome;
    });
  var nextAction = body.next_action || {};
  return {
    summary: {
      title: String(summary.title || "学习复盘").trim(),
      headline: String(summary.headline || "").trim(),
      todayDone: Number(summary.today_done || 0),
      recentThreeDone: Number(summary.recent_three_done || 0),
      primaryFocus: String(summary.primary_focus || "").trim(),
      weakCount: Number(summary.weak_count || 0),
    },
    attempts: attempts.slice(0, 5),
    diagnoses: diagnoses.slice(0, 4),
    loops: loops.slice(0, 3),
    nextAction: {
      title: String(nextAction.title || "").trim(),
      subtitle: String(nextAction.subtitle || "").trim(),
      cta: String(nextAction.cta || "开始训练").trim(),
      estimatedMinutes: Number(nextAction.estimated_minutes || 0),
    },
  };
}

function _mistakeBookPayloadFromCard(card) {
  var item = _asLearningBrainObject(card);
  return {
    attempt_ref: String(item.attemptRef || ""),
    subject_id: String(item.subjectId || ""),
    bot_id: String(item.botId || "construction-exam"),
    title: String(item.title || item.questionText || "错题复盘"),
    concept_label: String(item.concept || ""),
    error_label: String(item.diagnosis || ""),
    note: String(item.diagnosisDetail || item.explanation || ""),
    tags: ["learning-report"],
  };
}

function _notebookCardPayloadFromAttempt(card) {
  var item = _asLearningBrainObject(card);
  var attemptRef = String(item.attemptRef || "").trim();
  var diagnosis = String(item.diagnosisDetail || item.diagnosis || "").trim();
  return {
    card_type: diagnosis ? "error_pattern_note" : "scoring_card",
    subject_id: String(item.subjectId || ""),
    source_bot_id: String(item.botId || "construction-exam"),
    source_type: "grading",
    source_ref: attemptRef ? { attempt_ref: attemptRef } : {},
    evidence_event_ids: [],
    title: String(item.title || "批改学习卡").slice(0, 80),
    user_query: diagnosis || "保存这次批改的学习卡",
    output: "",
    ai_enhanced_content: {
      summary: diagnosis || String(item.resultLabel || "一次作答复盘"),
    },
  };
}

// 四态口径对齐后端 _score_status(strong/normal/weak/observed):
// 未学(observed)单独成态——旧三档会把"没学过"误归成"薄弱"(pct 0 → weak),
// 形成红灯墙,违反 10e 暖色语义。兜底阈值 70/40/>0 与后端一致。
function _radarDimStatus(d) {
  var pct = Math.round(((d && d.value) || 0) * 100);
  return (
    (d && (d.status || d.level)) ||
    (pct >= 70 ? "strong" : pct >= 40 ? "normal" : pct > 0 ? "weak" : "observed")
  );
}

var _RADAR_STATE_LABELS = {
  strong: "稳了",
  normal: "再看一眼",
  weak: "待复验",
  observed: "未学",
};

function _buildRadarViewModel(dims) {
  var strong = 0;
  var normal = 0;
  var weak = 0;
  var observed = 0;
  (dims || []).forEach(function (d) {
    // Prefer the upstream status if backend surfaces one (learning-state
    // engine emits mastered / developing / needs_attention); otherwise
    // derive from pct so chapter_mastery payloads still classify correctly.
    var status = _radarDimStatus(d);
    if (status === "strong" || status === "mastered") strong++;
    else if (status === "normal" || status === "developing") normal++;
    else if (status === "weak" || status === "needs_attention") weak++;
    else if (status === "observed") observed++;
  });
  var avg = Math.round(
    ((dims || []).reduce(function (sum, d) {
      return sum + (d.value || 0);
    }, 0) /
      Math.max((dims || []).length, 1)) *
      100,
  );
  var dimList = (dims || [])
    .slice()
    .sort(function (a, b) {
      return (a.value || 0) - (b.value || 0);
    })
    .map(function (d, index) {
      var pct = Math.round((d.value || 0) * 100);
      var status = _radarDimStatus(d);
      return {
        rank: index + 1,
        name: d.name,
        pct: pct,
        cls: d.cls || status,
        status: status,
        stateLabel: _RADAR_STATE_LABELS[status] || _RADAR_STATE_LABELS.observed,
      };
    });
  return {
    strongCount: strong,
    normalCount: normal,
    weakCount: weak,
    observedCount: observed,
    avgScore: avg,
    dimList: dimList,
  };
}

function _normalizeBattlePlan(raw) {
  var plan = raw || {};
  var focusTopic = String(plan.focus_topic || plan.focusTopic || "").trim();
  var priorityTask = String(
    plan.priority_task || plan.priorityTask || "",
  ).trim();
  var studyMethod = String(plan.study_method || plan.studyMethod || "").trim();
  var timeBudget = String(plan.time_budget || plan.timeBudget || "").trim();
  var coachNote = String(plan.coach_note || plan.coachNote || "").trim();

  if (!(focusTopic || priorityTask || studyMethod || timeBudget || coachNote)) {
    return null;
  }
  if (
    _looksLikeUnsafeTrainingPlanText(focusTopic) ||
    _looksLikeUnsafeTrainingPlanText(priorityTask) ||
    _looksLikeUnsafeTrainingPlanText(studyMethod) ||
    _looksLikeUnsafeTrainingPlanText(coachNote)
  ) {
    return null;
  }

  return {
    focusTopic: focusTopic || "今天先稳住基础节奏",
    priorityTask: priorityTask,
    studyMethod: studyMethod,
    timeBudget: timeBudget,
    coachNote: coachNote,
  };
}

function _looksLikeUnsafeTrainingPlanText(value) {
  var text = String(value || "").trim();
  if (!text) return false;
  return (
    text.indexOf("我想练习") >= 0 ||
    text.indexOf("请严格围绕") >= 0 ||
    text.indexOf("当前学习锚点") >= 0 ||
    text.indexOf("training_mode") >= 0 ||
    text.indexOf("mixed_rev") >= 0 ||
    text.indexOf("那出") >= 0
  );
}

function _buildBattlePlanFromPrescription(data) {
  var source = data || {};
  var title = String(source.prescriptionTitle || "").trim();
  var topic = String(source.prescriptionTopic || "").trim();
  var reason = String(
    source.prescriptionReason || source.prescriptionSubtitle || "",
  ).trim();
  var status = String(source.prescriptionStatus || "").trim();
  if (!(title || topic || reason)) return null;
  return _normalizeBattlePlan({
    focus_topic: topic || title,
    priority_task: title || "先来一次起步测评",
    study_method:
      status === "degraded"
        ? "先完成一题真实作答，系统再生成可靠专项训练"
        : "先按处方顺序完成训练，再用验证题确认是否改掉",
    time_budget: status === "degraded" ? "约 3 分钟" : "约 8 分钟",
    coach_note: reason || "这条训练安排来自学情处方",
  });
}

function _buildTrainingExecutionAction(input) {
  var source = input || {};
  var assessmentAction =
    source.assessmentTrainingAction &&
    typeof source.assessmentTrainingAction === "object"
      ? source.assessmentTrainingAction
      : null;
  if (assessmentAction) {
    var followupQuestionContext =
      assessmentAction.followupQuestionContext ||
      assessmentAction.followup_question_context ||
      null;
    var promptIntent = Object.assign({}, assessmentAction);
    delete promptIntent.followupQuestionContext;
    delete promptIntent.followup_question_context;
    var concept = String(assessmentAction.concept_label || "本次错题").trim();
    var count = Math.max(1, Number(assessmentAction.question_count) || 3);
    var query = String(assessmentAction.prompt || "").trim();
    if (!query) {
      query =
        "请围绕我刚才错的“" +
        concept +
        "”，出 " +
        count +
        " 道同类选择题训练我。先只出题，不要提前给答案和解析。";
    }
    return {
      type: "chat",
      label: "练 " + count + " 道同类题",
      hint: "带上本次错题、错因和 attempt_ref 进入结构化训练",
      query: query,
      promptIntent: promptIntent,
      followupQuestionContext: followupQuestionContext,
    };
  }
  var plan = source.battlePlan || {};
  var status = String(source.prescriptionStatus || "").trim();
  var topic = String(
    source.prescriptionTopic ||
      plan.focusTopic ||
      source.focusHint ||
      "当前薄弱点",
  ).trim();
  var task = String(plan.priorityTask || source.nextActionTitle || "").trim();
  var method = String(plan.studyMethod || "").trim();
  var evidenceCount = Number(source.prescriptionEvidenceCount || 0);
  var assessmentEnabled = source.assessmentEnabled !== false;

  if (status === "degraded") {
    var degradedLabel =
      String(source.prescriptionCtaLabel || "").trim() ||
      (evidenceCount > 0 ? "补一题诊断" : "去做摸底测试");
    return {
      type: assessmentEnabled ? "assessment" : "chat",
      label: assessmentEnabled ? degradedLabel : "去对话补一题",
      hint: assessmentEnabled
        ? "进入摸底测试，用 1 题补齐稳定诊断依据"
        : "带上当前处方进入对话，让 AI 先出 1 道诊断题",
      query:
        "请根据我的学情处方，先出 1 道可诊断题，目标是补齐稳定的题目主题和错因链。答完后再生成下一轮专项训练。",
    };
  }

  var activeTopic = topic || "当前薄弱点";
  var activeTask = task || "按今日处方开始一组定向训练";
  var activeMethod =
    method || "先诊断错因，再做同类专项，最后用新题验证是否真正掌握。";
  return {
    type: "chat",
    label: "去对话训练",
    hint: "带上今日处方进入对话，由 AI 直接出第一组专项题",
    query:
      "请根据我的学情处方开始训练。当前主攻：" +
      activeTopic +
      "。优先任务：" +
      activeTask +
      "。训练顺序：" +
      activeMethod +
      " 请先出第一组题，并在每题后按错因给出简短反馈。",
  };
}

function _buildProgressCards(input) {
  var data = input || {};
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var streakDays = Number(data.streakDays) || 0;
  var dueKnown = data.dueTodayKnown === true;
  var dueToday = dueKnown ? Number(data.dueTodayCount) || 0 : 0;
  var hotspotCount = Array.isArray(data.hotspots) ? data.hotspots.length : 0;
  var progressPct =
    dailyTarget > 0
      ? Math.min(100, Math.round((todayDone / dailyTarget) * 100))
      : 0;

  return [
    {
      label: "今日完成",
      value:
        dailyTarget > 0 ? todayDone + "/" + dailyTarget : String(todayDone),
      detail:
        dailyTarget > 0 ? "目标进度 " + progressPct + "%" : "今天已完成练习",
      toneClass: progressPct >= 100 ? "tone-good" : "tone-accent",
    },
    {
      label: "连续学习",
      value: streakDays + "天",
      detail: streakDays > 0 ? "节奏正在形成" : "今天开始建立节奏",
      toneClass: streakDays >= 3 ? "tone-good" : "tone-accent",
    },
    {
      label: "待复习",
      value: dueKnown ? String(dueToday) : "—",
      detail: dueKnown
        ? dueToday > 0
          ? "建议今天优先清理"
          : "当前没有到期项"
        : "复习排程暂不可用",
      toneClass: dueToday > 0 || !dueKnown ? "tone-warn" : "tone-accent",
    },
    {
      label: "热点关注",
      value: String(hotspotCount),
      detail: hotspotCount > 0 ? "优先看高频失分点" : "当前证据未定位到热点",
      toneClass: hotspotCount > 0 ? "tone-warn" : "tone-accent",
    },
  ];
}

function _buildProgressInsight(input) {
  var data = input || {};
  var dueToday = Number(data.dueTodayCount) || 0;
  var hotspotCount = Array.isArray(data.hotspots) ? data.hotspots.length : 0;
  var weakGroup = (data.masteryGroups || []).find(function (group) {
    return (
      group &&
      group.name === "需要加强" &&
      Array.isArray(group.chapters) &&
      group.chapters.length
    );
  });
  var weakChapter =
    weakGroup && weakGroup.chapters[0] ? weakGroup.chapters[0].name : "";

  if (data.focusHint) return data.focusHint;
  if (weakChapter) {
    return (
      "当前最值得观察的变化点在“" +
      weakChapter +
      "”，继续推进后这里最容易先出现抬升"
    );
  }
  if (dueToday > 0) {
    return (
      "今天还有 " + dueToday + " 个待复习点，先清掉它们，后面的进步反馈会更扎实"
    );
  }
  if (hotspotCount > 0) {
    return (
      "系统检测到 " +
      hotspotCount +
      " 个高频失分热点，先处理这些点更容易看到掌握度变化"
    );
  }
  return "先保持今天的学习动作，系统会持续把你的节奏变化沉淀成可见反馈";
}

function _buildProgressSummary(input) {
  var data = input || {};
  var streakDays = Number(data.streakDays) || 0;
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  if (dailyTarget > 0) {
    return (
      (streakDays > 0 ? "已连续学习 " + streakDays + " 天" : "今天是新的起点") +
      "，当前已完成 " +
      todayDone +
      "/" +
      dailyTarget +
      "，继续保持就能看到更稳的进步反馈"
    );
  }
  return streakDays > 0
    ? "已连续学习 " + streakDays + " 天，继续保持，系统会持续记录你的进步轨迹"
    : "开始完成今天的第一轮练习后，这里会出现更清晰的进步反馈";
}

function _buildProgressMilestones(input) {
  var data = input || {};
  var milestones = [];
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var streakDays = Number(data.streakDays) || 0;
  var dueToday = Number(data.dueTodayCount) || 0;
  var weakGroup = (data.masteryGroups || []).find(function (group) {
    return (
      group &&
      group.name === "需要加强" &&
      Array.isArray(group.chapters) &&
      group.chapters.length
    );
  });
  var weakChapter =
    weakGroup && weakGroup.chapters[0] ? weakGroup.chapters[0] : null;

  if (todayDone > 0) {
    milestones.push({
      title: "今日学习已经启动",
      detail:
        dailyTarget > 0
          ? "今天已完成 " +
            todayDone +
            "/" +
            dailyTarget +
            "，继续推进后这里会更快出现正向反馈"
          : "今天已经完成 " + todayDone + " 题，系统开始记录你的变化轨迹",
      toneClass: "tone-accent",
    });
  }

  if (weakChapter && weakChapter.name) {
    milestones.push({
      title: "薄弱章节已经锁定",
      detail:
        "当前最需要优先拉升的是“" +
        weakChapter.name +
        "”，掌握度 " +
        weakChapter.mastery +
        "%",
      toneClass: "tone-warn",
    });
  }

  if (streakDays > 0) {
    milestones.push({
      title: streakDays >= 3 ? "连续学习节奏已形成" : "连续学习正在建立",
      detail:
        streakDays >= 3
          ? "已经连续学习 " + streakDays + " 天，继续保持更容易看到掌握度抬升"
          : "已连续学习 " +
            streakDays +
            " 天，再保持几天就能形成更稳定的进步曲线",
      toneClass: streakDays >= 3 ? "tone-good" : "tone-accent",
    });
  }

  if (dueToday > 0) {
    milestones.push({
      title: "复习压力还需要处理",
      detail:
        "今天还有 " + dueToday + " 个待复习点，先清理这些内容，再加练会更高效",
      toneClass: "tone-warn",
    });
  }

  return milestones.slice(0, 3);
}

function _normalizeProgressFeedback(raw) {
  var feedback = raw || {};
  var summary = String(feedback.summary || "").trim();
  var insight = String(feedback.insight || "").trim();
  var cards = (feedback.cards || [])
    .map(function (item) {
      return {
        label: String(item.label || "").trim(),
        value: String(item.value || "").trim(),
        detail: String(item.detail || "").trim(),
        toneClass:
          String(item.tone_class || item.toneClass || "tone-accent").trim() ||
          "tone-accent",
      };
    })
    .filter(function (item) {
      return item.label || item.value || item.detail;
    });
  var milestones = (feedback.milestones || [])
    .map(function (item) {
      return {
        title: String(item.title || "").trim(),
        detail: String(item.detail || "").trim(),
        toneClass:
          String(item.tone_class || item.toneClass || "tone-accent").trim() ||
          "tone-accent",
      };
    })
    .filter(function (item) {
      return item.title || item.detail;
    });

  if (!(summary || insight || cards.length || milestones.length)) {
    return null;
  }

  return {
    summary: summary,
    insight: insight,
    cards: cards,
    milestones: milestones,
  };
}

function _hasSnapshotData(value) {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.length > 0;
  return Object.keys(value).length > 0;
}

function _snapshotValue(snapshot, key) {
  var value = snapshot && snapshot[key];
  return _hasSnapshotData(value) ? value : null;
}

function _unwrapSnapshotItem(raw) {
  var value = api.unwrapResponse(raw);
  return reportSnapshot.isLearningReportPayload(value) ? value : null;
}

var _DEGRADED_SOURCE_LABELS = {
  today_progress: "今日进度",
  home_dashboard: "首页仪表盘",
  assessment_profile: "诊断画像",
  mastery_dashboard: "掌握度看板",
  learner_events: "学习事件",
  compiled_truth: "Learning Brain 持久结论",
  dry_run_synthesis: "Learning Brain 即时合成",
  learning_report: "学情统一接口",
  learning_report_window: "近 3 天窗口",
  note_assets: "学习卡片",
};

function _buildDegradedHint(sources) {
  var list = (Array.isArray(sources) ? sources : []).filter(Boolean);
  if (!list.length) return "";
  var labels = list.map(function (name) {
    return _DEGRADED_SOURCE_LABELS[name] || name;
  });
  return "部分数据降级：" + labels.join("、");
}

function _reportOptionalRead(promise, timeoutMs) {
  var settled = false;
  return new Promise(function (resolve) {
    var timer = setTimeout(function () {
      if (settled) return;
      settled = true;
      resolve(null);
    }, timeoutMs || REPORT_UNIFIED_READ_TIMEOUT_MS);
    promise
      .then(function (value) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(value);
      })
      .catch(function () {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(null);
      });
  });
}

function _emptyReportHome() {
  return buildReportHomeViewModel({});
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,

    // WXML 不支持 HTML 实体，用 data 绑定传入 Unicode 字符
    // \u7A7A\u6001\u5370\u7AE0\u4E66\u6CD5\u5B57\uFF08emoji \u5B57\u7B26\u56FE\u6807\u8FDD\u53CD\u7EBF\u6027\u56FE\u6807\u7EAA\u5F8B\uFF0C\u6539\u4E0E attempt-detail \u7A7A\u6001\u540C\u6784\uFF09
    warnIcon: "\u91CD",
    radarIcon: "\u6D4B",

    isDark: false, // 学情页默认亮色(owner 2026-07-12);用户显式选过主题则跟随
    reportDetailView: "home",
    reportDetailTitle: REPORT_DETAIL_TITLES.home,
    reportScrollTop: 0,

    // 加载状态
    radarLoading: true,
    masteryLoading: true,
    learningBrainLoading: true,
    radarError: false,
    masteryError: false,
    learningBrainError: false,
    learningBrainEmpty: false,

    // B5 精简首页：learning-report 只提供近期证据/盲点；唯一下一步只读
    // homeDashboard.next_step，经学习页共用翻译器生成。
    reportHome: _emptyReportHome(),

    // 雷达图数据
    radarDimensions: [],
    strongCount: 0,
    normalCount: 0,
    weakCount: 0,
    observedCount: 0,
    avgScore: 0,

    // ── 10e 诊断单(第 10 轮定稿 + round11 增量①) ──
    // 掌握地图 40 格:全部字段来自 read model pack_lifecycle 投影,前端零判分
    masteryMap: {
      available: false,
      degraded: false,
      packUniverse: 0,
      cells: [],
      counts: { stable: 0, watch: 0, reverify: 0, unlearned: 0, blue: 0 },
    },
    // 风险档位词(非精确百分比)+ 主要差距 + 方向性趋势(不画假曲线)
    riskGearLabel: "待评估",
    riskGearTone: "none",
    diagnosisHeadline: "",
    trendDirection: "",
    trendNarrative: "",
    recurrentErrorCount: 0,
    // 轻量诊断卡折叠单:默认收起,只给结论
    diagFoldOpen: false,

    // 维度详情列表（按后端 projection 顺序展示）
    dimList: [],

    // 雷达图渲染后的图片（解决 canvas 不跟随滚动的问题）
    radarImage: "",

    // 掌握度数据
    overallMastery: 0,
    overallMasteryKnown: false,
    masteryScoreClass: "",
    masteryGroups: [],
    hotspots: [],
    knowledgeSummary: {},
    textbookChapters: [],
    reviewSummary: { total_due: 0, overdue_count: 0 },
    todayDone: 0,
    dailyTarget: 0,
    streakDays: 0,
    dueTodayCount: 0,
    dueTodayKnown: false,
    dueTodayState: "unavailable",
    weakNodeCount: 0,
    focusHint: "",
    homeStudyPlan: null,
    homeProgressFeedback: null,
    learnerLevel: "",
    learnerLevelName: "",
    learnerStageTitle: "当前学习状态",
    studyTip: "",
    diagnosticScore: 0,
    learningBrainTruths: [],
    learningBrainEvidence: [],
    learningBrainTraining: [],
    learningBrainChains: [],
    learningReviewSummary: {
      title: "学习复盘",
      headline: "",
      todayDone: 0,
      recentThreeDone: 0,
      primaryFocus: "",
      weakCount: 0,
    },
    learningAttemptCards: [],
    noteAssets: [],
    todayTasks: [],
    learningDiagnosisCards: [],
    learningTrainingLoops: [],
    learningNextAction: { title: "", subtitle: "", cta: "开始训练" },
    gradingLoopStatus: "",
    gradingLoopNextRequiredAction: "",
    gradingLoopEvidenceRefs: [],
    gradingLoopCurrentAction: {},
    gradingLoopLatestOutcome: {},
    gradingLoopStages: [],
    gradingLoopAuthority: {},
    gradingLoopSourceStatus: {},
    trainingExecutionAction: {
      type: "chat",
      label: "去对话训练",
      hint: "带上今日处方进入对话，由 AI 直接出第一组专项题",
      query: "",
      promptIntent: null,
    },
    assessmentTrainingAction: null,
    learningBrainGraphStats: {
      eventCount: 0,
      createdClaimCount: 0,
      typedGraphEdgeCount: 0,
      projectionSubject: "",
      projectionSubjectLabel: "",
    },
    battlePlan: {
      focusTopic: "",
      priorityTask: "",
      studyMethod: "",
      timeBudget: "",
      coachNote: "",
    },
    progressSummary: "完成更多练习后，这里会出现更清晰的进步反馈",
    progressInsight: "先开始今天的练习，系统会逐步把你的变化沉淀成更清晰的反馈",
    progressCards: _buildProgressCards({}),
    progressMilestones: _buildProgressMilestones({}),
    navBackLabel: "对话",
    assessmentEnabled: true,
    degradedHint: "",
    degradedSources: [],
    reportFallbackActive: false,
    reportModuleHintVisible: true,
    isGuestPreview: false,
  },

  _radarRenderSeq: 0,
  _radarRenderPending: false,
  _radarImageSignature: "",
  _radarSignature: "",
  _reportSnapshot: null,
  // 「页面进入 vs 子页返回」判别位:首个 onShow=页面进入(允许新鲜缓存跳过网络),
  // 后续 onShow=子页返回(刚发生学习动作,强制刷新)。数据加载只由 onShow 触发。
  _shownOnce: false,

  onLoad(options) {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    const requestedDetail =
      options && options.detail ? String(options.detail) : "";
    const assessmentTrainingAction =
      requestedDetail === "training"
        ? this._readPendingAssessmentTrainingAction(options)
        : null;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
      reportDetailView: REPORT_DETAIL_TITLES[requestedDetail]
        ? requestedDetail
        : this.data.reportDetailView,
      reportDetailTitle:
        REPORT_DETAIL_TITLES[requestedDetail] || this.data.reportDetailTitle,
      reportModuleHintVisible: this._shouldShowReportModuleHint(),
      assessmentTrainingAction: assessmentTrainingAction,
    });
  },

  _readPendingAssessmentTrainingAction(options) {
    var stored = null;
    try {
      stored = auth.readOwnerStorage
        ? auth.readOwnerStorage(ASSESSMENT_PENDING_TRAINING_ACTION_KEY)
        : null;
    } catch (_) {
      stored = null;
    }
    var intent =
      stored && typeof stored === "object" ? Object.assign({}, stored) : {};
    var attemptRef = String(
      intent.attempt_ref || (options && options.attempt_ref) || "",
    ).trim();
    var concept = String(
      intent.concept_label || (options && options.knowledge_point) || "",
    ).trim();
    var error = String(
      intent.error_label || (options && options.error_code) || "",
    ).trim();
    if (!attemptRef && !concept && !error) return null;
    if (attemptRef) intent.attempt_ref = attemptRef;
    if (concept) intent.concept_label = concept;
    if (error) intent.error_label = error;
    intent.source = String(intent.source || "assessment_result_wrong_item");
    intent.learning_signal_type = String(
      intent.learning_signal_type || "assessment_wrong_item_practice",
    );
    intent.subject_id = String(intent.subject_id || "construction_exam");
    intent.question_count = Math.max(1, Number(intent.question_count) || 3);
    intent.training_mode = String(intent.training_mode || "same_type_repair");
    if (!Array.isArray(intent.evidence_refs)) {
      intent.evidence_refs = attemptRef ? [attemptRef] : [];
    }
    return intent;
  },

  onShow() {
    surfaceTelemetry.trackModuleView(this, { module: "learning_report", section: "home" });
    var workspaceBack = runtime.getWorkspaceBack(route.report());
    if (!flags.ensureFeatureEnabled("report")) return;
    this.setData({ isDark: helpers.isDarkOr("light") });
    this.setData({
      navBackLabel: workspaceBack ? workspaceBack.label : "对话",
      assessmentEnabled: flags.isFeatureEnabled("assessment"),
    });
    // 五 tab 壳:学情 index=3
    helpers.syncTabBar(this, 3, {
      hidden: !flags.shouldShowWorkspaceShell(),
      isDark: helpers.isDarkOr("light"),
    });
    var loggedIn = auth.isLoggedIn();
    var reportOwnerId = loggedIn
      ? String((auth.getUserId && auth.getUserId()) || "").trim()
      : "";
    if (this._reportHomeOwnerId !== reportOwnerId) {
      // 页面实例可能跨登录态复用；先清空上一 owner 的可见首页投影，再读
      // owner-scoped cache/网络，防止切号瞬间闪出上一位学员的盲点。
      this._reportHomeOwnerId = reportOwnerId;
      this._reportSnapshot = null;
      this.setData({ reportHome: _emptyReportHome() });
    }
    if (!loggedIn) {
      this.setData({
        isGuestPreview: true,
        radarLoading: false,
        masteryLoading: false,
        learningBrainLoading: false,
        radarError: false,
        masteryError: false,
        learningBrainError: false,
        learningBrainEmpty: false,
        degradedHint: "",
        reportFallbackActive: false,
      });
      this._syncExperienceSections();
      return;
    }
    var reportFirstShow = !this._shownOnce;
    this._shownOnce = true;
    this.setData({
      isGuestPreview: false,
      radarLoading: true,
      masteryLoading: true,
      learningBrainLoading: true,
      radarError: false,
      masteryError: false,
      learningBrainError: false,
      learningBrainEmpty: false,
    });
    this._loadReportPage({ freshSkip: reportFirstShow });
  },

  onHide() {
    surfaceTelemetry.trackModuleExit(this);
  },

  onUnload() {
    surfaceTelemetry.trackModuleExit(this);
  },

  async _loadReportSnapshot() {
    var optionalReadOpts = { suppressAuthRedirect: true };
    optionalReadOpts.schemaVersion = 2;
    // 掌握地图 40 格的绿灯站标题/深链元数据:复用既有 getLubanLessons,
    // 与 unified report 并行拉;失败只降级(格子仍按 lifecycle 渲染,点击不深链)。
    const lessonsPromise =
      typeof api.getLubanLessons === "function"
        ? _reportOptionalRead(
            api.getLubanLessons({ suppressAuthRedirect: true }),
            REPORT_UNIFIED_READ_TIMEOUT_MS,
          )
        : Promise.resolve(null);
    const homePromise =
      typeof api.getHomeDashboard === "function"
        ? _reportOptionalRead(
            api.getHomeDashboard({ suppressAuthRedirect: true }),
            REPORT_UNIFIED_READ_TIMEOUT_MS,
          )
        : Promise.resolve(null);
    const report = _unwrapSnapshotItem(
      await _reportOptionalRead(api.getLearningReport(100, optionalReadOpts), REPORT_UNIFIED_READ_TIMEOUT_MS),
    );
    if (!report) {
      // 5xx / network failure / payload contract 断裂 → 返回 null 让 _loadReportPage 走显式 fallback
      return null;
    }
    const supportingReads = await Promise.all([lessonsPromise, homePromise]);
    const lessons = api.unwrapResponse(supportingReads[0]) || null;
    const homeDashboard = api.unwrapResponse(supportingReads[1]) || null;
    // 组装收权:快照形状由唯一 builder 组装(report 已过合法性检查,必返回非 null)。
    return reportSnapshot.buildUnifiedReportSnapshot({
      report: report,
      homeDashboard: homeDashboard,
      lessons: lessons,
    });
  },

  async _loadReportPage(options) {
    var opts = options || {};
    var userId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    var generation = Number(this._reportLoadGeneration || 0) + 1;
    this._reportLoadGeneration = generation;
    var isCurrentRequest = function (page) {
      var currentUserId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
      return !!userId && page._reportLoadGeneration === generation && currentUserId === userId;
    };
    // readWithMeta 带回快照年龄供「新鲜即跳过网络」判定;typeof 守卫兜底旧
    // vm 测试 harness 的 report-cache stub(只有 read/write),行为与原 read 等价。
    var cachedHit =
      typeof reportCache.readWithMeta === "function"
        ? reportCache.readWithMeta(userId, reportCache.SNAPSHOT_MAX_AGE_MS)
        : null;
    var cachedSnapshot = cachedHit
      ? cachedHit.snapshot
      : reportCache.read(userId, reportCache.SNAPSHOT_MAX_AGE_MS);
    if (cachedSnapshot && isCurrentRequest(this)) {
      // 「新鲜即跳过网络」:仅页面进入(首个 onShow,opts.freshSkip=true)且快照
      // 年龄 < FRESH_MAX_AGE_MS 时,以缓存为终态渲染并省掉网络重拉;
      // 子页返回(后续 onShow,刚发生学习动作)不带 freshSkip,保持强制刷新。
      if (
        opts.freshSkip &&
        cachedHit &&
        cachedHit.ageMs < reportCache.FRESH_MAX_AGE_MS
      ) {
        this._reportSnapshot = cachedSnapshot;
        // 非 cached hydrate:降级提示如实反映快照自身状态(不显示"正在刷新"),
        // 且 _hydrateFromUnifiedReport 会清掉 radar/mastery/learningBrain 全部 loading 态。
        this._hydrateFromUnifiedReport(cachedSnapshot, {});
        this._syncExperienceSections();
        return;
      }
      this._reportSnapshot = cachedSnapshot;
      this._hydrateFromUnifiedReport(cachedSnapshot, { cached: true });
      this._syncExperienceSections();
    }
    var snapshot = await this._loadReportSnapshot();
    if (!isCurrentRequest(this)) return;
    if (snapshot) {
      this._reportSnapshot = snapshot;
      reportCache.write(userId, snapshot);
      this._hydrateFromUnifiedReport(snapshot);
      this._syncExperienceSections();
      return;
    }
    if (cachedSnapshot) {
      this.setData({
        radarLoading: false,
        masteryLoading: false,
        learningBrainLoading: false,
        degradedHint:
          this.data.degradedHint || "网络暂时不稳，已显示上次学情快照",
        degradedSources:
          this.data.degradedSources && this.data.degradedSources.length
            ? this.data.degradedSources
            : ["learning_report"],
        reportFallbackActive: false,
      });
      this._syncExperienceSections();
      return;
    }
    // Fallback：unified report 拿不到时只暴露降级状态；不再调用旧 reader 组合。
    this._reportSnapshot = null;
    this.setData({
      degradedHint: "学情接口暂时不可用，已显示基础数据",
      degradedSources: ["learning_report"],
      reportFallbackActive: true,
      radarLoading: false,
      masteryLoading: false,
      learningBrainLoading: false,
      radarError: true,
      masteryError: true,
      learningBrainError: true,
    });
    this._syncExperienceSections();
  },

  _hydrateFromUnifiedReport(snapshot, options) {
    var opts = options || {};
    var report = (snapshot && snapshot.report) || {};
    var overview = report.overview || {};
    var home = (snapshot && snapshot.home) || {};
    var sharedReport = reportViewModel.buildLearningReportViewModel(report);
    var sharedPageData = reportViewModel.toReportPageData(sharedReport);
    var canonicalLearningTask = buildCanonicalLearningTask({
      homeDashboard: snapshot && snapshot.homeDashboard,
      lessons: snapshot && snapshot.lessons,
      // review(到期验证)供给真值在 pack_review(二轮红队 A5):
      // forward-only 的 lessons light 旗标不得裁决 review 资格
      report: report,
    });
    var reportHome = buildReportHomeViewModel({
      report: report,
      reportPageData: sharedPageData,
      nextTask: canonicalLearningTask,
    });
    // 掌握地图 40 格(10e 核心):pack_lifecycle × 绿灯 lessons 纯投影
    var masteryMap =
      typeof reportViewModel.buildPackMasteryMap === "function"
        ? reportViewModel.buildPackMasteryMap(report, snapshot && snapshot.lessons)
        : this.data.masteryMap;
    this.setData(
      Object.assign({}, sharedPageData, {
        reportHome: reportHome,
        masteryMap: masteryMap,
        todayDone: overview.today_done || 0,
        dailyTarget: overview.daily_target || 0,
        streakDays: overview.streak_days || 0,
        dueTodayCount: sharedPageData.dueTodayCount,
        dueTodayKnown: sharedPageData.dueTodayKnown === true,
        dueTodayState: sharedPageData.dueTodayState || "unavailable",
        weakNodeCount: overview.weak_node_count || 0,
        focusHint: overview.focus_hint || "",
        homeStudyPlan: home.study_plan || null,
        homeProgressFeedback: home.progress_feedback || null,
        learnerLevel: _displayLevelName(overview.learner_level || ""),
        learnerLevelName: _displayLevelName(overview.learner_level || ""),
        learnerStageTitle: overview.learner_level
          ? _displayLevelName(overview.learner_level) + "阶段"
          : "当前学习状态",
        studyTip: overview.study_tip || "",
        radarLoading: false,
        radarError: false,
        masteryLoading: false,
        masteryError: false,
        learningBrainLoading: false,
        learningBrainError: false,
        degradedHint: opts.cached
          ? "正在刷新，先显示上次学情快照"
          : snapshot.degraded
            ? _buildDegradedHint(snapshot.degradedSources)
            : "",
        degradedSources: opts.cached
          ? ["learning_report"]
          : snapshot.degraded
            ? snapshot.degradedSources.slice()
            : [],
        prescriptionAuthority: sharedPageData.prescriptionAuthority || "",
        prescriptionEvidenceLabels:
          sharedPageData.prescriptionEvidenceRefs || [],
        reportFallbackActive: false,
      }),
    );
    if (sharedPageData.radarDimensions.length) {
      this._radarSignature = _buildRadarSignature(
        sharedPageData.radarDimensions,
      );
      this._ensureRadarRendered(
        sharedPageData.radarDimensions,
        this._radarSignature,
      );
    }
  },

  onReady() {
    this._canvasReady = true;
    this._ensureRadarRendered(
      this.data.radarDimensions,
      this._radarSignature || _buildRadarSignature(this.data.radarDimensions),
    );
  },

  handleReportBack() {
    if (this.data.reportDetailView && this.data.reportDetailView !== "home") {
      this._setReportDetailView("home");
      return;
    }
    this.goHome();
  },

  openReportDetail(event) {
    var detail =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.detail
        : "";
    if (!detail) return;
    helpers.vibrate("light");
    this._dismissReportModuleHint();
    this._setReportDetailView(detail);
  },

  dismissReportModuleHint() {
    helpers.vibrate("light");
    this._dismissReportModuleHint();
  },

  toggleMasteryGroup(e) {
    var index = Number(e && e.currentTarget && e.currentTarget.dataset.index);
    var groups = (this.data.masteryGroups || []).map(
      function (group, groupIndex) {
        if (groupIndex !== index) return group;
        return Object.assign({}, group, { expanded: !group.expanded });
      },
    );
    helpers.vibrate("light");
    this.setData({ masteryGroups: groups });
  },

  _setReportDetailView(view) {
    var next = REPORT_DETAIL_TITLES[view] ? view : "home";
    var scrollTop = this.data.reportScrollTop === 0 ? 1 : 0;
    this.setData({
      reportDetailView: next,
      reportDetailTitle: REPORT_DETAIL_TITLES[next],
      reportScrollTop: scrollTop,
    });
    if (next === "map") {
      wx.nextTick(() => {
        this._ensureRadarRendered(
          this.data.radarDimensions,
          this._radarSignature ||
            _buildRadarSignature(this.data.radarDimensions),
        );
      });
    }
  },

  _shouldShowReportModuleHint() {
    if (typeof wx === "undefined" || typeof wx.getStorageSync !== "function") {
      return true;
    }
    try {
      return wx.getStorageSync(REPORT_MODULE_HINT_STORAGE_KEY) !== "dismissed";
    } catch (err) {
      return true;
    }
  },

  _dismissReportModuleHint() {
    if (!this.data.reportModuleHintVisible) return;
    this.setData({ reportModuleHintVisible: false });
    if (typeof wx === "undefined" || typeof wx.setStorageSync !== "function")
      return;
    try {
      wx.setStorageSync(REPORT_MODULE_HINT_STORAGE_KEY, "dismissed");
    } catch (err) {}
  },

  // ── 返回首页 ───────────────────────────────────────
  goHome() {
    var workspaceBack = runtime.consumeWorkspaceBack(route.report());
    if (workspaceBack && workspaceBack.url) {
      wx.reLaunch({ url: workspaceBack.url });
      return;
    }
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.markGoHome();
    wx.reLaunch({ url: route.chat() });
  },

  goQuickLogin() {
    this._requireLogin();
  },

  _requireLogin() {
    runtime.redirectToLogin(route.report());
  },

  openMistakeBook() {
    helpers.vibrate("light");
    this._dismissReportModuleHint();
    wx.navigateTo({ url: route.mistakeBook() });
  },

  // ── 10e 诊断单交互(照镜子页:全部只读/深链,零写入) ─────────────

  // 轻量诊断卡折叠单:展开/收起只是本地视图态
  toggleDiagFold() {
    helpers.vibrate("light");
    this.setData({ diagFoldOpen: !this.data.diagFoldOpen });
  },

  // 掌握地图点格深链:绿灯站回学习页对应站;未开通站如实说,不装可点
  openMasteryCell(event) {
    var ds =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset
        : {};
    var packId = String(ds.packId || "").trim();
    if (!packId) return;
    helpers.vibrate("light");
    if (!ds.green) {
      wx.showToast({ title: "这一站即将开通", icon: "none", duration: 1400 });
      return;
    }
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/station/station?pack_id=" +
        encodeURIComponent(packId),
    });
  },

  // 学情首页唯一行动键：仅转发学习页共用的 canonical task，不从诊断卡
  // 自行生成处方，也不把旧 learningBrain.nextAction 提升成并行 authority。
  goReportHomeTask() {
    var home = (this.data && this.data.reportHome) || {};
    var task = home.nextTask || {};
    var packId = String(task.pack_id || "").trim();
    if (!task.cta || !packId) return;
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    helpers.vibrate("light");
    runtime.setWorkspaceBack(route.report(), "学情");
    var url = "";
    if (task.action_kind === "lesson") {
      url = route.lubanStation(packId);
    } else if (task.action_kind === "retest" && task.practice_kind === "retest") {
      url =
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
        encodeURIComponent(packId) +
        "&mode=" +
        (task.mode === "review" ? "review" : "forward") +
        "&training_intent_id=" +
        encodeURIComponent(String(task.training_intent_id || "")) +
        "&probe_id=" +
        encodeURIComponent(String(task.probe_id || ""));
    }
    if (!url) return;
    wx.navigateTo({
      url: url,
      fail: function () {
        if (wx.reLaunch) wx.reLaunch({ url: url });
      },
    });
  },

  // 10e 诊断单唯一行动键:把诊断喂回本周计划(深链学习路线站点)。
  // d2e62d46 随 B5 精简误删,owner 2026-07-17 拍板恢复 10e 主面时一并还原。
  absorbDiagnosisIntoPlan() {
    helpers.vibrate("light");
    runtime.setWorkspaceBack(route.report(), "学情");
    var url = route.lubanStations();
    wx.navigateTo({
      url: url,
      fail: function () {
        if (wx.reLaunch) wx.reLaunch({ url: url });
      },
    });
  },

  async _loadOverview(snapshot) {
    // unified report 命中由 _hydrateFromUnifiedReport 完整接管；snapshot 非空时直接返回。
    if (snapshot) return;
    try {
      var optionalReadOpts = { suppressAuthRedirect: true };
      const progress =
        api.unwrapResponse(await api.getTodayProgress(optionalReadOpts)) || {};
      const home =
        api.unwrapResponse(await api.getHomeDashboard(optionalReadOpts)) || {};
      const assessment =
        api.unwrapResponse(await api.getAssessmentProfile(optionalReadOpts)) ||
        {};

      const weakNodes = ((home.mastery || {}).weak_nodes || []).filter(Boolean);
      const diagnosticFeedback = assessment.diagnostic_feedback || {};
      const learnerProfile = diagnosticFeedback.learner_profile || {};

      this.setData({
        todayDone: progress.today_done || 0,
        dailyTarget: progress.daily_target || 0,
        streakDays: progress.streak_days || 0,
        dueTodayCount: null,
        dueTodayKnown: false,
        dueTodayState: "unavailable",
        weakNodeCount: weakNodes.length,
        focusHint: (home.today || {}).hint || "",
        homeStudyPlan: home.study_plan || null,
        homeProgressFeedback: home.progress_feedback || null,
        learnerLevel: _displayLevelName(assessment.level || ""),
        learnerLevelName: _displayLevelName(assessment.level || ""),
        learnerStageTitle: assessment.level
          ? _displayLevelName(assessment.level) + "阶段"
          : "当前学习状态",
        studyTip: learnerProfile.study_tip || "",
      });
    } catch (_) {}
  },

  async _loadLearningBrain(snapshot) {
    // unified report 命中由 _hydrateFromUnifiedReport 完整接管；snapshot 非空时直接返回。
    if (snapshot) return;
    try {
      var optionalReadOpts = { suppressAuthRedirect: true };
      const payload =
        api.unwrapResponse(
          await api.getLearningBrainProjection(100, optionalReadOpts),
        ) || {};
      var normalized = _normalizeLearningBrainPayload(payload);
      var isEmpty =
        normalized.truths.length === 0 &&
        normalized.evidence.length === 0 &&
        normalized.training.length === 0 &&
        normalized.chains.length === 0 &&
        !normalized.stats.eventCount &&
        !normalized.stats.createdClaimCount &&
        !normalized.stats.typedGraphEdgeCount;
      this.setData({
        learningBrainTruths: normalized.truths,
        learningBrainEvidence: normalized.evidence,
        learningBrainTraining: normalized.training,
        learningBrainChains: normalized.chains,
        learningBrainGraphStats: normalized.stats,
        learningBrainLoading: false,
        learningBrainError: false,
        learningBrainEmpty: isEmpty,
      });
    } catch (_err) {
      this.setData({
        learningBrainLoading: false,
        learningBrainError: true,
        learningBrainEmpty: false,
      });
    }
  },

  // ── 加载学情数据（unified payload 不可用时的兜底）────
  async _loadRadar(snapshot) {
    if (snapshot) return;
    var optionalReadOpts = { suppressAuthRedirect: true };
    try {
      var dims = [];
      var assessmentData =
        api.unwrapResponse(await api.getAssessmentProfile(optionalReadOpts)) ||
        {};
      dims = _buildRadarDimensionsFromAssessment(assessmentData);

      if (!dims.length) {
        try {
          var radarResult = await api.getRadarData(
            RADAR_SELF_SUBJECT,
            optionalReadOpts,
          );
          var radarData = api.unwrapResponse(radarResult) || {};
          var radarDims = _normalizeRadarDimensions(radarData);
          if (radarDims.length && _hasPositiveRadarSignal(radarDims)) {
            dims = radarDims;
          }
        } catch (_) {}
      }

      if (dims.length === 0) {
        this.setData({ radarLoading: false, radarError: false });
        return;
      }

      var viewModel = _buildRadarViewModel(dims);
      var signature = _buildRadarSignature(dims);

      this.setData({
        radarDimensions: dims,
        strongCount: viewModel.strongCount,
        normalCount: viewModel.normalCount,
        weakCount: viewModel.weakCount,
        observedCount: viewModel.observedCount,
        avgScore: viewModel.avgScore,
        dimList: viewModel.dimList,
        radarLoading: false,
      });

      this._radarSignature = signature;
      this._ensureRadarRendered(dims, signature);
    } catch (e) {
      try {
        var fallbackDims = [];
        try {
          var radarFallback = await api.getRadarData(
            RADAR_SELF_SUBJECT,
            optionalReadOpts,
          );
          var radarFallbackData = api.unwrapResponse(radarFallback) || {};
          var radarDims = _normalizeRadarDimensions(radarFallbackData);
          if (radarDims.length && _hasPositiveRadarSignal(radarDims)) {
            fallbackDims = radarDims;
          }
        } catch (_) {}
        if (!fallbackDims.length) {
          this.setData({ radarLoading: false, radarError: true });
          return;
        }
        var fallbackViewModel = _buildRadarViewModel(fallbackDims);
        var signature = _buildRadarSignature(fallbackDims);
        this.setData({
          radarDimensions: fallbackDims,
          strongCount: fallbackViewModel.strongCount,
          normalCount: fallbackViewModel.normalCount,
          weakCount: fallbackViewModel.weakCount,
          observedCount: fallbackViewModel.observedCount,
          avgScore: fallbackViewModel.avgScore,
          dimList: fallbackViewModel.dimList,
          radarLoading: false,
          radarError: false,
        });
        this._radarSignature = signature;
        this._ensureRadarRendered(fallbackDims, signature);
      } catch (_) {
        // 雷达数据加载失败，通过 radarError 状态展示
        this.setData({ radarLoading: false, radarError: true });
      }
    }
  },

  // ── 加载掌握度数据（unified payload 不可用时的兜底）────
  async _loadMastery(snapshot) {
    if (snapshot) return;
    var optionalReadOpts = { suppressAuthRedirect: true };
    try {
      var data =
        api.unwrapResponse(await api.getMasteryDashboard(optionalReadOpts)) ||
        {};
      var groups = (data.groups || []).map(function (group) {
        var chapters = (group.chapters || []).map(function (chapter) {
          var mastery = Math.round(
            _asLearningBrainNumber(
              chapter.mastery,
              _asLearningBrainNumber(chapter.score, 0),
            ),
          );
          return {
            name: _displayChapterName(chapter.name || ""),
            mastery: mastery,
            color: chapter.color || "",
          };
        });
        return {
          name: group.name || "",
          avgMastery: Math.round(group.avg_mastery || 0),
          avgLabel: Math.round(group.avg_mastery || 0) + "%",
          avgClass: group.avg_class || group.class_name || "",
          chapters: chapters,
        };
      });

      var hotspots = (data.hotspots || []).map(function (item) {
        var mastery = Math.round(
          _asLearningBrainNumber(
            item.mastery,
            _asLearningBrainNumber(item.score, 0),
          ),
        );
        return {
          name: _displayChapterName(item.name || ""),
          mastery: mastery,
          rateText: mastery + "%",
        };
      });

      var overallPayload = _asLearningBrainObject(data.overall_mastery);
      var hasOverall =
        _hasExplicitNumericValue(data.overall_mastery) ||
        _hasExplicitNumericValue(overallPayload.score);
      var overall = Math.round(
        _asLearningBrainNumber(
          overallPayload.score,
          _asLearningBrainNumber(data.overall_mastery, 0),
        ),
      );
      var masteryScoreClass =
        overallPayload.class_name || overallPayload.status || "";
      var reviewSummary = data.review_summary || {
        total_due: 0,
        overdue_count: 0,
      };
      var knowledgeSummary =
        data.knowledge_summary || data.knowledgeSummary || {};

      if (!groups.length && !hasOverall) {
        var fallbackData =
          api.unwrapResponse(
            await api.getAssessmentProfile(optionalReadOpts),
          ) || {};
        var cm = fallbackData.chapter_mastery || {};
        var observedChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = _displayChapterName(
            (typeof v === "object" ? v.name : k) || k,
          );
          var mastery = _asLearningBrainNumber(
            typeof v === "object" ? v.mastery : v,
            0,
          );
          var item = {
            name: name,
            mastery: mastery,
            color: typeof v === "object" ? v.color || "" : "",
          };
          observedChapters.push(item);
        });

        groups = [];
        if (observedChapters.length)
          groups.push({
            name: "历史观测",
            avgMastery: 0,
            avgClass: "",
            chapters: observedChapters,
          });
        // 设计权威铁律「前端不算分/不算掌握度」:降级路径不再用章节均值
        // 客户端合成组均分与总体掌握——没有后端 read model 就诚实展示"—"。
        groups.forEach(function (g) {
          g.avgMastery = 0;
          g.avgLabel = "—";
          g.avgClass = "";
        });
        overall = null;
        masteryScoreClass = "";
        hotspots = [];
        reviewSummary = { total_due: 0, overdue_count: 0 };
        knowledgeSummary = {};
      }

      this.setData({
        overallMastery: overall == null ? 0 : overall,
        overallMasteryKnown: overall != null,
        masteryScoreClass: masteryScoreClass,
        masteryGroups: groups,
        hotspots: hotspots,
        knowledgeSummary: knowledgeSummary,
        textbookChapters:
          knowledgeSummary.textbook_chapters ||
          knowledgeSummary.textbookChapters ||
          [],
        reviewSummary: reviewSummary,
        masteryLoading: false,
      });
    } catch (e) {
      // 掌握度数据加载失败，通过 masteryError 状态展示
      this.setData({ masteryLoading: false, masteryError: true });
    }
  },

  _syncExperienceSections() {
    var hasMastery = this.data.masteryGroups && this.data.masteryGroups.length;
    var diagnosticScore =
      hasMastery || !this.data.radarDimensions.length
        ? this.data.overallMastery
        : this.data.avgScore || 0;
    var sharedInput = {
      masteryGroups: this.data.masteryGroups,
      hotspots: this.data.hotspots,
      dimList: this.data.dimList,
      dueTodayCount: this.data.dueTodayCount,
      dueTodayKnown: this.data.dueTodayKnown,
      dueTodayState: this.data.dueTodayState,
      reviewSummary: this.data.reviewSummary,
      todayDone: this.data.todayDone,
      dailyTarget: this.data.dailyTarget,
      streakDays: this.data.streakDays,
      focusHint: this.data.focusHint,
    };
    var progressFeedback = _normalizeProgressFeedback(
      this.data.homeProgressFeedback,
    );
    var homeBattlePlan = _normalizeBattlePlan(this.data.homeStudyPlan);
    var prescriptionBattlePlan = _buildBattlePlanFromPrescription(this.data);
    var shouldUsePrescriptionPlan =
      prescriptionBattlePlan &&
      (!homeBattlePlan ||
        String(this.data.prescriptionStatus || "") === "active");
    var battlePlan = (shouldUsePrescriptionPlan
      ? prescriptionBattlePlan
      : homeBattlePlan) || {
      focusTopic: "",
      priorityTask: "",
      studyMethod: "",
      timeBudget: "",
      coachNote: "",
    };

    this.setData({
      diagnosticScore: diagnosticScore,
      battlePlan: battlePlan,
      trainingExecutionAction: _buildTrainingExecutionAction({
        battlePlan: battlePlan,
        prescriptionStatus: this.data.prescriptionStatus,
        prescriptionTopic: this.data.prescriptionTopic,
        prescriptionCtaLabel: this.data.prescriptionCtaLabel,
        prescriptionEvidenceCount: this.data.prescriptionEvidenceCount,
        assessmentEnabled: this.data.assessmentEnabled,
        nextActionTitle: this.data.learningNextAction.title,
        focusHint: this.data.focusHint,
        assessmentTrainingAction: this.data.assessmentTrainingAction,
      }),
      progressSummary:
        (progressFeedback && progressFeedback.summary) ||
        _buildProgressSummary(sharedInput),
      progressInsight:
        (progressFeedback && progressFeedback.insight) ||
        _buildProgressInsight(sharedInput),
      progressCards:
        (progressFeedback &&
        progressFeedback.cards &&
        progressFeedback.cards.length
          ? progressFeedback.cards
          : null) || _buildProgressCards(sharedInput),
      progressMilestones:
        (progressFeedback &&
        progressFeedback.milestones &&
        progressFeedback.milestones.length
          ? progressFeedback.milestones
          : null) || _buildProgressMilestones(sharedInput),
    });
  },

  // ── 重试（统一走 unified report 入口，不再单独命中旧接口）────
  retryRadar() {
    this._radarImageSignature = "";
    this._radarSignature = "";
    this._radarRenderPending = false;
    this._radarRenderSeq += 1;
    this.setData({ radarError: false, radarLoading: true, radarImage: "" });
    this._loadReportPage();
  },

  retryMastery() {
    this.setData({ masteryError: false, masteryLoading: true });
    this._loadReportPage();
  },

  // ── Canvas 2D 绘制雷达图 ──────────────────────────
  _ensureRadarRendered(dims, signature) {
    signature = signature || _buildRadarSignature(dims);
    if (this.data.reportDetailView !== "map") return;
    if (!this._canvasReady) return;
    if (!Array.isArray(dims) || dims.length === 0) return;
    if (this._radarRenderPending) return;
    if (this.data.radarImage && this._radarImageSignature === signature) return;
    this._drawRadar(dims, signature);
  },

  _drawRadar(dims, signature) {
    signature = signature || _buildRadarSignature(dims);
    var renderSeq = ++this._radarRenderSeq;
    this._radarRenderPending = true;
    const query = wx.createSelectorQuery().in(this);
    query
      .select("#radarCanvas")
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          if (renderSeq === this._radarRenderSeq) {
            this._radarRenderPending = false;
          }
          return;
        }
        if (renderSeq !== this._radarRenderSeq) return;

        const canvas = res[0].node;
        const ctx = canvas.getContext("2d");
        const dpr = helpers.getWindowInfo().pixelRatio || 2;
        const width = res[0].width;
        const height = res[0].height;

        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        const cx = width / 2;
        const cy = height / 2;
        const r = Math.min(cx, cy) - 24;
        const n = dims.length;
        const values = dims.map((d) => d.value || 0);
        const labels = dims.map((d) => {
          const name = d.name || "";
          return name.length > 5 ? name.slice(0, 5) + "…" : name;
        });
        const palette = this.data.isDark
          ? {
              grid: "rgba(255,255,255,0.12)",
              axis: "rgba(255,255,255,0.08)",
              fill: "rgba(99,102,241,0.18)",
              line: "rgba(129,140,248,0.78)",
              point: "rgba(129,140,248,0.95)",
              label: "rgba(255,255,255,0.72)",
            }
          : {
              grid: "rgba(51,65,85,0.18)",
              axis: "rgba(51,65,85,0.12)",
              fill: "rgba(47,107,255,0.14)",
              line: "rgba(37,99,235,0.76)",
              point: "rgba(37,99,235,0.92)",
              label: "rgba(15,23,42,0.76)",
            };

        ctx.clearRect(0, 0, width, height);

        // 网格（4 层同心多边形）
        for (let ring = 1; ring <= 4; ring++) {
          ctx.beginPath();
          const rr = (r * ring) / 4;
          for (let i = 0; i <= n; i++) {
            const angle = (Math.PI * 2 * (i % n)) / n - Math.PI / 2;
            const x = cx + rr * Math.cos(angle);
            const y = cy + rr * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.closePath();
          ctx.strokeStyle = palette.grid;
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        // 轴线
        for (let i = 0; i < n; i++) {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.lineTo(cx + r * Math.cos(angle), cy + r * Math.sin(angle));
          ctx.strokeStyle = palette.axis;
          ctx.stroke();
        }

        // 数据多边形
        ctx.beginPath();
        for (let i = 0; i <= n; i++) {
          const idx = i % n;
          const angle = (Math.PI * 2 * idx) / n - Math.PI / 2;
          const v = values[idx] * r;
          const x = cx + v * Math.cos(angle);
          const y = cy + v * Math.sin(angle);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fillStyle = palette.fill;
        ctx.fill();
        ctx.strokeStyle = palette.line;
        ctx.lineWidth = 2;
        ctx.stroke();

        // 数据点 + 标签
        const labelOffset = r + 14;
        ctx.font = "10px -apple-system, sans-serif";
        for (let i = 0; i < n; i++) {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const v = values[i] * r;
          const x = cx + v * Math.cos(angle);
          const y = cy + v * Math.sin(angle);

          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fillStyle = palette.point;
          ctx.fill();

          const cosA = Math.cos(angle);
          const sinA = Math.sin(angle);
          let lx = cx + labelOffset * cosA;
          let ly = cy + labelOffset * sinA;

          // 根据角度动态对齐
          if (cosA > 0.3) ctx.textAlign = "left";
          else if (cosA < -0.3) ctx.textAlign = "right";
          else ctx.textAlign = "center";

          if (sinA < -0.3) ctx.textBaseline = "bottom";
          else if (sinA > 0.3) ctx.textBaseline = "top";
          else ctx.textBaseline = "middle";

          // 防止标签溢出画布边界
          const pad = 2;
          const tw = ctx.measureText
            ? ctx.measureText(labels[i]).width
            : labels[i].length * 10;
          if (ctx.textAlign === "left" && lx + tw > width - pad) {
            lx = width - pad - tw;
          } else if (ctx.textAlign === "right" && lx - tw < pad) {
            lx = pad + tw;
          }
          if (ly < pad + 10) ly = pad + 10;
          if (ly > height - pad) ly = height - pad;

          ctx.fillStyle = palette.label;
          ctx.fillText(labels[i], lx, ly);
        }

        // 仅在 canvas 完成本次绘制后导出一次图片，避免靠定时器猜测时机
        wx.nextTick(() => {
          if (renderSeq !== this._radarRenderSeq) return;
          wx.canvasToTempFilePath({
            canvas: canvas,
            success: (result) => {
              if (renderSeq !== this._radarRenderSeq) return;
              this._radarImageSignature = signature;
              this.setData({ radarImage: result.tempFilePath });
            },
            fail: () => {},
            complete: () => {
              if (renderSeq === this._radarRenderSeq) {
                this._radarRenderPending = false;
              }
            },
          });
        });
      });
  },

  // ── 学情内训练安排：练习中心还未完成体验打磨，先不跨页跳转 ─────
  goPractice() {
    helpers.vibrate("light");
    this._setReportDetailView("training");
  },

  executeTrainingAction() {
    var action = this.data.trainingExecutionAction || {};
    helpers.vibrate("light");
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    if (action.type === "assessment") {
      if (!flags.ensureFeatureEnabled("assessment")) return;
      wx.navigateTo({ url: route.assessment() });
      return;
    }
    var query = String(action.query || "").trim();
    if (!query) {
      query = "请根据我的学情处方开始今天的定向训练，先出第一组题。";
    }
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.setPendingChatIntent(
      query,
      "AUTO",
      action.promptIntent || null,
      action.followupQuestionContext || null,
    );
    wx.reLaunch({ url: route.chat() });
  },

  _trackLearningNoteBehavior(eventName, options) {
    var opts = options || {};
    if (!surfaceTelemetry || !surfaceTelemetry.trackProductBehavior) return;
    surfaceTelemetry.trackProductBehavior(eventName, {
      module: "learning_report",
      section: opts.section || "note_assets",
      action: opts.action || "view",
      objectType: opts.objectType || "notebook_card",
      objectId: opts.objectId || "",
      entrySource: opts.entrySource || "learning_report",
      result: opts.result || "",
      errorCode: opts.errorCode || "",
    });
  },

  async saveAttemptNotebookCard(event) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card || !api.saveNotebookCard) {
      wx.showToast({ title: "这条记录暂不能存卡片", icon: "none", duration: 1600 });
      return;
    }
    try {
      this._trackLearningNoteBehavior("note_card_suggested", {
        action: "suggest",
        objectId: String(card.key || ""),
      });
      var saved = await api.saveNotebookCard(_notebookCardPayloadFromAttempt(card));
      var noteId = String(
        (saved && saved.note_id) ||
          (saved && saved.card && saved.card.note_id) ||
          card.key ||
          "",
      );
      this._trackLearningNoteBehavior("note_card_saved", {
        action: "save_note",
        objectId: noteId,
        result: "success",
      });
      wx.showToast({ title: "已保存学习卡", icon: "success", duration: 1400 });
    } catch (_err) {
      this._trackLearningNoteBehavior("note_card_rejected", {
        action: "reject",
        objectId: String(card.key || ""),
        result: "failed",
        errorCode: "save_failed",
      });
      wx.showToast({ title: "保存失败，请稍后重试", icon: "none", duration: 1800 });
    }
  },

  startAttemptProbe(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card) return;
    this._trackLearningNoteBehavior("probe_requested_from_note", {
      action: card.attemptRef ? "start_retest" : "start_probe",
      objectId: String(card.key || ""),
    });
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.setPendingChatIntent(
      "请围绕这次批改暴露的问题，出一道同类题让我重新作答。",
      "AUTO",
      {
        source: "note_asset",
        attempt_ref: String(card.attemptRef || ""),
        subject_id: String(card.subjectId || ""),
      },
      null,
    );
    wx.reLaunch({ url: route.chat() });
  },

  startNoteAssetAction(event) {
    var noteId =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.noteid
        : "";
    var asset = (this.data.noteAssets || []).find(function (item) {
      return item.noteId === noteId;
    });
    if (!asset) return;
    this._trackLearningNoteBehavior("note_action_started", {
      action: asset.action && asset.action.type === "reanswer" ? "start_retest" : "start_probe",
      objectId: noteId,
    });
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.setPendingChatIntent(
      "请根据这张学习卡片安排一道复测题，先出题，不要直接给答案。",
      "AUTO",
      {
        source: "note_asset",
        note_id: noteId,
        attempt_ref: String(asset.action && asset.action.attemptRef || ""),
      },
      null,
    );
    wx.reLaunch({ url: route.chat() });
  },

  challengeDiagnosis(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningDiagnosisCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card) return;
    if (surfaceTelemetry && surfaceTelemetry.trackProductBehavior) {
      surfaceTelemetry.trackProductBehavior("learning_action_started", {
        module: "learning_report",
        section: "why",
        action: "start_retest",
        objectType: "diagnosis",
        objectId: String(card.key || ""),
        entrySource: "learner_challenge",
        result: "probe_requested",
      });
    }
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.setPendingChatIntent(
      "我觉得这个学情判断可能不准确。请围绕“" +
        String(card.title || card.meta || "当前薄弱点") +
        "”给我一题复测，先出题，不要直接给答案。",
      "AUTO",
      {
        source: "learning_report",
        reason: "learner_challenge_mastery",
        diagnosis_key: String(card.key || ""),
        evidence_refs: card.evidenceRefs || [],
      },
      null,
    );
    wx.reLaunch({ url: route.chat() });
  },

  async openAttemptDetail(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card) return;
    var cacheKey =
      "learning_attempt_detail_preview:" +
      String(card.key || Date.now()).replace(/[^a-zA-Z0-9:_-]/g, "_");
    if (auth.writeOwnerStorage)
      auth.writeOwnerStorage(cacheKey, { card: card, savedAt: Date.now() });
    if (typeof wx !== "undefined" && typeof wx.navigateTo === "function") {
      var params = ["cacheKey=" + encodeURIComponent(cacheKey)];
      if (card.attemptRef)
        params.push("attemptRef=" + encodeURIComponent(card.attemptRef));
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/attempt-detail/attempt-detail?" +
          params.join("&"),
      });
    }
  },

  async toggleMistakeBookmark(event) {
    if (!auth.isLoggedIn()) {
      this._requireLogin();
      return;
    }
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (
      !card ||
      !card.attemptRef ||
      !card.subjectId ||
      !api.saveMistakeBookItem
    ) {
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({
          title: "这条作答暂不能收藏",
          icon: "none",
          duration: 1800,
        });
      }
      return;
    }
    if (card.isBookmarked) {
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({ title: "已在云端错题集", icon: "none", duration: 1600 });
      }
      return;
    }
    try {
      await api.saveMistakeBookItem(_mistakeBookPayloadFromCard(card));
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({
          title: "已收藏到云端错题集",
          icon: "success",
          duration: 1600,
        });
      }
    } catch (_err) {
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({
          title: "收藏失败，请稍后重试",
          icon: "none",
          duration: 1800,
        });
      }
    }
  },
});
