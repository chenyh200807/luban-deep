function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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
    };
  });
  var scores = dims.map(function (item) {
    return Math.round(asNumber(item.value, 0) * 100);
  });
  var strong = scores.filter(function (score) {
    return score >= 70;
  }).length;
  var weak = scores.filter(function (score) {
    return score > 0 && score < 40;
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
      var score = Math.round(asNumber(item.value, 0) * 100);
      return {
        name: item.name,
        score: score,
        rateText: score + "%",
        level: score >= 70 ? "strong" : score >= 40 ? "normal" : "weak",
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
  if (overall && typeof overall === "object") overall = overall.score;
  var groups = asList(mastery.groups).map(function (group) {
    var item = asObject(group);
    var chapters = asList(item.chapters).map(function (chapter) {
      var c = asObject(chapter);
      var rate = Math.round(asNumber(c.mastery, asNumber(c.score, 0)));
      return {
        name: chapterName(c.name || ""),
        mastery: rate,
        color: rate >= 70 ? "#34d399" : rate >= 40 ? "#fbbf24" : "#f87171",
      };
    });
    chapters.sort(function (a, b) {
      return a.mastery - b.mastery;
    });
    return {
      name: String(item.name || ""),
      avgMastery: Math.round(asNumber(item.avg_mastery, 0)),
      chapters: chapters,
    };
  });
  return {
    overall: Math.round(asNumber(overall, 0)),
    overallConfidence: overallConfidence,
    overallStatus: overallStatus,
    overallStatusLabel: masteryStatusLabel(overallStatus, overallConfidence),
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
  var value = asNumber(confidence, 0);
  if (key === "insufficient_evidence" || value < 0.4) return "证据不足";
  if (key === "stable" || value >= 0.7) return "稳定掌握";
  if (key === "needs_confirmation") return "待确认";
  return "正在形成";
}

function normalizeLearningBrain(report) {
  var learnerFacing = asObject(report.learner_facing);
  var learningBrain = asObject(report.learning_brain);
  var summary = asObject(learnerFacing.summary);
  var nextAction = asObject(learnerFacing.next_action);
  var attempts = asList(learnerFacing.recent_attempts).map(function (item, index) {
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
      diagnosisDetail: String(attempt.diagnosis_detail || attempt.explanation || ""),
      explanation: String(attempt.explanation || ""),
      evidenceLabel: String(attempt.evidence_label || ""),
      collectable: Boolean(attempt.collectable),
      isBookmarked: Boolean(attempt.is_bookmarked || attempt.isBookmarked),
      bookmarkLabel: String(attempt.bookmark_label || attempt.bookmarkLabel || (attempt.is_bookmarked || attempt.isBookmarked ? "已加入错题" : "")),
      detailLines: asList(attempt.detail_lines).length
        ? asList(attempt.detail_lines)
        : [attempt.answer_line, attempt.diagnosis_detail, attempt.explanation].filter(Boolean),
    };
  });
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
  var evidence = asList(learnerFacing.evidence_timeline).map(function (item, index) {
    var event = asObject(item);
    return {
      key: String(event.key || "timeline-" + index),
      timeLabel: String(event.time_label || ""),
      title: String(event.title || ""),
      line: String(event.line || ""),
      tone: String(event.tone || ""),
    };
  });
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
    attempts: attempts.filter(function (item) {
      return item.title || item.answerLine || item.diagnosis;
    }).slice(0, 5),
    diagnoses: diagnoses.filter(function (item) {
      return item.title || item.detail;
    }).slice(0, 4),
    truths: (visibleTruths.length ? visibleTruths : diagnoses.slice(0, 4).map(function (item) {
      return {
        key: item.key,
        levelLabel: item.levelLabel,
        title: item.title,
        meta: item.meta,
        detail: item.detail,
        evidenceLabels: item.meta ? [item.meta] : [],
      };
    })),
    evidence: (visibleEvidence.length ? visibleEvidence : evidence.filter(function (item) {
      return item.title || item.line;
    }).slice(0, 5)),
    training: training,
    chains: chains.filter(function (item) {
      return item.title || item.outcome;
    }).slice(0, 4),
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
      createdClaimCount: asNumber(asObject(report.learning_brain).created_claim_count, 0),
      typedGraphEdgeCount: asNumber(asObject(report.learning_brain).typed_graph_edge_count, 0),
      projectionSubject: String(asObject(report.learning_brain).projection_subject || ""),
      projectionSubjectLabel: String(asObject(report.learning_brain).projection_subject || ""),
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

function normalizeVisibleTruths(sections) {
  return asList(asObject(sections).current_truth)
    .map(function (item, index) {
      var truth = asObject(item);
      var title = cleanLearningText(truth.display_title || truth.current_truth || "");
      var meta = cleanLearningText(truth.display_meta || "");
      if (!isReadableLearningText(title + " " + meta)) return null;
      return {
        key: String(truth.key || "truth-" + index),
        levelLabel: String(truth.evidence_level_label || truth.evidence_level || ""),
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
      var type = cleanLearningText(evidence.display_label || evidence.display_title || "");
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
      var improved = edgeType.indexOf("improved") >= 0 && edgeType.indexOf("not_improved") < 0;
      return {
        key: "chain-" + index,
        tone: improved ? "improved" : "not-improved",
        title: String(outcome.display_meta || outcome.display_path || "训练闭环"),
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
    String(asObject(body.learner_facing).summary ? asObject(asObject(body.learner_facing).summary).primary_focus || "" : "") ||
    String(overview.focus_hint || "");
  var nextTraining = normalizeNextTraining(body.next_training, learningBrain);
  var attempts = normalizeV2Attempts(body.attempts, learningBrain);
  return {
    schemaVersion: asNumber(body.schema_version, 1),
    hero: {
      stageLabel: String(hero.stage_label || levelName(overview.learner_level || "") || "当前学习状态"),
      scoreText: String(hero.score_text || mastery.overall + "%"),
      headline: String(hero.headline || (primaryFocus ? "当前最该补：" + primaryFocus : "完成一次练习后生成重点")),
      primaryCta: asObject(hero.primary_cta),
    },
    metrics: [
      { key: "today", label: "今日", value: asNumber(overview.today_done, 0) },
      { key: "recent_three", label: "近3天", value: asNumber(overview.recent_three_done, 0) },
      { key: "streak", label: "连续学习", value: asNumber(overview.streak_days, 0) },
      { key: "weak", label: "待补错因", value: asNumber(overview.weak_node_count, 0) },
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
    degraded: Boolean(body.degraded) || degradedSources.length > 0,
    degradedSources: degradedSources,
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
      questionText: String(attempt.question_preview || attempt.question_text || ""),
      resultLabel: String(attempt.result_label || ""),
      tone: String(attempt.tone || ""),
      answerLine: String(attempt.answer_line || ""),
      diagnosis: String(attempt.diagnosis || ""),
      diagnosisDetail: String(attempt.why_it_matters || ""),
      collectable: Boolean(asObject(attempt.actions).bookmark),
      isBookmarked: Boolean(attempt.is_bookmarked || attempt.isBookmarked),
      bookmarkLabel: String(attempt.bookmark_label || attempt.bookmarkLabel || (attempt.is_bookmarked || attempt.isBookmarked ? "已加入错题" : "")),
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
    overviewScore: asList(radar.dims).length ? radar.avgScore || 0 : mastery.overall || 0,
    dimList: asList(radar.dimList),
    overallMastery: mastery.overall || 0,
    masteryConfidence: mastery.overallConfidence || 0,
    masteryStatus: mastery.overallStatus || "",
    masteryStatusLabel: mastery.overallStatusLabel || "证据不足",
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
    learningAttemptCards: asList(vm.attempts).length ? asList(vm.attempts) : asList(brain.attempts),
    learningDiagnosisCards: asList(brain.diagnoses),
    learningTrainingLoops: asList(brain.chains),
    learningNextAction: asObject(brain.nextAction),
    sharedLearningReportViewModel: vm,
  };
}

module.exports = {
  buildLearningReportViewModel: buildLearningReportViewModel,
  toReportPageData: toReportPageData,
};
