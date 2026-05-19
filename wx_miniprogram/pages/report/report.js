// pages/report/report.js — 学习报告：能力雷达 + 摸底报告

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

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

function displayLevelName(value) {
  var key = String(value || "").trim();
  return LEVEL_NAMES[key] || key || "";
}

function displayChapterName(value) {
  var text = String(value || "").trim();
  if (/^1A\d{6}$/i.test(text)) return "综合能力";
  return text || "综合能力";
}

function buildRadarDimensionsFromAssessment(data) {
  var mastery = (data && data.chapter_mastery) || {};
  return Object.keys(mastery).map(function (key) {
    var item = mastery[key];
    var score = Number(typeof item === "object" ? item.mastery : item);
    return {
      name: displayChapterName((typeof item === "object" ? item.name : key) || key),
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
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function normalizeEventIds(ids) {
  return asList(ids)
    .map(function (id) {
      var eventId = compactId(id);
      return eventId ? "证据 " + eventId : "";
    })
    .filter(Boolean)
    .slice(0, 3);
}

function learningBrainNodeId(edge, side) {
  var node = asObject(edge && edge[side]);
  return String(node.id || node.type || "").trim();
}

function learningBrainLevelLabel(level) {
  var key = String(level || "").trim();
  return LEARNING_BRAIN_LEVEL_LABELS[key] || key || LEARNING_BRAIN_LEVEL_LABELS.unclassified;
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
  var code = String(errorCode || "").trim().toUpperCase();
  return code ? "错因" : "";
}

function learningBrainConceptLabel(code, withCode) {
  var text = String(code || "").trim().toUpperCase();
  if (!text) return "";
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
  return "采分点：" + (part && /^r\d+$/i.test(part) ? part.toUpperCase() : compactId(part || text));
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
    if (/^(concept|error|question|rubric_item|submission|next_training|training|weak_point)$/.test(prefix)) {
      type = prefix;
      id = id.slice(prefix.length + 1);
    }
  }
  if (type === "concept" || /^1A\d{6}$/i.test(id)) {
    return "知识点：" + learningBrainConceptLabel(id, true);
  }
  if (type === "error" || /^1A\d{6}:E\d{2}$/i.test(id) || /^E\d{2}$/i.test(id)) {
    var parts = id.split(":");
    var concept = /^1A\d{6}$/i.test(parts[0]) ? learningBrainConceptLabel(parts[0], false) : "";
    var error = learningBrainErrorLabel(parts[parts.length - 1]);
    return "错因：" + [concept, error].filter(Boolean).join(" / ");
  }
  if (type === "question") return learningBrainQuestionLabel(id);
  if (type === "rubric_item") return learningBrainRubricLabel(id);
  if (type === "next_training" || type === "training") return learningBrainTrainingLabel(id);
  if (type === "submission") return "作答记录：" + compactId(id);
  if (type === "weak_point") return "薄弱点";
  return "学习对象：" + compactId(id || type);
}

function humanizeLearningBrainText(value) {
  var text = String(value || "").trim();
  if (!text) return "";
  text = text.replace(/concept:/g, "知识点：");
  text = text.replace(/rubric_item:/g, "采分点：");
  text = text.replace(/question:/g, "案例题：");
  text = text.replace(/error:/g, "错因：");
  text = text.replace(/1A\d{6}/gi, function (code) {
    return learningBrainConceptLabel(code, false);
  });
  text = text.replace(/\bE\d{2}\b/gi, function (code) {
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
  ].filter(Boolean).join(" → ");
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
  return outcomes.map(function (edge, index) {
    var trainingId = learningBrainNodeId(edge, "from");
    var useEdge = usesByTraining[trainingId] || {};
    var questionId = String(edge.question_id || learningBrainNodeId(useEdge, "to") || "").trim();
    var errorId = learningBrainNodeId(edge, "to");
    var improved = edge.edge_type === "training_improved_error";
    return {
      key: "chain-" + index,
      tone: improved ? "improved" : "not-improved",
      title: edge.display_meta || learningBrainObjectLabel(errorId, "error") || "错因：待确认",
      training: edge.display_path || learningBrainObjectLabel(trainingId, "next_training") || "训练建议：围绕薄弱点做变式训练",
      question: useEdge.display_path || (questionId ? learningBrainQuestionLabel(questionId) : ""),
      outcome: learningBrainOutcomeText(edge.edge_type),
      eventId: compactId(edge.reason_edge_event_id || edge.evidence_event_id || ""),
      eventLabel: edge.reason_edge_event_id || edge.evidence_event_id ? "证据 " + compactId(edge.reason_edge_event_id || edge.evidence_event_id || "") : "",
    };
  }).slice(0, 4);
}

function normalizeLearningBrainPayload(raw) {
  var body = api.unwrapResponse(raw) || {};
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
      title: truth.display_title || humanizeLearningBrainText(truth.current_truth || truth.object_key || ""),
      meta: truth.display_meta || truth.display_label || "",
      level: level || "unclassified",
      levelLabel: truth.evidence_level_label || learningBrainLevelLabel(level || "unclassified"),
      eventIds: normalizeEventIds(truth.supporting_event_ids),
    });
  });

  if (!truths.length) Object.keys(compiled).forEach(function (key) {
    var item = asObject(compiled[key]);
    var level = item.evidence_level || "";
    var currentTruth = item.current_truth || item.claim || item.object_id || "";
    if (!currentTruth && !level) return;
    truths.push({
      key: key,
      title: humanizeLearningBrainText(currentTruth || key),
      meta: learningBrainObjectLabel(key, item.object_type || ""),
      level: level || "unclassified",
      levelLabel: learningBrainLevelLabel(level || "unclassified"),
      eventIds: normalizeEventIds(item.supporting_event_ids),
    });
  });

  if (!truths.length) weakPoints.forEach(function (item, index) {
    var weak = asObject(item);
    var concept = weak.concept_id || weak.concept || "";
    var error = weak.error_code || weak.error || "";
    var level = weak.evidence_level || "";
    var title = weak.current_truth || [concept, error].filter(Boolean).join(" / ");
    if (!title && !level) return;
    truths.push({
      key: "weak-" + index,
      title: humanizeLearningBrainText(title || "薄弱点"),
      meta: [learningBrainObjectLabel(concept, "concept"), learningBrainObjectLabel(error, "error")].filter(Boolean).join("；") || "薄弱点",
      level: level || "unclassified",
      levelLabel: learningBrainLevelLabel(level || "unclassified"),
      eventIds: normalizeEventIds(weak.supporting_event_ids),
    });
  });

  var evidence = asList(visible.evidence_flow).map(function (item, index) {
    var flow = asObject(item);
    var eventId = compactId(flow.event_id || "");
    return {
      key: flow.event_id || "visible-edge-" + index,
      type: flow.display_title || flow.display_label || learningBrainEdgeLabel(flow.edge_type),
      path: flow.display_path || flow.path || flow.display_meta || "",
      eventId: eventId,
      eventLabel: eventId ? "证据 " + eventId : "",
    };
  }).filter(function (item) {
    return item.type || item.path || item.eventId;
  });
  if (!evidence.length) evidence = graphEdges.concat(chainEdges).map(function (edge, index) {
    var eventId = compactId(edge.evidence_event_id || edge.reason_edge_event_id || edge.event_id || "");
    return {
      key: "edge-" + index,
      type: edge.display_title || edge.display_label || learningBrainEdgeLabel(edge.edge_type),
      path: edge.display_path || learningBrainEdgePath(edge),
      eventId: eventId,
      eventLabel: eventId ? "证据 " + eventId : "",
    };
  }).filter(function (item) {
    return item.type || item.path || item.eventId;
  });

  var training = asList(visible.next_training).map(function (item, index) {
    var plan = asObject(item);
    return {
      key: plan.concept_id || plan.error_code || "visible-training-" + index,
      title: plan.display_title || humanizeLearningBrainText(plan.claim || "下一步训练"),
      meta: plan.display_meta || plan.display_label || "",
    };
  }).filter(function (item) {
    return item.title || item.meta;
  });
  gradingResults.forEach(function (result, index) {
    var signal = asObject(result.next_training_signal);
    var concept = signal.concept || signal.concept_id || "";
    var focus = signal.focus || signal.training_focus || signal.mode || "";
    if (!concept && !focus) return;
    training.push({
      key: "grading-" + index,
      title: humanizeLearningBrainText(focus || "下一步训练"),
      meta: learningBrainObjectLabel(concept, "concept") || humanizeLearningBrainText(signal.mode || ""),
    });
  });
  if (!training.length) graphEdges.concat(chainEdges).forEach(function (edge, index) {
    if (
      edge.edge_type !== "error_points_to_training" &&
      edge.edge_type !== "training_uses_question" &&
      edge.edge_type !== "training_improved_error" &&
      edge.edge_type !== "training_not_improved_error" &&
      edge.edge_type !== "weak_point_drives_training"
    ) {
      return;
    }
    var from = asObject(edge.from);
    var to = asObject(edge.to);
    training.push({
      key: "edge-training-" + index,
      title: edge.display_title || learningBrainObjectLabel(to.id || to.type || "", to.type || "") || "下一步训练",
      meta: edge.display_path || edge.display_meta || learningBrainObjectLabel(from.id || from.type || "", from.type || "") || learningBrainEdgeLabel(edge.edge_type),
    });
  });
  if (!training.length) {
    weakPoints.slice(0, 3).forEach(function (item, index) {
      var weak = asObject(item);
      var concept = weak.concept_id || "";
      var error = weak.error_code || "";
      if (!concept && !error) return;
      training.push({
        key: "weak-training-" + index,
        title: "围绕薄弱点做变式训练",
        meta: [learningBrainObjectLabel(concept, "concept"), learningBrainObjectLabel(error, "error")].filter(Boolean).join("；"),
      });
    });
  }

  var eventCount = Number(projection.event_count || synthesisRun.input_event_count || 0);
  var createdClaimCount = Number(projection.created_claim_count || synthesisRun.created_claim_count || 0);
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
      createdClaimCount: Number.isFinite(createdClaimCount) ? createdClaimCount : 0,
      typedGraphEdgeCount: Number.isFinite(typedGraphEdgeCount) ? typedGraphEdgeCount : 0,
      projectionSubject: projection.projection_subject || projection.subject || "",
      projectionSubjectLabel: learningBrainSubjectLabel(projection.projection_subject || projection.subject || ""),
    },
  };
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
    learnerLevel: "",
    studyTip: "",
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
      this._loadOverview();
      this._loadLearningBrain();
      this._loadRadar();
      this._loadMastery();
    });
  },

  onReady() {
    this._canvasReady = true;
    if (this.data.radarDimensions.length > 0) {
      this._drawRadar(this.data.radarDimensions);
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
        dueTodayCount: ((home.review || {}).due_today || 0),
        weakNodeCount: weakNodes.length,
        focusHint: ((home.today || {}).hint || ""),
        learnerLevel: displayLevelName(assessment.level || ""),
        studyTip: learnerProfile.study_tip || "",
      });
    } catch (_) {}
  },

  toggleMastery() {
    helpers.vibrate("light");
    this.setData({ masteryExpanded: !this.data.masteryExpanded });
  },

  async _loadLearningBrain() {
    try {
      var normalized = normalizeLearningBrainPayload(await api.getLearningBrainProjection());
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
        var pct = Math.round((d.value || 0) * 100);
        if (pct >= 70) strong++;
        else if (pct >= 40) normal++;
        else weak++;
      });

      var avg = Math.round(
        (dims.reduce(function (s, d) {
          return s + (d.value || 0);
        }, 0) /
          dims.length) *
          100,
      );

      var sorted = dims.slice().sort(function (a, b) {
        return (a.value || 0) - (b.value || 0);
      });
      var dimList = sorted.map(function (d, i) {
        var pct = Math.round((d.value || 0) * 100);
        return {
          rank: i + 1,
          name: d.name,
          pct: pct,
          cls: pct >= 70 ? "strong" : pct >= 40 ? "normal" : "weak",
          color: pct >= 70 ? "#34d399" : pct >= 40 ? "#fbbf24" : "#f87171",
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

      if (this._canvasReady) {
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
          chapters: (group.chapters || []).map(function (chapter) {
            var mastery = Math.round(chapter.mastery || 0);
            return {
              name: displayChapterName(chapter.name || ""),
              mastery: mastery,
              color:
                mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
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

      var overall = Math.round(data.overall_mastery || 0);
      var reviewSummary = data.review_summary || { total_due: 0, overdue_count: 0 };

      if (!groups.length && !overall) {
        var fallback = await api.getAssessmentProfile();
        var fallbackData = api.unwrapResponse(fallback) || {};
        var cm = fallbackData.chapter_mastery || {};
        var weakChapters = [];
        var normalChapters = [];
        var strongChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = displayChapterName((typeof v === "object" ? v.name : k) || k);
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
        if (weakChapters.length) groups.push({ name: "需要加强", avgMastery: 0, chapters: weakChapters });
        if (normalChapters.length) groups.push({ name: "基本掌握", avgMastery: 0, chapters: normalChapters });
        if (strongChapters.length) groups.push({ name: "掌握较好", avgMastery: 0, chapters: strongChapters });
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
        overviewScore: this.data.radarDimensions.length ? this.data.avgScore : overall,
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
    this._loadRadar();
  },

  retryMastery() {
    this.setData({ masteryError: false, masteryLoading: true });
    this._loadMastery();
  },

  retryLearningBrain() {
    this.setData({
      learningBrainError: false,
      learningBrainLoading: true,
      learningBrainEmpty: false,
    });
    this._loadLearningBrain();
  },

  // ── Canvas 2D 绘制雷达图 ──────────────────────────
  _drawRadar(dims) {
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
});
