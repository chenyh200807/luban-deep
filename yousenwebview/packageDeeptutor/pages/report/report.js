// pages/report/report.js — 学情页：诊断 + AI作战方案 + 进步反馈

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");
const flags = require("../../utils/flags");
const reportViewModel = require("../../utils/learning-report-view-model");

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

function _displayLevelName(value) {
  var key = String(value || "").trim();
  return LEVEL_NAMES[key] || key || "";
}

function _displayChapterName(value) {
  var text = String(value || "").trim();
  if (/^1A\d{6}$/i.test(text)) return "知识点 " + text.toUpperCase();
  return text || "未归类能力";
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
    return {
      name: _displayChapterName(
        (typeof item === "object" ? item.name : key) || key,
      ),
      value: (Number.isFinite(mastery) ? mastery : 0) / 100,
    };
  });
}

function _chapterMasteryFromRadar(dimensions) {
  var mastery = {};
  (Array.isArray(dimensions) ? dimensions : []).forEach(function (item) {
    var name = _displayChapterName(
      item && (item.name || item.label || item.key),
    );
    var value = Number(item && item.value);
    mastery[name] = {
      name: name,
      mastery: Math.round((Number.isFinite(value) ? value : 0) * 100),
    };
  });
  return mastery;
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

function _learningBrainErrorLabel(errorCode) {
  var code = String(errorCode || "")
    .trim()
    .toUpperCase();
  if (!code) return "";
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
  return "错因";
}

function _learningBrainConceptLabel(code, withCode) {
  var text = String(code || "")
    .trim()
    .toUpperCase();
  if (!text) return "";
  var original = String(code || "").trim();
  var topic = original.match(/我想练习(.+?)相关的题目/);
  if (topic && topic[1]) return topic[1].trim();
  return withCode ? "知识点" : "知识点";
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
  gradingResults.forEach(function (result, index) {
    var signal = _asLearningBrainObject(result.next_training_signal);
    var concept = signal.concept || signal.concept_id || "";
    var focus = signal.focus || signal.training_focus || signal.mode || "";
    if (!concept && !focus) return;
    training.push({
      key: "grading-" + index,
      title: _humanizeLearningBrainText(focus || "下一步训练"),
      meta:
        _learningBrainObjectLabel(concept, "concept") ||
        _humanizeLearningBrainText(signal.mode || ""),
    });
  });
  if (!training.length)
    graphEdges.concat(chainEdges).forEach(function (edge, index) {
      if (
        edge.edge_type !== "error_points_to_training" &&
        edge.edge_type !== "training_uses_question" &&
        edge.edge_type !== "training_improved_error" &&
        edge.edge_type !== "training_not_improved_error"
      ) {
        return;
      }
      var from = _asLearningBrainObject(edge.from);
      var to = _asLearningBrainObject(edge.to);
      training.push({
        key: "edge-training-" + index,
        title:
          edge.display_title ||
          _learningBrainObjectLabel(to.id || to.type || "", to.type || "") ||
          "下一步训练",
        meta:
          edge.display_path ||
          edge.display_meta ||
          _learningBrainObjectLabel(
            from.id || from.type || "",
            from.type || "",
          ) ||
          _learningBrainEdgeLabel(edge.edge_type),
      });
    });
  if (!training.length) {
    weakPoints.slice(0, 3).forEach(function (item, index) {
      var weak = _asLearningBrainObject(item);
      var concept = weak.concept_id || "";
      var error = weak.error_code || "";
      if (!concept && !error) return;
      training.push({
        key: "weak-training-" + index,
        title: "围绕薄弱点做变式训练",
        meta: [
          _learningBrainObjectLabel(concept, "concept"),
          _learningBrainObjectLabel(error, "error"),
        ]
          .filter(Boolean)
          .join("；"),
      });
    });
  }

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

function _attemptDetailText(card) {
  if (!card) return "";
  var parts = [];
  if (card.timeLabel) parts.push(card.timeLabel);
  if (card.questionText) parts.push("题目：" + card.questionText);
  if (card.answerLine) parts.push(card.answerLine);
  if (card.diagnosisDetail) parts.push("错因：" + card.diagnosisDetail);
  if (card.explanation) parts.push("解析：" + card.explanation);
  return parts.join("\n\n");
}

function _buildRadarViewModel(dims) {
  var strong = 0;
  var normal = 0;
  var weak = 0;
  (dims || []).forEach(function (d) {
    var pct = Math.round((d.value || 0) * 100);
    if (pct >= 70) strong++;
    else if (pct >= 40) normal++;
    else weak++;
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
      return {
        rank: index + 1,
        name: d.name,
        pct: pct,
        cls: pct >= 70 ? "strong" : pct >= 40 ? "normal" : "weak",
        color: pct >= 70 ? "#34d399" : pct >= 40 ? "#fbbf24" : "#f87171",
      };
    });
  return {
    strongCount: strong,
    normalCount: normal,
    weakCount: weak,
    avgScore: avg,
    dimList: dimList,
  };
}

function _pickPrimaryTopic(groups, hotspots, dimList, focusHint) {
  var candidates = [];
  (hotspots || []).forEach(function (item) {
    if (item && item.name) candidates.push(item.name);
  });
  (groups || []).forEach(function (group) {
    (group && group.chapters ? group.chapters : []).forEach(function (chapter) {
      if (chapter && chapter.name) candidates.push(chapter.name);
    });
  });
  (dimList || []).forEach(function (item) {
    if (item && item.name) candidates.push(item.name);
  });

  if (focusHint) {
    var matched = candidates.find(function (name) {
      return focusHint.indexOf(name) >= 0;
    });
    if (matched) return matched;
  }

  var weakGroup = (groups || []).find(function (group) {
    return (
      group &&
      group.name === "需要加强" &&
      Array.isArray(group.chapters) &&
      group.chapters.length
    );
  });
  if (weakGroup && weakGroup.chapters[0] && weakGroup.chapters[0].name) {
    return weakGroup.chapters[0].name;
  }
  if (hotspots && hotspots[0] && hotspots[0].name) {
    return hotspots[0].name;
  }
  if (dimList && dimList[0] && dimList[0].name) {
    return dimList[0].name;
  }
  return "";
}

function _buildBattlePlanModel(input) {
  var data = input || {};
  var topic = _pickPrimaryTopic(
    data.masteryGroups,
    data.hotspots,
    data.dimList,
    data.focusHint,
  );
  var dueToday = Number(data.dueTodayCount) || 0;
  var totalDue = Number((data.reviewSummary || {}).total_due) || 0;
  var overdueCount = Number((data.reviewSummary || {}).overdue_count) || 0;
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var remainingTarget = Math.max(dailyTarget - todayDone, 0);
  var questionCount = Math.max(Math.min(remainingTarget || 5, 5), 3);
  var priorityTask = "";
  var studyMethod = "";
  var timeBudget = "";
  var coachNote = "";

  if (totalDue > 0 && topic) {
    priorityTask =
      "先清理 " +
      Math.min(totalDue, 3) +
      " 个待复习点，再围绕“" +
      topic +
      "”做 " +
      questionCount +
      " 题巩固";
  } else if (topic) {
    priorityTask =
      "先围绕“" +
      topic +
      "”速练 " +
      questionCount +
      " 题，尽快把薄弱点拉回主线";
  } else if (remainingTarget > 0) {
    priorityTask =
      "先完成今天剩余的 " + remainingTarget + " 题目标，保持学习节奏";
  } else {
    priorityTask = "先完成一轮短练习，系统会继续更新你的薄弱点判断";
  }

  if (topic) {
    studyMethod = "先看“" + topic + "”考点梳理，再做真题强化，最后回看错题";
  } else if (dueToday > 0) {
    studyMethod = "先复习再练题，把今天待回看的内容优先清掉";
  } else {
    studyMethod = "先做短练，再按错题回看考点，保持诊断持续更新";
  }

  if (totalDue > 0 || overdueCount > 0) {
    timeBudget = "约 15 分钟，优先清理复习任务";
  } else if (remainingTarget > 0) {
    timeBudget = "约 12 分钟，完成今日目标后再加练一轮";
  } else {
    timeBudget = "约 10 分钟，保持今天的学习节奏";
  }

  if (data.focusHint) {
    coachNote = data.focusHint;
  } else if (topic) {
    coachNote = "当前最值得优先补强的章节是“" + topic + "”";
  } else if ((data.hotspots || []).length) {
    coachNote = "系统检测到热点失分项，建议优先处理高频问题";
  } else {
    coachNote = "先保持练习频率，系统会继续为你收敛更准确的作战建议";
  }

  return {
    focusTopic: topic || "今天先稳住基础节奏",
    priorityTask: priorityTask,
    studyMethod: studyMethod,
    timeBudget: timeBudget,
    coachNote: coachNote,
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

  return {
    focusTopic: focusTopic || "今天先稳住基础节奏",
    priorityTask: priorityTask,
    studyMethod: studyMethod,
    timeBudget: timeBudget,
    coachNote: coachNote,
  };
}

function _buildProgressCards(input) {
  var data = input || {};
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var streakDays = Number(data.streakDays) || 0;
  var dueToday = Number(data.dueTodayCount) || 0;
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
      value: String(dueToday),
      detail: dueToday > 0 ? "建议今天优先清理" : "复习节奏稳定",
      toneClass: dueToday > 0 ? "tone-warn" : "tone-good",
    },
    {
      label: "热点关注",
      value: String(hotspotCount),
      detail: hotspotCount > 0 ? "优先看高频失分点" : "当前无明显热点",
      toneClass: hotspotCount > 0 ? "tone-warn" : "tone-good",
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

function _isLearningReportPayload(value) {
  var authority = value && value.authority;
  return (
    value &&
    typeof value === "object" &&
    Number(value.schema_version) === 1 &&
    authority &&
    authority.read_model === "learning-report-read-model" &&
    value.overview &&
    typeof value.overview === "object" &&
    value.freshness &&
    typeof value.freshness === "object" &&
    value.learning_brain &&
    typeof value.learning_brain === "object"
  );
}

function _snapshotValue(snapshot, key) {
  var value = snapshot && snapshot[key];
  return _hasSnapshotData(value) ? value : null;
}

function _unwrapSnapshotItem(raw) {
  var value = api.unwrapResponse(raw);
  return _isLearningReportPayload(value) ? value : null;
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
};

function _buildDegradedHint(sources) {
  var list = (Array.isArray(sources) ? sources : []).filter(Boolean);
  if (!list.length) return "";
  var labels = list.map(function (name) {
    return _DEGRADED_SOURCE_LABELS[name] || name;
  });
  return "部分数据降级：" + labels.join("、");
}

function _learningReportDegradedSources(report) {
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

function _reportOptionalRead(promise, timeoutMs) {
  var settled = false;
  return new Promise(function (resolve) {
    var timer = setTimeout(function () {
      if (settled) return;
      settled = true;
      resolve(null);
    }, timeoutMs || 3500);
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

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,

    // WXML 不支持 HTML 实体，用 data 绑定传入 Unicode 字符
    warnIcon: "\u26A0\uFE0F",
    radarIcon: "\uD83D\uDCE1",

    isDark: true,

    // 加载状态
    radarLoading: true,
    masteryLoading: true,
    learningBrainLoading: true,
    radarError: false,
    masteryError: false,
    learningBrainError: false,
    learningBrainEmpty: false,

    // 雷达图数据
    radarDimensions: [],
    strongCount: 0,
    normalCount: 0,
    weakCount: 0,
    avgScore: 0,

    // 维度详情列表（按 value 升序 = 薄弱优先）
    dimList: [],

    // 雷达图渲染后的图片（解决 canvas 不跟随滚动的问题）
    radarImage: "",

    // 掌握度数据
    overallMastery: 0,
    masteryGroups: [],
    hotspots: [],
    reviewSummary: { total_due: 0, overdue_count: 0 },
    todayDone: 0,
    dailyTarget: 0,
    streakDays: 0,
    dueTodayCount: 0,
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
    learningDiagnosisCards: [],
    learningTrainingLoops: [],
    learningNextAction: { title: "", subtitle: "", cta: "开始训练" },
    learningBrainGraphStats: {
      eventCount: 0,
      createdClaimCount: 0,
      typedGraphEdgeCount: 0,
      projectionSubject: "",
      projectionSubjectLabel: "",
    },
    battlePlan: {
      focusTopic: "系统正在生成今日主攻",
      priorityTask: "学情同步后，这里会给你最优先的一步动作",
      studyMethod: "系统会结合薄弱点、热点和今日任务，自动给出学习顺序",
      timeBudget: "约 10 分钟",
      coachNote: "完成更多练习后，AI 作战建议会更准确",
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
  },

  _radarRenderSeq: 0,
  _radarRenderPending: false,
  _radarImageSignature: "",
  _radarSignature: "",
  _reportSnapshot: null,

  onLoad() {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
    });
  },

  onShow() {
    var workspaceBack = runtime.getWorkspaceBack(route.report());
    if (!flags.ensureFeatureEnabled("report")) return;
    this.setData({ isDark: helpers.isDark() });
    this.setData({
      navBackLabel: workspaceBack ? workspaceBack.label : "对话",
      assessmentEnabled: flags.isFeatureEnabled("assessment"),
    });
    helpers.syncTabBar(this, 2, {
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    runtime.checkAuth(() => {
      this.setData({
        radarLoading: true,
        masteryLoading: true,
        learningBrainLoading: true,
        radarError: false,
        masteryError: false,
        learningBrainError: false,
        learningBrainEmpty: false,
      });
      this._loadReportPage();
    });
  },

  async _loadReportSnapshot() {
    var optionalReadOpts = { suppressAuthRedirect: true };
    optionalReadOpts.schemaVersion = 2;
    const report = _unwrapSnapshotItem(
      await _reportOptionalRead(api.getLearningReport(100, optionalReadOpts)),
    );
    if (!report) {
      // 5xx / network failure / payload contract 断裂 → 返回 null 让 _loadReportPage 走显式 fallback
      return null;
    }
    const overview = report.overview || {};
    const mastery = report.mastery || {};
    const weakNodes = (
      (report.learning_brain || {}).weak_points ||
      [] ||
      []
    ).map(function (item) {
      return {
        name: item.display_title || item.claim || item.concept_id || "薄弱点",
        mastery: 0,
      };
    });
    return {
      report: report,
      degraded:
        Boolean(report.degraded) ||
        _learningReportDegradedSources(report).length > 0,
      degradedSources: _learningReportDegradedSources(report),
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
        chapter_mastery: _chapterMasteryFromRadar(
          report.radar_dimensions || [],
        ),
        diagnostic_feedback: {
          learner_profile: { study_tip: overview.study_tip || "" },
        },
      },
      mastery: mastery,
      learningBrain: report.learning_brain || {},
      learnerFacing: report.learner_facing || {},
    };
  },

  async _loadReportPage() {
    var snapshot = await this._loadReportSnapshot();
    if (snapshot) {
      this._reportSnapshot = snapshot;
      this._hydrateFromUnifiedReport(snapshot);
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

  _hydrateFromUnifiedReport(snapshot) {
    var report = (snapshot && snapshot.report) || {};
    var overview = report.overview || {};
    var home = (snapshot && snapshot.home) || {};
    var sharedReport = reportViewModel.buildLearningReportViewModel(report);
    var sharedPageData = reportViewModel.toReportPageData(sharedReport);
    this.setData(Object.assign({}, sharedPageData, {
      todayDone: overview.today_done || 0,
      dailyTarget: overview.daily_target || 0,
      streakDays: overview.streak_days || 0,
      dueTodayCount: overview.due_today_count || 0,
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
      degradedHint: snapshot.degraded
        ? _buildDegradedHint(snapshot.degradedSources)
        : "",
      degradedSources: snapshot.degraded
        ? snapshot.degradedSources.slice()
        : [],
      reportFallbackActive: false,
    }));
    if (sharedPageData.radarDimensions.length) {
      this._radarSignature = _buildRadarSignature(sharedPageData.radarDimensions);
      this._ensureRadarRendered(sharedPageData.radarDimensions, this._radarSignature);
    }
  },

  onReady() {
    this._canvasReady = true;
    this._ensureRadarRendered(
      this.data.radarDimensions,
      this._radarSignature || _buildRadarSignature(this.data.radarDimensions),
    );
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

  goAssessment() {
    if (!flags.ensureFeatureEnabled("assessment")) return;
    helpers.vibrate("light");
    wx.navigateTo({ url: route.assessment() });
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
        dueTodayCount: (home.review || {}).due_today || 0,
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
          var mastery = Math.round(chapter.mastery || 0);
          return {
            name: _displayChapterName(chapter.name || ""),
            mastery: mastery,
            color:
              mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
          };
        });
        chapters.sort(function (a, b) {
          return a.mastery - b.mastery;
        });
        return {
          name: group.name || "",
          avgMastery: Math.round(group.avg_mastery || 0),
          chapters: chapters,
        };
      });

      var hotspots = (data.hotspots || []).map(function (item) {
        var mastery = Math.round(item.mastery || 0);
        return {
          name: _displayChapterName(item.name || ""),
          mastery: mastery,
          rateText: mastery + "%",
        };
      });

      var overall = Math.round(data.overall_mastery || 0);
      var reviewSummary = data.review_summary || {
        total_due: 0,
        overdue_count: 0,
      };

      if (!groups.length && !overall) {
        var fallbackData =
          api.unwrapResponse(
            await api.getAssessmentProfile(optionalReadOpts),
          ) || {};
        var cm = fallbackData.chapter_mastery || {};
        var weakChapters = [];
        var normalChapters = [];
        var strongChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = _displayChapterName(
            (typeof v === "object" ? v.name : k) || k,
          );
          var mastery = (typeof v === "object" ? v.mastery : v) || 0;
          var item = {
            name: name,
            mastery: mastery,
            color:
              mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
          };
          if (mastery >= 70) strongChapters.push(item);
          else if (mastery >= 40) normalChapters.push(item);
          else weakChapters.push(item);
        });

        groups = [];
        if (weakChapters.length)
          groups.push({
            name: "需要加强",
            avgMastery: 0,
            chapters: weakChapters,
          });
        if (normalChapters.length)
          groups.push({
            name: "基本掌握",
            avgMastery: 0,
            chapters: normalChapters,
          });
        if (strongChapters.length)
          groups.push({
            name: "掌握较好",
            avgMastery: 0,
            chapters: strongChapters,
          });
        groups.forEach(function (g) {
          if (!g.chapters.length) return;
          g.chapters.sort(function (a, b) {
            return a.mastery - b.mastery;
          });
          g.avgMastery = Math.round(
            g.chapters.reduce(function (s, c) {
              return s + c.mastery;
            }, 0) / g.chapters.length,
          );
        });

        var allMastery = Object.keys(cm).map(function (k) {
          var v = cm[k];
          return (typeof v === "object" ? v.mastery : v) || 0;
        });
        overall = allMastery.length
          ? Math.round(
              allMastery.reduce(function (a, b) {
                return a + b;
              }, 0) / allMastery.length,
            )
          : 0;
        hotspots = [];
        reviewSummary = { total_due: 0, overdue_count: 0 };
      }

      this.setData({
        overallMastery: overall,
        masteryGroups: groups,
        hotspots: hotspots,
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
      reviewSummary: this.data.reviewSummary,
      todayDone: this.data.todayDone,
      dailyTarget: this.data.dailyTarget,
      streakDays: this.data.streakDays,
      focusHint: this.data.focusHint,
    };
    var progressFeedback = _normalizeProgressFeedback(
      this.data.homeProgressFeedback,
    );

    this.setData({
      diagnosticScore: diagnosticScore,
      battlePlan:
        _normalizeBattlePlan(this.data.homeStudyPlan) ||
        _buildBattlePlanModel(sharedInput),
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

  // ── 跳转练习 ─────────────────────────────────────
  goPractice() {
    wx.navigateTo({ url: route.practice() });
  },

  openAttemptDetail(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card) return;
    var content = _attemptDetailText(card);
    if (typeof wx !== "undefined" && typeof wx.showModal === "function") {
      wx.showModal({
        title: card.resultLabel
          ? card.resultLabel + "｜" + card.concept
          : card.concept,
        content: content || "这次作答暂无可展开内容。",
        showCancel: false,
        confirmText: "知道了",
      });
    }
  },

  // 错题集 authority 收敛到云端 `learner_mistake_book_items`（见
  // docs/plan/2026-05-21-luban-learning-report-world-class-optimization-plan.md §-1.2 #3 / §Task 3）。
  // 云端 endpoint 未上线前，yousen 端不持有第二套本地 truth source；点击只提示待接入，
  // 不写 wx storage、不改任何展示状态。
  toggleMistakeBookmark() {
    if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
      wx.showToast({
        title: "云端错题集即将上线",
        icon: "none",
        duration: 1800,
      });
    }
  },
});
