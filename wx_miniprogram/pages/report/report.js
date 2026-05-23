// pages/report/report.js — 学习报告：能力雷达 + 摸底报告

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const reportViewModel = require("../../utils/learning-report-view-model");

const taxonomy = require("../../utils/taxonomy");
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

function displayLevelName(value) {
  var key = String(value || "").trim();
  return LEVEL_NAMES[key] || key || "";
}

function displayChapterName(value) {
  return taxonomy.displayChapterName(value, "未归类能力");
}

function buildRadarDimensionsFromAssessment(data) {
  var mastery = (data && data.chapter_mastery) || {};
  return Object.keys(mastery).map(function (key) {
    var item = mastery[key];
    var score = Number(typeof item === "object" ? item.mastery : item);
    return {
      name: displayChapterName(
        (typeof item === "object" ? item.name : key) || key,
      ),
      value: (Number.isFinite(score) ? score : 0) / 100,
    };
  });
}

function hasPositiveRadarSignal(dims) {
  return (dims || []).some(function (item) {
    return Number(item && item.value) > 0;
  });
}

function normalizeRadarDimensions(radarData) {
  return ((radarData && radarData.dimensions) || []).map(function (item) {
    var score = Number(item.score);
    var value =
      typeof item.value === "number"
        ? item.value
        : Number.isFinite(score)
          ? score / 100
          : 0;
    return {
      name: displayChapterName(item.label || item.name || item.key || ""),
      value: value || 0,
    };
  });
}

function compactId(value) {
  var text = String(value || "").trim();
  if (!text) return "";
  return text.length > 18 ? text.slice(0, 8) + "..." + text.slice(-4) : text;
}

function asList(value) {
  if (Array.isArray(value)) return value;
  return [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function asNumber(value, fallback) {
  var num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function mistakeBookPayloadFromCard(card) {
  var item = asObject(card);
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

function normalizeEventIds(ids) {
  return asList(ids)
    .map(function (_id, index) {
      return learningBrainEvidenceLabel(index);
    })
    .filter(Boolean)
    .slice(0, 3);
}

function learningBrainEventLabels(labels, ids) {
  var readable = asList(labels).filter(Boolean).slice(0, 3);
  return readable.length ? readable : normalizeEventIds(ids);
}

function learningBrainEvidenceLabel(index) {
  if (index === 0) return "最近一次批改";
  if (index === 1) return "上一次批改";
  return "第 " + (index + 1) + " 条批改证据";
}

function learningBrainNodeId(edge, side) {
  var node = asObject(edge && edge[side]);
  return String(node.id || node.type || "").trim();
}

function learningBrainLevelLabel(level) {
  var key = String(level || "").trim();
  return (
    LEARNING_BRAIN_LEVEL_LABELS[key] ||
    key ||
    LEARNING_BRAIN_LEVEL_LABELS.unclassified
  );
}

function learningBrainSubjectLabel(subject) {
  var key = String(subject || "").trim();
  return LEARNING_BRAIN_SUBJECT_LABELS[key] || key || "";
}

function learningBrainEdgeLabel(edgeType) {
  var key = String(edgeType || "").trim();
  return key ? "学习关系" : "";
}

function learningBrainErrorLabel(errorCode) {
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

function learningBrainConceptLabel(code, withCode) {
  var text = String(code || "")
    .trim()
    .toUpperCase();
  if (!text) return "";
  var original = String(code || "").trim();
  var topic = original.match(/我想练习(.+?)相关的题目/);
  if (topic && topic[1]) return topic[1].trim();
  return withCode ? "知识点" : "知识点";
}

function learningBrainQuestionLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  if (/wechat-harness-case-\d+/i.test(text)) {
    return "案例题：" + text.replace(/^wechat-harness-case-/i, "专项训练 ");
  }
  if (/^case[-_:]?\d+/i.test(text)) {
    return "案例题：" + text.replace(/^case[-_:]?/i, "第 ") + " 题";
  }
  return "案例题：" + compactId(text);
}

function learningBrainRubricLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  var part = text.split(":").pop();
  return (
    "采分点：" +
    (part && /^r\d+$/i.test(part)
      ? part.toUpperCase()
      : compactId(part || text))
  );
}

function learningBrainTrainingLabel(id) {
  var text = String(id || "").trim();
  if (!text) return "";
  var parts = text.split(":");
  var focus = parts.length > 2 ? parts.slice(2).join(" / ") : "";
  if (focus) return "训练建议：" + focus;
  if (parts[0] && /^1A\d{6}$/i.test(parts[0])) {
    return "训练建议：" + learningBrainConceptLabel(parts[0], false);
  }
  return "训练建议：" + compactId(text);
}

function learningBrainObjectLabel(rawId, rawType) {
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
    return "知识点：" + learningBrainConceptLabel(id, true);
  }
  if (
    type === "error" ||
    /^1A\d{6}:[EM]\d{2}$/i.test(id) ||
    /^[EM]\d{2}$/i.test(id)
  ) {
    var parts = id.split(":");
    var concept = /^1A\d{6}$/i.test(parts[0])
      ? learningBrainConceptLabel(parts[0], false)
      : "";
    var error = learningBrainErrorLabel(parts[parts.length - 1]);
    return "错因：" + [concept, error].filter(Boolean).join(" / ");
  }
  if (type === "question") return learningBrainQuestionLabel(id);
  if (type === "rubric_item") return learningBrainRubricLabel(id);
  if (type === "next_training" || type === "training")
    return learningBrainTrainingLabel(id);
  if (type === "submission") return "作答记录：" + compactId(id);
  if (type === "weak_point") return "薄弱点";
  return "学习对象：" + compactId(id || type);
}

function humanizeLearningBrainText(value) {
  var text = String(value || "").trim();
  if (!text) return "";
  text = text.replace(/我想练习(.+?)相关的题目\s*请严格围绕.*?当前学习锚点出题/g, "$1");
  text = text.replace(/concept:/g, "知识点：");
  text = text.replace(/rubric_item:/g, "采分点：");
  text = text.replace(/question:/g, "案例题：");
  text = text.replace(/error:/g, "错因：");
  text = text.replace(/\bpractice\s*\/\s*/gi, "训练建议：");
  text = text.replace(/\s*->\s*/g, " → ");
  text = text.replace(/\bq[-_:]?(\d+)\b/gi, "第 $1 题");
  text = text.replace(/1A\d{6}/gi, function (code) {
    return learningBrainConceptLabel(code, false);
  });
  text = text.replace(/\b[EM]\d{2}\b/gi, function (code) {
    return learningBrainErrorLabel(code);
  });
  text = text.replace(/\s*上出现\s*/g, "出现");
  text = text.replace(/\s*相关错因观察/g, "相关错因");
  text = text.replace(/\s*错因观察/g, "错因");
  text = text.replace(/\s{2,}/g, " ");
  return text;
}

function learningBrainEdgePath(edge) {
  if (edge && edge.display_path) return String(edge.display_path);
  var from = asObject(edge.from);
  var to = asObject(edge.to);
  return [
    learningBrainObjectLabel(from.id || from.type || "", from.type || ""),
    learningBrainObjectLabel(to.id || to.type || "", to.type || ""),
  ]
    .filter(Boolean)
    .join(" → ");
}

function learningBrainOutcomeText(edgeType) {
  if (edgeType === "training_improved_error") return "本次训练结果：已改善";
  if (edgeType === "training_not_improved_error") return "本次训练结果：未改善";
  return "已推荐训练题";
}

function buildLearningBrainTrainingChains(graphChain) {
  var uses = asList(graphChain.training_uses_question);
  var outcomes = asList(graphChain.training_improved_error).concat(
    asList(graphChain.training_not_improved_error),
  );
  var usesByTraining = {};
  uses.forEach(function (edge) {
    var trainingId = learningBrainNodeId(edge, "from");
    if (trainingId && !usesByTraining[trainingId]) {
      usesByTraining[trainingId] = edge;
    }
  });
  return outcomes
    .map(function (edge, index) {
      var trainingId = learningBrainNodeId(edge, "from");
      var useEdge = usesByTraining[trainingId] || {};
      var questionId = String(
        edge.question_id || learningBrainNodeId(useEdge, "to") || "",
      ).trim();
      var errorId = learningBrainNodeId(edge, "to");
      var improved = edge.edge_type === "training_improved_error";
      return {
        key: "chain-" + index,
        tone: improved ? "improved" : "not-improved",
        title: humanizeLearningBrainText(
          edge.display_meta ||
            learningBrainObjectLabel(errorId, "error") ||
            "错因：待确认",
        ),
        training: humanizeLearningBrainText(
          edge.display_path ||
            learningBrainObjectLabel(trainingId, "next_training") ||
            "训练建议：围绕薄弱点做变式训练",
        ),
        question: humanizeLearningBrainText(
          useEdge.display_path ||
            (questionId ? learningBrainQuestionLabel(questionId) : ""),
        ),
        outcome: learningBrainOutcomeText(edge.edge_type),
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

function normalizeLearnerFacingPayload(body, learnerFacing) {
  var freshness = asObject(body.freshness);
  var summary = asObject(learnerFacing.summary);
  var nextAction = asObject(learnerFacing.next_action);
  var attempts = asList(learnerFacing.recent_attempts)
    .map(function (item, index) {
      var attempt = asObject(item);
      return {
        key: attempt.key || "attempt-" + index,
        timeLabel: attempt.time_label || "",
        title: attempt.title || "一次练习",
        concept: attempt.concept || "",
        resultLabel: attempt.result_label || "",
        tone: attempt.tone || "",
        answerLine: attempt.answer_line || "",
        diagnosis: attempt.diagnosis || "",
        diagnosisDetail: attempt.diagnosis_detail || "",
        evidenceLabel: attempt.evidence_label || "",
      };
    })
    .filter(function (item) {
      return item.title || item.answerLine || item.diagnosis;
    });
  var diagnoses = asList(learnerFacing.diagnoses)
    .map(function (item, index) {
      var diagnosis = asObject(item);
      return {
        key: diagnosis.key || "diagnosis-" + index,
        levelLabel: diagnosis.level_label || "",
        title: diagnosis.title || "",
        meta: diagnosis.meta || "",
        detail: diagnosis.detail || "",
        action: diagnosis.action || "",
        count: Number(diagnosis.count || 0),
      };
    })
    .filter(function (item) {
      return item.title || item.detail;
    });
  var evidence = asList(learnerFacing.evidence_timeline)
    .map(function (item, index) {
      var evidenceItem = asObject(item);
      return {
        key: evidenceItem.key || "timeline-" + index,
        timeLabel: evidenceItem.time_label || "",
        title: evidenceItem.title || "",
        line: evidenceItem.line || "",
        tone: evidenceItem.tone || "",
      };
    })
    .filter(function (item) {
      return item.title || item.line;
    });
  var chains = asList(learnerFacing.training_loops)
    .map(function (item, index) {
      var chain = asObject(item);
      return {
        key: chain.key || "loop-" + index,
        tone: chain.tone || "",
        title: chain.title || "",
        from: chain.from || "",
        training: chain.training || "",
        outcome: chain.outcome || "",
      };
    })
    .filter(function (item) {
      return item.title || item.outcome;
    });
  var training = nextAction.title
    ? [
        {
          key: "next-action",
          title: nextAction.title,
          meta: nextAction.subtitle || "",
          cta: nextAction.cta || "开始训练",
          estimatedMinutes: nextAction.estimated_minutes || 0,
        },
      ]
    : [];
  return {
    learnerFacing: true,
    summary: {
      title: summary.title || "今日学习复盘",
      headline: summary.headline || "",
      primaryFocus: summary.primary_focus || "",
      todayDone: Number(summary.today_done || 0),
      recentThreeDone: Number(summary.recent_three_done || 0),
      weakCount: Number(summary.weak_count || 0),
    },
    attempts: attempts.slice(0, 5),
    diagnoses: diagnoses.slice(0, 4),
    truths: diagnoses.slice(0, 4).map(function (item) {
      return {
        key: item.key,
        title: item.title,
        meta: [item.meta, item.detail].filter(Boolean).join("｜"),
        level: "learner-facing",
        levelLabel: item.levelLabel || "系统判断",
        eventIds: [],
      };
    }),
    evidence: evidence.slice(0, 6).map(function (item) {
      return {
        key: item.key,
        type: [item.timeLabel, item.title].filter(Boolean).join("｜"),
        path: item.line,
        eventLabel: "",
        tone: item.tone,
      };
    }),
    training: training,
    chains: chains.slice(0, 3),
    nextAction: training[0] || {},
    stats: {
      eventCount: Number(freshness.event_count || summary.recent_three_done || 0),
      createdClaimCount: diagnoses.length,
      typedGraphEdgeCount: 0,
      projectionSubject: "",
      projectionSubjectLabel: "学习复盘",
    },
  };
}

function normalizeLearningBrainPayload(raw) {
  var body = api.unwrapResponse(raw) || {};
  var learnerFacing = asObject(
    body.learner_facing ||
      asObject(body.learning_brain).learner_facing ||
      asObject(body.projection).learner_facing,
  );
  if (
    learnerFacing.summary ||
    asList(learnerFacing.recent_attempts).length ||
    asList(learnerFacing.diagnoses).length
  ) {
    return normalizeLearnerFacingPayload(body, learnerFacing);
  }
  var projection = asObject(body.projection || body.learning_brain || body);
  var compiled = asObject(projection.compiled_objects);
  var weakPoints = asList(projection.weak_points);
  var graph = asObject(projection.typed_graph);
  var graphEdges = asList(projection.typed_graph_edges || graph.edges);
  var graphChain = asObject(projection.graph_chain);
  var visible = asObject(projection.visible_sections);
  var chainEdges = asList(graphChain.training_uses_question)
    .concat(asList(graphChain.training_improved_error))
    .concat(asList(graphChain.training_not_improved_error));
  var trainingChains = buildLearningBrainTrainingChains(graphChain);
  var gradingResults = asList(projection.grading_results);
  var synthesisRun = asObject(projection.synthesis_run);
  var truths = [];

  asList(visible.current_truth).forEach(function (item, index) {
    var truth = asObject(item);
    var level = truth.evidence_level || "";
    truths.push({
      key: "truth-" + index,
      title: humanizeLearningBrainText(
        truth.display_title || truth.current_truth || truth.object_key || "",
      ),
      meta: humanizeLearningBrainText(
        truth.display_meta || truth.display_label || "",
      ),
      level: level || "unclassified",
      levelLabel:
        truth.evidence_level_label ||
        learningBrainLevelLabel(level || "unclassified"),
      eventIds: learningBrainEventLabels(
        truth.supporting_event_labels,
        truth.supporting_event_ids,
      ),
    });
  });

  if (!truths.length)
    Object.keys(compiled).forEach(function (key) {
      var item = asObject(compiled[key]);
      var level = item.evidence_level || "";
      var currentTruth =
        item.current_truth || item.claim || item.object_id || "";
      if (!currentTruth && !level) return;
      truths.push({
        key: key,
        title: humanizeLearningBrainText(currentTruth || key),
        meta: learningBrainObjectLabel(key, item.object_type || ""),
        level: level || "unclassified",
        levelLabel: learningBrainLevelLabel(level || "unclassified"),
        eventIds: learningBrainEventLabels(
          item.supporting_event_labels,
          item.supporting_event_ids,
        ),
      });
    });

  if (!truths.length)
    weakPoints.forEach(function (item, index) {
      var weak = asObject(item);
      var concept = weak.concept_id || weak.concept || "";
      var error = weak.error_code || weak.error || "";
      var level = weak.evidence_level || "";
      var title =
        weak.current_truth || [concept, error].filter(Boolean).join(" / ");
      if (!title && !level) return;
      truths.push({
        key: "weak-" + index,
        title: humanizeLearningBrainText(title || "薄弱点"),
        meta:
          [
            learningBrainObjectLabel(concept, "concept"),
            learningBrainObjectLabel(error, "error"),
          ]
            .filter(Boolean)
            .join("；") || "薄弱点",
        level: level || "unclassified",
        levelLabel: learningBrainLevelLabel(level || "unclassified"),
        eventIds: learningBrainEventLabels(
          weak.supporting_event_labels,
          weak.supporting_event_ids,
        ),
      });
    });

  var evidence = asList(visible.evidence_flow)
    .map(function (item, index) {
      var flow = asObject(item);
      var hasEvidence = !!(flow.event_label || flow.event_id);
      return {
        key: "visible-edge-" + index,
        type:
          humanizeLearningBrainText(flow.display_title) ||
          flow.display_label ||
          learningBrainEdgeLabel(flow.edge_type),
        path: humanizeLearningBrainText(
          flow.display_path || flow.path || flow.display_meta || "",
        ),
        eventId: "",
        eventLabel: flow.event_label || (hasEvidence ? learningBrainEvidenceLabel(index) : ""),
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
            humanizeLearningBrainText(edge.display_title) ||
            edge.display_label ||
            learningBrainEdgeLabel(edge.edge_type),
          path: humanizeLearningBrainText(edge.display_path || learningBrainEdgePath(edge)),
          eventId: "",
          eventLabel: hasEvidence ? learningBrainEvidenceLabel(index) : "",
        };
      })
      .filter(function (item) {
        return item.type || item.path || item.eventId;
      });

  var training = asList(visible.next_training)
    .map(function (item, index) {
      var plan = asObject(item);
      return {
        key: "visible-training-" + index,
        title: humanizeLearningBrainText(
          plan.display_title || plan.claim || "下一步训练",
        ),
        meta: humanizeLearningBrainText(plan.display_meta || plan.display_label || ""),
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
    learnerFacing: false,
    summary: {
      title: "学习事实复盘",
      headline: truths.length
        ? "系统已整理出学习事实，但缺少可还原的具体作答明细。"
        : "",
      primaryFocus: "",
      todayDone: 0,
      recentThreeDone: Number.isFinite(eventCount) ? eventCount : 0,
      weakCount: truths.length,
    },
    attempts: [],
    diagnoses: truths.slice(0, 4).map(function (item) {
      return {
        key: item.key,
        levelLabel: item.levelLabel,
        title: item.title,
        meta: item.meta,
        detail: item.meta,
        action: "围绕这个薄弱点做一组专项训练",
        count: 1,
      };
    }),
    nextAction: training[0] || {},
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
      projectionSubjectLabel: learningBrainSubjectLabel(
        projection.projection_subject || projection.subject || "",
      ),
    },
  };
}

function normalizeMasteryGroups(data) {
  var overallPayload = asObject(data.overall_mastery);
  var groups = asList(data.groups).map(function (group) {
    return {
      name: group.name || "",
      avgMastery: Math.round(group.avg_mastery || 0),
      avgClass: group.avg_class || group.class_name || "",
      chapters: asList(group.chapters).map(function (chapter) {
        var mastery = Math.round(chapter.mastery || 0);
        return {
          name: displayChapterName(chapter.name || ""),
          mastery: mastery,
          color: chapter.color || "",
        };
      }),
    };
  });
  var hotspots = asList(data.hotspots).map(function (item) {
    var mastery = Math.round(item.mastery || 0);
    return {
      name: displayChapterName(item.name || ""),
      mastery: mastery,
      rateText: mastery + "%",
    };
  });
  return {
    overall: Math.round(
      asNumber(overallPayload.score, asNumber(data.overall_mastery, 0)),
    ),
    overallClass: overallPayload.class_name || overallPayload.status || "",
    groups: groups,
    hotspots: hotspots,
    reviewSummary: data.review_summary || { total_due: 0, overdue_count: 0 },
  };
}

function normalizeRadarState(dims) {
  var normalized = asList(dims).map(function (item) {
    var value = Number(item.value || 0);
    return {
      name: displayChapterName(item.name || item.label || item.key || ""),
      value: Number.isFinite(value) ? value : 0,
      status: item.status || item.level || "",
      color: item.color || "",
    };
  });
  var strong = 0;
  var normal = 0;
  var weak = 0;
  normalized.forEach(function (d) {
    if (d.status === "strong" || d.status === "mastered") strong++;
    else if (d.status === "normal" || d.status === "developing") normal++;
    else if (d.status === "weak" || d.status === "needs_attention") weak++;
  });
  var avg = normalized.length
    ? Math.round(
        (normalized.reduce(function (sum, item) {
          return sum + (item.value || 0);
        }, 0) /
          normalized.length) *
          100,
      )
    : 0;
  var dimList = normalized.map(function (d, i) {
      var pct = Math.round((d.value || 0) * 100);
      return {
        rank: i + 1,
        name: d.name,
        pct: pct,
        cls: d.status || "",
        color: d.color || "",
      };
    });
  return {
    dims: normalized,
    strong: strong,
    normal: normal,
    weak: weak,
    avg: avg,
    dimList: dimList,
  };
}

function isLearningBrainEmpty(normalized) {
  return (
    normalized.truths.length === 0 &&
    normalized.evidence.length === 0 &&
    normalized.training.length === 0 &&
    normalized.chains.length === 0 &&
    !normalized.stats.eventCount &&
    !normalized.stats.createdClaimCount &&
    !normalized.stats.typedGraphEdgeCount
  );
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

function buildDegradedHint(sources) {
  var list = (Array.isArray(sources) ? sources : []).filter(Boolean);
  if (!list.length) return "";
  var labels = list.map(function (name) {
    return _DEGRADED_SOURCE_LABELS[name] || name;
  });
  return "部分数据降级：" + labels.join("、");
}

function isLearningReportPayload(body) {
  var authority = asObject(body && body.authority);
  var schemaVersion = Number(body && body.schema_version);
  return (
    body &&
    typeof body === "object" &&
    (schemaVersion === 1 || schemaVersion === 2) &&
    authority.read_model === "learning-report-read-model" &&
    body.overview &&
    typeof body.overview === "object" &&
    body.freshness &&
    typeof body.freshness === "object" &&
    body.learning_brain &&
    typeof body.learning_brain === "object"
  );
}

function learningReportDegradedSources(body) {
  var sources = Array.isArray(body && body.degraded_sources)
    ? body.degraded_sources.slice()
    : [];
  if (body && body.freshness && body.freshness.window_truncated) {
    sources.push("learning_report_window");
  }
  return sources.filter(function (item, index) {
    return item && sources.indexOf(item) === index;
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
    reportDetailView: "home",
    reportDetailTitle: REPORT_DETAIL_TITLES.home,
    reportScrollTop: 0,

    // Degraded UI（plan §Phase 2 / §测试矩阵 第 19 行）
    degradedHint: "",
    degradedSources: [],
    reportFallbackActive: false,

    // 加载状态
    radarLoading: true,
    masteryLoading: true,
    learningBrainLoading: true,
    masteryExpanded: false,
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
    overviewScore: 0,

    // 维度详情列表（按后端 projection 顺序展示）
    dimList: [],

    // 雷达图渲染后的图片（解决 canvas 不跟随滚动的问题）
    radarImage: "",

    // 掌握度数据
    overallMastery: 0,
    masteryScoreClass: "",
    masteryGroups: [],
    hotspots: [],
    reviewSummary: { total_due: 0, overdue_count: 0 },
    todayDone: 0,
    dailyTarget: 0,
    streakDays: 0,
    dueTodayCount: 0,
    weakNodeCount: 0,
    focusHint: "",
    learnerLevel: "",
    learnerStageTitle: "当前学习状态",
    masteryStatusLabel: "正在形成",
    studyTip: "",
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
    learningNextAction: { title: "", subtitle: "", cta: "开始训练" },
    learningBrainSummary: {},
    learningBrainAttempts: [],
    learningBrainDiagnoses: [],
    learningBrainNextAction: {},
    learningBrainTruths: [],
    learningBrainEvidence: [],
    learningBrainTraining: [],
    learningBrainChains: [],
    learningBrainGraphStats: {
      eventCount: 0,
      createdClaimCount: 0,
      typedGraphEdgeCount: 0,
      projectionSubject: "",
      projectionSubjectLabel: "",
    },
  },

  onLoad() {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
    });
  },

  onShow() {
    this.setData({ isDark: helpers.isDark() });
    helpers.syncTabBar(this, 2);
    const app = getApp();
    app.checkAuth(() => {
      this._loadLearningReport();
    });
  },

  onReady() {
    this._canvasReady = true;
    if (this.data.reportDetailView === "map" && this.data.radarDimensions.length > 0) {
      this._drawRadar(this.data.radarDimensions);
    }
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
    this._setReportDetailView(detail);
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
        if (this.data.radarDimensions.length) {
          this._drawRadar(this.data.radarDimensions);
        }
      });
    }
  },

  // ── 返回首页 ───────────────────────────────────────
  goHome() {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },

  goAssessment() {
    helpers.vibrate("light");
    wx.navigateTo({ url: "/pages/assessment/assessment" });
  },

  async _loadOverview() {
    try {
      const tasks = [
        api.getTodayProgress().catch(() => null),
        api.getHomeDashboard().catch(() => null),
        api.getAssessmentProfile().catch(() => null),
      ];

      const result = await Promise.all(tasks);
      const progress = api.unwrapResponse(result[0]) || {};
      const home = api.unwrapResponse(result[1]) || {};
      const assessment = api.unwrapResponse(result[2]) || {};

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
        learnerLevel: displayLevelName(assessment.level || ""),
        studyTip: learnerProfile.study_tip || "",
      });
    } catch (_) {}
  },

  async _loadLearningReport() {
    try {
      var raw = await api.getLearningReport(100, { schemaVersion: 2 });
      var body = api.unwrapResponse(raw) || {};
      if (!isLearningReportPayload(body)) {
        throw new Error("learning-report payload contract mismatch");
      }
      var sharedReport = reportViewModel.buildLearningReportViewModel(body);
      var sharedPageData = reportViewModel.toReportPageData(sharedReport);
      var degradedSources = learningReportDegradedSources(body);
      var degraded = Boolean(body.degraded) || degradedSources.length > 0;
      this.setData(Object.assign({}, sharedPageData, {
        radarLoading: false,
        radarError: false,
        masteryLoading: false,
        masteryError: false,
        learningBrainLoading: false,
        learningBrainError: false,
        degradedHint: degraded ? buildDegradedHint(degradedSources) : "",
        degradedSources: degraded ? degradedSources : [],
        reportFallbackActive: false,
      }));
      if (
        this._canvasReady &&
        this.data.reportDetailView === "map" &&
        sharedPageData.radarDimensions.length
      ) {
        this._drawRadar(sharedPageData.radarDimensions);
      }
    } catch (e) {
      // unified payload 不可用（5xx / payload contract 断裂 / 网络异常）→ 暴露 degraded fallback 标记
      this.setData({
        radarLoading: false,
        masteryLoading: false,
        learningBrainLoading: false,
        radarError: true,
        masteryError: true,
        learningBrainError: true,
        learningBrainEmpty: false,
        degradedHint: "学情接口暂时不可用，已显示基础数据",
        degradedSources: ["learning_report"],
        reportFallbackActive: true,
      });
    }
  },

  toggleMastery() {
    helpers.vibrate("light");
    this.setData({ masteryExpanded: !this.data.masteryExpanded });
  },

  async _loadLearningBrain() {
    try {
      var normalized = normalizeLearningBrainPayload(
        await api.getLearningBrainProjection(),
      );
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
        learningBrainSummary: normalized.summary || {},
        learningBrainAttempts: normalized.attempts || [],
        learningBrainDiagnoses: normalized.diagnoses || [],
        learningBrainNextAction: normalized.nextAction || {},
        learningBrainLoading: false,
        learningBrainError: false,
        learningBrainEmpty: isEmpty,
      });
    } catch (e) {
      this.setData({
        learningBrainLoading: false,
        learningBrainError: true,
        learningBrainEmpty: false,
      });
    }
  },

  // ── 加载学情数据（assessment profile 为唯一主 authority）────
  async _loadRadar() {
    try {
      var dims = [];
      var result = await api.getAssessmentProfile();
      var data = api.unwrapResponse(result) || {};
      dims = buildRadarDimensionsFromAssessment(data);

      if (!dims.length) {
        try {
          var radarResult = await api.getRadarData(RADAR_SELF_SUBJECT);
          var radarData = api.unwrapResponse(radarResult) || {};
          var radarDims = normalizeRadarDimensions(radarData);
          if (radarDims.length && hasPositiveRadarSignal(radarDims)) {
            dims = radarDims;
          }
        } catch (_) {}
      }

      if (dims.length === 0) {
        this.setData({ radarLoading: false });
        return;
      }

      var strong = 0,
        normal = 0,
        weak = 0;
      dims.forEach(function (d) {
        if (d.status === "strong" || d.status === "mastered") strong++;
        else if (d.status === "normal" || d.status === "developing") normal++;
        else if (d.status === "weak" || d.status === "needs_attention") weak++;
      });

      var avg = Math.round(
        (dims.reduce(function (s, d) {
          return s + (d.value || 0);
        }, 0) /
          dims.length) *
          100,
      );

      var dimList = dims.map(function (d, i) {
        var pct = Math.round((d.value || 0) * 100);
        return {
          rank: i + 1,
          name: d.name,
          pct: pct,
          cls: d.status || d.level || "",
          color: d.color || "",
        };
      });

      this.setData({
        radarDimensions: dims,
        strongCount: strong,
        normalCount: normal,
        weakCount: weak,
        avgScore: avg,
        overviewScore: avg,
        dimList: dimList,
        radarLoading: false,
      });

      if (this._canvasReady && this.data.reportDetailView === "map") {
        this._drawRadar(dims);
      }
    } catch (e) {
      // 雷达数据加载失败，通过 radarError 状态展示
      this.setData({ radarLoading: false, radarError: true });
    }
  },

  // ── 加载掌握度数据（也从 assessment profile 获取）────
  async _loadMastery() {
    try {
      var result = await api.getMasteryDashboard();
      var data = api.unwrapResponse(result) || {};
      var groups = (data.groups || []).map(function (group) {
        return {
          name: group.name || "",
          avgMastery: Math.round(group.avg_mastery || 0),
          avgClass: group.avg_class || group.class_name || "",
          chapters: (group.chapters || []).map(function (chapter) {
            var mastery = Math.round(chapter.mastery || 0);
            return {
              name: displayChapterName(chapter.name || ""),
              mastery: mastery,
              color: chapter.color || "",
            };
          }),
        };
      });

      var hotspots = (data.hotspots || []).map(function (item) {
        var mastery = Math.round(item.mastery || 0);
        return {
          name: displayChapterName(item.name || ""),
          mastery: mastery,
          rateText: mastery + "%",
        };
      });

      var overallPayload = asObject(data.overall_mastery);
      var overall = Math.round(
        asNumber(overallPayload.score, asNumber(data.overall_mastery, 0)),
      );
      var masteryScoreClass =
        overallPayload.class_name || overallPayload.status || "";
      var reviewSummary = data.review_summary || {
        total_due: 0,
        overdue_count: 0,
      };

      if (!groups.length && !overall) {
        var fallback = await api.getAssessmentProfile();
        var fallbackData = api.unwrapResponse(fallback) || {};
        var cm = fallbackData.chapter_mastery || {};
        var observedChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = displayChapterName(
            (typeof v === "object" ? v.name : k) || k,
          );
          var mastery = (typeof v === "object" ? v.mastery : v) || 0;
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
        groups.forEach(function (g) {
          if (!g.chapters.length) return;
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
        masteryScoreClass: masteryScoreClass,
        overviewScore: this.data.radarDimensions.length
          ? this.data.avgScore
          : overall,
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

  // ── 重试 ──────────────────────────────────────────
  retryRadar() {
    this.setData({ radarError: false, radarLoading: true, radarImage: "" });
    this._loadLearningReport();
  },

  retryMastery() {
    this.setData({ masteryError: false, masteryLoading: true });
    this._loadLearningReport();
  },

  retryLearningBrain() {
    this.setData({
      learningBrainError: false,
      learningBrainLoading: true,
      learningBrainEmpty: false,
    });
    this._loadLearningReport();
  },

  // ── Canvas 2D 绘制雷达图 ──────────────────────────
  _drawRadar(dims) {
    if (this.data.reportDetailView !== "map") return;
    const query = wx.createSelectorQuery().in(this);
    query
      .select("#radarCanvas")
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) return;

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

        // 转为图片，解决 canvas 不跟随 scroll-view 滚动的问题
        setTimeout(() => {
          wx.canvasToTempFilePath({
            canvas: canvas,
            success: (result) => {
              this.setData({ radarImage: result.tempFilePath });
            },
            fail: () => {},
          });
        }, 100);
      });
  },

  // ── 跳转练习 ─────────────────────────────────────
  goPractice() {
    wx.navigateTo({ url: "/pages/practice/practice" });
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
    var cacheKey = "learning_attempt_detail_preview:" + String(card.key || Date.now()).replace(/[^a-zA-Z0-9:_-]/g, "_");
    if (typeof wx !== "undefined" && typeof wx.setStorageSync === "function") {
      try {
        wx.setStorageSync(cacheKey, { card: card, savedAt: Date.now() });
      } catch (_err) {}
    }
    if (typeof wx !== "undefined" && typeof wx.navigateTo === "function") {
      var params = ["cacheKey=" + encodeURIComponent(cacheKey)];
      if (card.attemptRef) params.push("attemptRef=" + encodeURIComponent(card.attemptRef));
      wx.navigateTo({ url: "/pages/attempt-detail/attempt-detail?" + params.join("&") });
    }
  },

  async toggleMistakeBookmark(event) {
    var key =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.key
        : "";
    var card = (this.data.learningAttemptCards || []).find(function (item) {
      return item.key === key;
    });
    if (!card || !card.attemptRef || !card.subjectId || !api.saveMistakeBookItem) {
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({ title: "这条作答暂不能收藏", icon: "none", duration: 1800 });
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
      await api.saveMistakeBookItem(mistakeBookPayloadFromCard(card));
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({ title: "已收藏到云端错题集", icon: "success", duration: 1600 });
      }
      if (typeof this._loadLearningReport === "function") {
        this._loadLearningReport();
      }
    } catch (_err) {
      if (typeof wx !== "undefined" && typeof wx.showToast === "function") {
        wx.showToast({ title: "收藏失败，请稍后重试", icon: "none", duration: 1800 });
      }
    }
  },
});
