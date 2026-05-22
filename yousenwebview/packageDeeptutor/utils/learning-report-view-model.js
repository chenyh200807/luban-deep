function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asNumber(value, fallback) {
  var number = Number(value);
  return Number.isFinite(number) ? number : fallback || 0;
}

function levelName(value) {
  var key = String(value || "").trim();
  var names = {
    beginner: "入门",
    intermediate: "中级",
    advanced: "进阶",
    expert: "精通",
  };
  return names[key] || key || "";
}

function chapterName(value) {
  var text = String(value || "").trim();
  if (/^1A\d{6}$/i.test(text)) return "知识点 " + text.toUpperCase();
  return text || "未归类能力";
}

function normalizeRadar(dimensions) {
  var dims = asList(dimensions).map(function (item) {
    var source = asObject(item);
    var score = asNumber(source.score, NaN);
    var value =
      typeof source.value === "number"
        ? source.value
        : Number.isFinite(score)
          ? score / 100
          : 0;
    return {
      name: chapterName(source.label || source.name || source.key || ""),
      value: value || 0,
      score: Math.round(asNumber(source.score, asNumber(value, 0) * 100)),
      level: String(source.level || source.status || "observed"),
      rateText: String(source.rate_text || source.rateText || ""),
    };
  });
  var scores = dims.map(function (item) {
    return Math.round(asNumber(item.value, 0) * 100);
  });
  var strong = dims.filter(function (item) {
    return item.level === "strong" || item.level === "stable";
  }).length;
  var weak = dims.filter(function (item) {
    return ["weak", "unstable", "needs_revalidation"].indexOf(item.level) >= 0;
  }).length;
  var normal = Math.max(0, dims.length - strong - weak);
  var avg = scores.length
    ? Math.round(
        scores.reduce(function (sum, score) {
          return sum + score;
        }, 0) / scores.length,
      )
    : 0;
  return {
    dims: dims,
    strongCount: strong,
    normalCount: normal,
    weakCount: weak,
    avgScore: avg,
    dimList: dims.map(function (item) {
      var score = Math.round(asNumber(item.score, asNumber(item.value, 0) * 100));
      return {
        name: item.name,
        score: score,
        rateText: item.rateText || score + "%",
        level: item.level,
      };
    }),
  };
}

function normalizeMastery(source) {
  var mastery = asObject(source);
  var overall = mastery.overall_mastery;
  var overallPayload = asObject(overall);
  var overallConfidence = asNumber(overallPayload.confidence, 0);
  var overallStatus = String(overallPayload.status || "");
  var overallClass = String(overallPayload.class_name || overallPayload.className || "");
  if (overall && typeof overall === "object") overall = overall.score;
  var groups = asList(mastery.groups).map(function (group) {
    var item = asObject(group);
    var chapters = asList(item.chapters).map(function (chapter) {
      var c = asObject(chapter);
      var rate = Math.round(asNumber(c.mastery, asNumber(c.score, 0)));
      return {
        name: chapterName(c.name || ""),
        mastery: rate,
        color: String(c.color || ""),
      };
    });
    return {
      name: String(item.name || ""),
      avgMastery: Math.round(asNumber(item.avg_mastery, 0)),
      avgClass: String(item.avg_class || item.avgClass || ""),
      chapters: chapters,
    };
  });
  return {
    overall: Math.round(asNumber(overall, 0)),
    overallConfidence: overallConfidence,
    overallStatus: overallStatus,
    overallStatusLabel: masteryStatusLabel(overallStatus, overallConfidence),
    overallClass: overallClass,
    groups: groups,
    hotspots: asList(mastery.hotspots).map(function (hotspot) {
      var item = asObject(hotspot);
      var rate = Math.round(asNumber(item.mastery, asNumber(item.score, 0)));
      return {
        name: chapterName(item.name || ""),
        mastery: rate,
        rateText: rate + "%",
      };
    }),
    reviewSummary: asObject(mastery.review_summary),
  };
}

function masteryStatusLabel(status, confidence) {
  var key = String(status || "");
  asNumber(confidence, 0);
  if (key === "insufficient_evidence") return "证据不足";
  if (key === "stable") return "稳定掌握";
  if (key === "needs_confirmation") return "待确认";
  return "正在形成";
}

function normalizeLearningBrain(report) {
  var learnerFacing = asObject(report.learner_facing);
  var learningBrain = asObject(report.learning_brain);
  var summary = asObject(learnerFacing.summary);
  var nextAction = asObject(learnerFacing.next_action);
  var attempts = asList(learnerFacing.recent_attempts).map(
    function (item, index) {
      var attempt = asObject(item);
      return {
        key: String(attempt.key || "attempt-" + index),
        attemptRef: String(attempt.attempt_ref || ""),
        subjectId: String(attempt.subject_id || ""),
        botId: String(attempt.bot_id || ""),
        timeLabel: String(attempt.time_label || ""),
        title: String(attempt.title || "一次练习"),
        questionText: String(attempt.question_text || attempt.title || ""),
        concept: String(attempt.concept || ""),
        resultLabel: String(attempt.result_label || ""),
        tone: String(attempt.tone || ""),
        answerLine: String(attempt.answer_line || ""),
        diagnosis: String(attempt.diagnosis || ""),
        diagnosisDetail: String(
          attempt.diagnosis_detail || attempt.explanation || "",
        ),
        explanation: String(attempt.explanation || ""),
        evidenceLabel: String(attempt.evidence_label || ""),
        collectable: Boolean(attempt.collectable),
        isBookmarked: Boolean(attempt.is_bookmarked || attempt.isBookmarked),
        bookmarkLabel: String(
          attempt.bookmark_label ||
            attempt.bookmarkLabel ||
            (attempt.is_bookmarked || attempt.isBookmarked ? "已加入错题" : ""),
        ),
        detailLines: asList(attempt.detail_lines).length
          ? asList(attempt.detail_lines)
          : [
              attempt.answer_line,
              attempt.diagnosis_detail,
              attempt.explanation,
            ].filter(Boolean),
      };
    },
  );
  var diagnoses = asList(learnerFacing.diagnoses).map(function (item, index) {
    var diagnosis = asObject(item);
    return {
      key: String(diagnosis.key || "diagnosis-" + index),
      levelLabel: String(diagnosis.level_label || ""),
      title: String(diagnosis.title || ""),
      meta: String(diagnosis.meta || ""),
      detail: String(diagnosis.detail || ""),
      action: String(diagnosis.action || ""),
      count: asNumber(diagnosis.count, 0),
    };
  });
  var evidence = asList(learnerFacing.evidence_timeline).map(
    function (item, index) {
      var event = asObject(item);
      return {
        key: String(event.key || "timeline-" + index),
        timeLabel: String(event.time_label || ""),
        title: String(event.title || ""),
        line: String(event.line || ""),
        tone: String(event.tone || ""),
      };
    },
  );
  var visibleSections = asObject(learningBrain.visible_sections);
  var visibleTruths = normalizeVisibleTruths(visibleSections);
  var visibleEvidence = normalizeVisibleEvidence(visibleSections);
  var chains = asList(learnerFacing.training_loops).map(function (item, index) {
    var chain = asObject(item);
    return {
      key: String(chain.key || "loop-" + index),
      tone: String(chain.tone || ""),
      title: String(chain.title || ""),
      from: String(chain.from || ""),
      training: String(chain.training || ""),
      outcome: String(chain.outcome || ""),
    };
  });
  var training = nextAction.title
    ? [
        {
          key: "next-action",
          title: String(nextAction.title || ""),
          meta: String(nextAction.subtitle || ""),
          cta: String(nextAction.cta || "开始训练"),
          estimatedMinutes: asNumber(nextAction.estimated_minutes, 0),
          intent: asObject(nextAction.intent),
        },
      ]
    : [];
  return {
    summary: {
      title: String(summary.title || "今日学习复盘"),
      headline: String(summary.headline || ""),
      primaryFocus: String(summary.primary_focus || ""),
      todayDone: asNumber(summary.today_done, 0),
      recentThreeDone: asNumber(summary.recent_three_done, 0),
      weakCount: asNumber(summary.weak_count, 0),
    },
    attempts: attempts
      .filter(function (item) {
        return item.title || item.answerLine || item.diagnosis;
      })
      .slice(0, 5),
    diagnoses: diagnoses
      .filter(function (item) {
        return item.title || item.detail;
      })
      .slice(0, 4),
    truths: visibleTruths.length
      ? visibleTruths
      : diagnoses.slice(0, 4).map(function (item) {
          return {
            key: item.key,
            levelLabel: item.levelLabel,
            title: item.title,
            meta: item.meta,
            detail: item.detail,
            evidenceLabels: item.meta ? [item.meta] : [],
          };
        }),
    evidence: visibleEvidence.length
      ? visibleEvidence
      : evidence
          .filter(function (item) {
            return item.title || item.line;
          })
          .slice(0, 5),
    training: training,
    chains: chains
      .filter(function (item) {
        return item.title || item.outcome;
      })
      .slice(0, 4),
    graphChains: normalizeGraphChains(learningBrain),
    nextAction: {
      title: String(nextAction.title || ""),
      subtitle: String(nextAction.subtitle || ""),
      cta: String(nextAction.cta || "开始训练"),
      estimatedMinutes: asNumber(nextAction.estimated_minutes, 0),
      intent: asObject(nextAction.intent),
    },
    stats: {
      eventCount: asNumber(asObject(report.freshness).event_count, 0),
      createdClaimCount: asNumber(
        asObject(report.learning_brain).created_claim_count,
        0,
      ),
      typedGraphEdgeCount: asNumber(
        asObject(report.learning_brain).typed_graph_edge_count,
        0,
      ),
      projectionSubject: String(
        asObject(report.learning_brain).projection_subject || "",
      ),
      projectionSubjectLabel: String(
        asObject(report.learning_brain).projection_subject || "",
      ),
    },
  };
}

function isReadableLearningText(value) {
  var text = String(value || "");
  if (!text.trim()) return false;
  if (text.indexOf("practice /") >= 0) return false;
  if (text.indexOf("我想练习") >= 0) return false;
  if (text.indexOf("question_tests_concept") >= 0) return false;
  return true;
}

function cleanLearningText(value) {
  var text = String(value || "");
  var labels = {
    M06: "多选漏选",
    M07: "多选错选",
  };
  Object.keys(labels).forEach(function (code) {
    text = text.replace(new RegExp("错因\\s*" + code, "gi"), labels[code]);
    text = text.replace(new RegExp(code, "gi"), labels[code]);
  });
  text = text.replace(/我想练习.+?上出现\s*/g, "");
  text = text.replace(/practice \/.+?(?=(→|->|$))/g, "");
  text = text.replace(/\s*q_1\b/g, "案例题");
  return text.replace(/\s+/g, " ").trim();
}

function compactLearningTopic(value) {
  var text = cleanLearningText(value).trim();
  var match = text.match(/^我想练习(.+?)相关的题目/);
  if (match && match[1]) return match[1].trim();
  text = text.replace(/请严格围绕以下当前学习锚点出题/g, "").trim();
  return text || "";
}

function stateLabel(value) {
  var labels = {
    weak: "需要重点补",
    stable: "较稳定",
    observed: "已观察",
    insufficient_evidence: "证据不足",
    needs_revalidation: "需要复测",
    recurring: "反复出现",
    delivered: "已讲解",
    verified: "已验证",
    not_verified: "待再练",
  };
  var key = String(value || "").trim();
  return labels[key] || key || "";
}

function stateTone(value) {
  var key = String(value || "").trim();
  if (key === "weak" || key === "recurring" || key === "not_verified") return "warn";
  if (key === "stable" || key === "verified") return "good";
  return "neutral";
}

function abilityDimensionLabel(value) {
  var labels = {
    question_reading: "审题与题干边界",
    code_application: "规范应用",
    calculation: "计算与阈值判断",
    expression: "案例表达",
    transfer: "迁移应用",
    recurrence: "同类错误复发",
    explained: "系统解析跟进",
  };
  var key = String(value || "").trim();
  return labels[key] || compactLearningTopic(key) || key;
}

function prescriptionPhaseLabel(value) {
  var labels = {
    discovery_probe: "起步测评",
    repair_root: "补根因",
    expression_drill: "表达训练",
    transfer_case: "迁移练习",
    verification_probe: "验证题",
  };
  var key = String(value || "").trim();
  return labels[key] || key || "训练";
}

function evidenceCountLabel(count) {
  var n = asNumber(count, 0);
  return n > 0 ? "基于 " + n + " 条学习证据" : "";
}

function sourceValueLabel(count, unit, fallback) {
  var n = asNumber(count, 0);
  return n > 0 ? n + " " + unit : fallback || "待积累";
}

function sourceStatusLabel(count, activeLabel) {
  return asNumber(count, 0) > 0 ? activeLabel || "已接入" : "待积累";
}

function sourceTone(count) {
  return asNumber(count, 0) > 0 ? "active" : "pending";
}

function normalizeEvidenceEngineBatchC(body, learningState, scoringPointMap, mastery, learningBrain) {
  var sourceStatus = asObject(asObject(learningState).sourceStatus);
  var gradingCount = asNumber(sourceStatus.grading_fact_count, 0);
  var conversationCount = asNumber(sourceStatus.conversation_signal_count, 0);
  var totalSignalCount =
    gradingCount +
      conversationCount ||
    asNumber(asObject(asObject(learningBrain).stats).eventCount, 0);
  var attemptCount =
    asNumber(sourceStatus.case_attempt_count, 0) ||
    asList(asObject(learningBrain).attempts).length;
  var scoringCount = asList(asObject(scoringPointMap).items).length;
  var behaviorCount = asList(asObject(learningState).behaviorState).length;
  var graphCount = asList(asObject(learningState).knowledgeState).length;
  var decayCount =
    asNumber(asObject(mastery).overallConfidence, 0) > 0 ||
    asList(asObject(mastery).hotspots).length
      ? 1
      : 0;
  var difficultyCount = asNumber(sourceStatus.difficulty_signal_count, 0);
  var sources = [
    {
      key: "answers",
      label: "长期答题记录",
      value: sourceValueLabel(gradingCount, "条"),
      statusLabel: sourceStatusLabel(gradingCount, "已接入"),
      tone: sourceTone(gradingCount),
    },
    {
      key: "case_answers",
      label: "案例题答案",
      value: sourceValueLabel(attemptCount, "次"),
      statusLabel: sourceStatusLabel(attemptCount, "已接入"),
      tone: sourceTone(attemptCount),
    },
    {
      key: "scoring_points",
      label: "采分点命中",
      value: sourceValueLabel(scoringCount, "项"),
      statusLabel: sourceStatusLabel(scoringCount, "已接入"),
      tone: sourceTone(scoringCount),
    },
    {
      key: "error_tags",
      label: "错因标签",
      value: sourceValueLabel(behaviorCount, "类"),
      statusLabel: sourceStatusLabel(behaviorCount, "已识别"),
      tone: sourceTone(behaviorCount),
    },
    {
      key: "time_decay",
      label: "时间衰减",
      value: decayCount ? "已估计" : "待积累",
      statusLabel: decayCount ? "已估计" : "待积累",
      tone: sourceTone(decayCount),
    },
    {
      key: "knowledge_graph",
      label: "知识图谱关系",
      value: sourceValueLabel(graphCount, "个节点"),
      statusLabel: sourceStatusLabel(graphCount, "已关联"),
      tone: sourceTone(graphCount),
    },
    {
      key: "difficulty",
      label: "题目难度",
      value: sourceValueLabel(difficultyCount, "条"),
      statusLabel: sourceStatusLabel(difficultyCount, "已接入"),
      tone: sourceTone(difficultyCount),
    },
  ];
  return {
    title: "学习状态推断引擎",
    summary: totalSignalCount
      ? "融合 " + totalSignalCount + " 条历史学习证据"
      : "完成一次批改后开始推断",
    subtitle: "把答题记录、案例解析、采分点、错因与时间信号收束成今日行动",
    sources: sources,
    sourceStatus: sourceStatus,
    isEmpty: totalSignalCount === 0 && asObject(learningState).isEmpty,
  };
}

function normalizeVisibleTruths(sections) {
  return asList(asObject(sections).current_truth)
    .map(function (item, index) {
      var truth = asObject(item);
      var title = cleanLearningText(
        truth.display_title || truth.current_truth || "",
      );
      var meta = cleanLearningText(truth.display_meta || "");
      if (!isReadableLearningText(title + " " + meta)) return null;
      return {
        key: String(truth.key || "truth-" + index),
        levelLabel: String(
          truth.evidence_level_label || truth.evidence_level || "",
        ),
        title: title,
        meta: meta,
        detail: cleanLearningText(truth.current_truth || title),
        evidenceLabels: asList(truth.supporting_event_labels),
      };
    })
    .filter(Boolean)
    .slice(0, 4);
}

function normalizeVisibleEvidence(sections) {
  return asList(asObject(sections).evidence_flow)
    .map(function (item, index) {
      var evidence = asObject(item);
      var type = cleanLearningText(
        evidence.display_label || evidence.display_title || "",
      );
      var path = cleanLearningText(evidence.display_path || "");
      if (!isReadableLearningText(type + " " + path)) return null;
      return {
        key: String(evidence.key || "evidence-" + index),
        type: type,
        title: type,
        path: path,
        line: path,
        tone: String(evidence.tone || ""),
      };
    })
    .filter(Boolean)
    .slice(0, 5);
}

function normalizeGraphChains(learningBrain) {
  var graph = asObject(asObject(learningBrain).graph_chain);
  var uses = asList(graph.training_uses_question);
  var outcomes = asList(graph.training_not_improved_error).concat(
    asList(graph.training_improved_error),
  );
  return outcomes
    .map(function (item, index) {
      var outcome = asObject(item);
      var useEdge = asObject(uses[index]);
      var edgeType = String(outcome.edge_type || "");
      var improved =
        edgeType.indexOf("improved") >= 0 &&
        edgeType.indexOf("not_improved") < 0;
      return {
        key: "chain-" + index,
        tone: improved ? "improved" : "not-improved",
        title: String(
          outcome.display_meta || outcome.display_path || "训练闭环",
        ),
        training: String(useEdge.display_path || outcome.display_path || ""),
        question: String(useEdge.display_path || ""),
        outcome: improved ? "本次训练结果：改善" : "本次训练结果：未改善",
        eventLabel: outcome.reason_edge_event_id ? "训练链证据" : "",
      };
    })
    .filter(function (item) {
      return item.title || item.training;
    })
    .slice(0, 4);
}

function buildLearningReportViewModel(report) {
  var body = asObject(report);
  var overview = asObject(body.overview);
  var radar = normalizeRadar(body.radar_dimensions);
  var mastery = normalizeMastery(body.mastery);
  var learningBrain = normalizeLearningBrain(body);
  var truthSections = asObject(body.truth_sections);
  var degradedSources = asList(body.degraded_sources);
  var hero = asObject(body.hero);
  var primaryFocus =
    String(
      asObject(body.learner_facing).summary
        ? asObject(asObject(body.learner_facing).summary).primary_focus || ""
        : "",
    ) || String(overview.focus_hint || "");
  var nextTraining = normalizeNextTraining(body.next_training, learningBrain);
  var attempts = normalizeV2Attempts(body.attempts, learningBrain);
  // Batch C Task 8: three-layer learning state + scoring point map + today's prescription.
  var learningState = normalizeLearningStateBatchC(body.learning_state);
  var scoringPointMap = normalizeScoringPointMapBatchC(body.scoring_point_map);
  var prescription = normalizePrescriptionBatchC(nextTraining, learningState);
  var evidenceEngine = normalizeEvidenceEngineBatchC(
    body,
    learningState,
    scoringPointMap,
    mastery,
    learningBrain,
  );
  return {
    schemaVersion: asNumber(body.schema_version, 1),
    hero: {
      stageLabel: String(
        hero.stage_label ||
          levelName(overview.learner_level || "") ||
          "当前学习状态",
      ),
      scoreText: String(hero.score_text || mastery.overall + "%"),
      headline: String(
        hero.headline ||
          (primaryFocus
            ? "当前最该补：" + primaryFocus
            : "完成一次练习后生成重点"),
      ),
      primaryCta: asObject(hero.primary_cta),
    },
    metrics: [
      { key: "today", label: "今日", value: asNumber(overview.today_done, 0) },
      {
        key: "recent_three",
        label: "近3天",
        value: asNumber(overview.recent_three_done, 0),
      },
      {
        key: "streak",
        label: "连续学习",
        value: asNumber(overview.streak_days, 0),
      },
      {
        key: "weak",
        label: "待补错因",
        value: asNumber(overview.weak_node_count, 0),
      },
    ],
    stableTruths: asList(truthSections.stable_truths),
    recentObservations: asList(truthSections.recent_observations),
    attempts: attempts,
    mistakeBook: asObject(body.mistake_book),
    nextTraining: nextTraining,
    masteryDimensions: normalizeMasteryDimensions(body.mastery),
    overview: {
      todayDone: asNumber(overview.today_done, 0),
      dailyTarget: asNumber(overview.daily_target, 0),
      streakDays: asNumber(overview.streak_days, 0),
      dueTodayCount: asNumber(overview.due_today_count, 0),
      weakNodeCount: asNumber(overview.weak_node_count, 0),
      focusHint: String(overview.focus_hint || ""),
      learnerLevel: levelName(overview.learner_level || ""),
      learnerLevelName: levelName(overview.learner_level || ""),
      learnerStageTitle: overview.learner_level
        ? levelName(overview.learner_level) + "阶段"
        : "当前学习状态",
      studyTip: String(overview.study_tip || ""),
    },
    radar: radar,
    mastery: mastery,
    learningBrain: learningBrain,
    learningState: learningState,
    scoringPointMap: scoringPointMap,
    prescription: prescription,
    evidenceEngine: evidenceEngine,
    degraded: Boolean(body.degraded) || degradedSources.length > 0,
    degradedSources: degradedSources,
  };
}

// ─── Batch C Task 8: three-layer learning state + scoring point map ───

function normalizeLearningStateBatchC(state) {
  var src = asObject(state);
  function mapLayer(items, dimensionKey) {
    return asList(items).map(function (item, index) {
      var row = asObject(item);
      var rawLabel = String(row.label || row.dimension || row.node_id || "");
      var dimension = String(row.dimension || "");
      var label =
        dimensionKey === "dimension"
          ? abilityDimensionLabel(dimension || rawLabel)
          : compactLearningTopic(rawLabel) || abilityDimensionLabel(rawLabel);
      var state = String(row.state || "");
      var evidenceCount = asNumber(row.evidence_count, 0);
      return {
        key: String(row[dimensionKey] || row.node_id || "row-" + index),
        nodeId: String(row.node_id || ""),
        dimension: dimension,
        label: label,
        state: state,
        stateLabel: stateLabel(state),
        stateTone: stateTone(state),
        evidenceCount: evidenceCount,
        evidenceText: evidenceCountLabel(evidenceCount),
        evidenceRefs: asList(row.evidence_refs).map(function (ref) {
          return String(ref || "");
        }),
        granularity: String(row.granularity || ""),
        lastObservedAt: String(row.last_observed_at || ""),
      };
    });
  }
  var knowledge = mapLayer(src.knowledge_state, "node_id");
  var ability = mapLayer(src.ability_state, "dimension");
  var behavior = mapLayer(src.behavior_state, "dimension");
  return {
    knowledgeState: knowledge,
    abilityState: ability,
    behaviorState: behavior,
    sourceStatus: asObject(src.source_status),
    isEmpty:
      knowledge.length === 0 && ability.length === 0 && behavior.length === 0,
  };
}

function normalizeScoringPointMapBatchC(map) {
  var src = asObject(map);
  var items = asList(src.items).map(function (item, index) {
    var row = asObject(item);
    var nextAction = asObject(row.next_action);
    var intent = asObject(nextAction.intent);
    return {
      key: String(row.point_id || "item-" + index),
      pointId: String(row.point_id || ""),
      label: String(row.label || row.point_id || ""),
      granularity: String(row.granularity || ""),
      // UI label: "采分点" for scoring_point granularity, "审题要点" for keyword_only.
      granularityLabel:
        row.granularity === "keyword_only" ? "审题要点" : "采分点",
      rubricMode: String(row.rubric_mode || ""),
      knowledgeNodeId: String(row.knowledge_node_id || ""),
      abilityDimension: String(row.ability_dimension || ""),
      missCount: asNumber(row.miss_count, 0),
      evidenceRefs: asList(row.evidence_refs).map(function (ref) {
        return String(ref || "");
      }),
      errorCodes: asList(row.error_codes).map(function (code) {
        return String(code || "");
      }),
      nextActionKind: String(nextAction.kind || ""),
      nextActionIntent: intent,
    };
  });
  var emptyState = String(src.empty_state || "");
  return {
    items: items,
    emptyState: emptyState,
    emptyStateLabel: scoringPointMapEmptyLabel(emptyState),
    sourceStatus: asObject(src.source_status),
    isEmpty: items.length === 0,
  };
}

function scoringPointMapEmptyLabel(emptyState) {
  if (emptyState === "no_evidence") return "完成一次案例题批改后生成采分点地图";
  if (emptyState === "rubric_pending")
    return "本题暂无可拆采分点，已先按审题要点收集";
  return "";
}

function normalizePrescriptionBatchC(nextTraining, learningState) {
  var v2 = null;
  for (var i = 0; i < nextTraining.length; i++) {
    var candidate = asObject(nextTraining[i].intent);
    if (asNumber(candidate.intent_version, 0) === 2) {
      v2 = candidate;
      break;
    }
  }
  if (v2) {
    var conceptLabel = compactLearningTopic(v2.concept_label);
    return {
      status: String(v2.status || "active"),
      title: String(v2.concept_label || "今日处方"),
      titleLabel:
        conceptLabel ||
        (v2.status === "degraded" ? "先来一次起步测评" : "今日处方"),
      subtitle: String(v2.error_label || v2.reason || ""),
      reason: String(v2.reason || ""),
      conceptId: String(v2.concept_id || ""),
      conceptLabel: conceptLabel,
      abilityDimension: String(v2.ability_dimension || ""),
      abilityDimensionLabel: abilityDimensionLabel(v2.ability_dimension),
      behaviorState: String(v2.behavior_state || ""),
      behaviorStateLabel: stateLabel(v2.behavior_state),
      evidenceRefs: asList(v2.evidence_refs).map(function (ref) {
        return String(ref || "");
      }),
      steps: asList(v2.prescription_steps).map(function (step, index) {
        var src = asObject(step);
        return {
          key: String(src.phase || "phase-" + index),
          phase: String(src.phase || ""),
          phaseLabel: prescriptionPhaseLabel(src.phase),
          questionCount: asNumber(src.question_count, 0),
        };
      }),
      successCriteria: asObject(v2.success_criteria),
      intent: v2,
      ctaLabel: v2.status === "degraded" ? "先来一次起步测评" : "开始训练",
    };
  }
  // Degraded fallback when no v2 intent is available.
  return {
    status: "degraded",
    title: asObject(learningState).isEmpty
      ? "完成一次练习后生成今日处方"
      : "今日先做一轮探测题",
    titleLabel: asObject(learningState).isEmpty
      ? "完成一次练习后生成今日处方"
      : "今日先做一轮探测题",
    subtitle: "",
    reason: "",
    conceptId: "",
    conceptLabel: "",
    abilityDimension: "",
    abilityDimensionLabel: "",
    behaviorState: "",
    behaviorStateLabel: "",
    evidenceRefs: [],
    steps: [],
    successCriteria: {},
    intent: {},
    ctaLabel: "先做一道题",
  };
}

function normalizeV2Attempts(source, learningBrain) {
  var attempts = asList(source);
  if (!attempts.length) return asList(asObject(learningBrain).attempts);
  return attempts.map(function (item, index) {
    var attempt = asObject(item);
    return {
      key: String(attempt.attempt_key || attempt.key || "attempt-" + index),
      attemptRef: String(attempt.attempt_ref || ""),
      subjectId: String(attempt.subject_id || ""),
      botId: String(attempt.bot_id || ""),
      timeLabel: String(attempt.time_label || ""),
      title: String(attempt.question_title || attempt.title || "一次练习"),
      questionText: String(
        attempt.question_preview || attempt.question_text || "",
      ),
      resultLabel: String(attempt.result_label || ""),
      tone: String(attempt.tone || ""),
      answerLine: String(attempt.answer_line || ""),
      diagnosis: String(attempt.diagnosis || ""),
      diagnosisDetail: String(attempt.why_it_matters || ""),
      collectable: Boolean(asObject(attempt.actions).bookmark),
      isBookmarked: Boolean(attempt.is_bookmarked || attempt.isBookmarked),
      bookmarkLabel: String(
        attempt.bookmark_label ||
          attempt.bookmarkLabel ||
          (attempt.is_bookmarked || attempt.isBookmarked ? "已加入错题" : ""),
      ),
    };
  });
}

function normalizeNextTraining(source, learningBrain) {
  var items = asList(source);
  if (!items.length) return asList(asObject(learningBrain).training);
  return items.map(function (item, index) {
    var training = asObject(item);
    return {
      key: String(training.key || "training-" + index),
      title: String(training.title || ""),
      meta: String(training.reason || ""),
      cta: String(training.cta || "开始训练"),
      estimatedMinutes: asNumber(training.estimated_minutes, 0),
      intent: asObject(training.intent),
    };
  });
}

function normalizeMasteryDimensions(source) {
  return asList(asObject(source).dimensions).map(function (item, index) {
    var dimension = asObject(item);
    return {
      key: String(dimension.key || "mastery-" + index),
      name: chapterName(dimension.name || ""),
      score: asNumber(dimension.score, 0),
      confidence: asNumber(dimension.confidence, 0),
      status: String(dimension.status || ""),
      sampleCount: asNumber(dimension.sample_count, 0),
      coverageRatio: asNumber(dimension.coverage_ratio, 0),
    };
  });
}

function toReportPageData(model) {
  var vm = asObject(model);
  var overview = asObject(vm.overview);
  var radar = asObject(vm.radar);
  var mastery = asObject(vm.mastery);
  var brain = asObject(vm.learningBrain);
  var emptyBrain =
    asList(brain.truths).length === 0 &&
    asList(brain.evidence).length === 0 &&
    asList(brain.training).length === 0 &&
    asList(brain.chains).length === 0;
  return {
    todayDone: overview.todayDone || 0,
    dailyTarget: overview.dailyTarget || 0,
    streakDays: overview.streakDays || 0,
    dueTodayCount: overview.dueTodayCount || 0,
    weakNodeCount: overview.weakNodeCount || 0,
    focusHint: overview.focusHint || "",
    learnerLevel: overview.learnerLevel || "",
    learnerLevelName: overview.learnerLevelName || overview.learnerLevel || "",
    learnerStageTitle: overview.learnerStageTitle || "当前学习状态",
    studyTip: overview.studyTip || "",
    radarDimensions: asList(radar.dims),
    strongCount: radar.strongCount || 0,
    normalCount: radar.normalCount || 0,
    weakCount: radar.weakCount || 0,
    avgScore: radar.avgScore || 0,
    overviewScore: asList(radar.dims).length
      ? radar.avgScore || 0
      : mastery.overall || 0,
    dimList: asList(radar.dimList),
    overallMastery: mastery.overall || 0,
    masteryConfidence: mastery.overallConfidence || 0,
    masteryStatus: mastery.overallStatus || "",
    masteryStatusLabel: mastery.overallStatusLabel || "证据不足",
    masteryScoreClass: mastery.overallClass || "",
    masteryGroups: asList(mastery.groups),
    hotspots: asList(mastery.hotspots),
    reviewSummary: asObject(mastery.reviewSummary),
    learningBrainSummary: asObject(brain.summary),
    learningBrainAttempts: asList(brain.attempts),
    learningBrainDiagnoses: asList(brain.diagnoses),
    learningBrainTruths: asList(brain.truths),
    learningBrainEvidence: asList(brain.evidence),
    learningBrainTraining: asList(brain.training),
    learningBrainChains: asList(brain.graphChains),
    learningBrainNextAction: asObject(brain.nextAction),
    learningBrainGraphStats: asObject(brain.stats),
    learningBrainEmpty: emptyBrain,
    learningReviewSummary: asObject(brain.summary),
    learningAttemptCards: asList(vm.attempts).length
      ? asList(vm.attempts)
      : asList(brain.attempts),
    learningDiagnosisCards: asList(brain.diagnoses),
    learningTrainingLoops: asList(brain.chains),
    learningNextAction: asObject(brain.nextAction),
    engineEvidenceSummary: String(
      asObject(vm.evidenceEngine).summary || "",
    ),
    engineEvidenceSubtitle: String(
      asObject(vm.evidenceEngine).subtitle || "",
    ),
    engineEvidenceSources: asList(asObject(vm.evidenceEngine).sources),
    // Batch C Task 8: flat page fields for the new sections.
    learningStateKnowledge: asList(asObject(vm.learningState).knowledgeState),
    learningStateAbility: asList(asObject(vm.learningState).abilityState),
    learningStateBehavior: asList(asObject(vm.learningState).behaviorState),
    learningStateIsEmpty: Boolean(asObject(vm.learningState).isEmpty),
    scoringPointMapItems: asList(asObject(vm.scoringPointMap).items),
    scoringPointMapEmptyState: String(
      asObject(vm.scoringPointMap).emptyState || "",
    ),
    scoringPointMapEmptyLabel: String(
      asObject(vm.scoringPointMap).emptyStateLabel || "",
    ),
    prescriptionTitle: String(
      asObject(vm.prescription).titleLabel ||
        asObject(vm.prescription).title ||
        "",
    ),
    prescriptionSubtitle: String(asObject(vm.prescription).subtitle || ""),
    prescriptionReason: String(asObject(vm.prescription).reason || ""),
    prescriptionStatus: String(asObject(vm.prescription).status || ""),
    prescriptionSteps: asList(asObject(vm.prescription).steps),
    prescriptionCtaLabel: String(asObject(vm.prescription).ctaLabel || ""),
    prescriptionEvidenceRefs: asList(asObject(vm.prescription).evidenceRefs),
    sharedLearningReportViewModel: vm,
  };
}

module.exports = {
  buildLearningReportViewModel: buildLearningReportViewModel,
  toReportPageData: toReportPageData,
};
