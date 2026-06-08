var taxonomy = require("./taxonomy");

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
  if (isDeicticTopicLabel(text)) return "";
  var resolved = taxonomy.displayChapterName(text, "");
  if (isDeicticTopicLabel(resolved)) return "";
  return resolved || text || "未归类能力";
}

function isDeicticTopicLabel(value) {
  var compact = String(value || "").replace(/[\s　，,。.!！?？:：;；“”"'‘’（）()【】[\]<>《》]/g, "");
  return (
    [
      "这题",
      "那题",
      "本题",
      "该题",
      "此题",
      "题目",
      "当前题",
      "当前题目",
      "这个题",
      "那个题",
      "这道题",
      "那道题",
      "这一题",
      "那一题",
      "这道题目",
      "那道题目",
      "当前考点",
      "当前知识点",
    ].indexOf(compact) >= 0
  );
}

function normalizeLearningTopic(rawValue, taxonomyPath) {
  var raw = String(rawValue || "").trim();
  var path = asList(taxonomyPath).map(function (name) {
    return String(name || "").trim();
  }).filter(Boolean);
  if (taxonomy.isNonTopicLabel(raw)) return null;
  var label = chapterName(raw);
  var meta = taxonomy.resolveTextbookTopic(raw, path) || taxonomy.resolveTextbookTopic(label, path);
  if (!meta) return null;
  var name = label;
  if (/^1A\d{6}(?:-\d+)?(?:-[a-z]+)?$/i.test(raw) && path.length) {
    name = path[path.length - 1];
  }
  if (!name || taxonomy.isNonTopicLabel(name)) return null;
  return {
    name: name,
    textbookChapterNo: meta.chapterNo,
    textbookChapterName: meta.chapterName,
    textbookSectionName: meta.sectionName || "",
    taxonomyPath: path,
  };
}

function decorateMasteryGroup(group) {
  var item = asObject(group);
  var chapters = asList(item.chapters).filter(function (chapter) {
    return chapter && chapter.name;
  });
  var hiddenCount = Math.max(0, chapters.length - 3);
  var unit = item.hierarchical ? "子章节" : "章节";
  return {
    name: String(item.name || ""),
    avgMastery: Math.round(asNumber(item.avg_mastery, item.avgMastery || 0)),
    avgClass: String(item.avg_class || item.avgClass || ""),
    chapters: chapters,
    previewChapters: chapters.slice(0, 3),
    chapterCount: chapters.length,
    hiddenCount: hiddenCount,
    expanded: Boolean(item.expanded),
    previewText:
      chapters.length + " 个" + unit + (hiddenCount ? " · 还有 " + hiddenCount + " 个" + unit : ""),
  };
}

function masteryAvgClass(score) {
  var value = Math.round(asNumber(score, 0));
  if (value >= 70) return "avg-good";
  if (value >= 40) return "avg-mid";
  return "avg-low";
}

function buildMasteryDisplayGroups(sourceGroups) {
  var byChapter = {};
  var textbookGroups = [];
  asList(sourceGroups).forEach(function (group) {
    asList(group.chapters).forEach(function (chapter) {
      var chapterNameKey = String(chapter.textbookChapterName || "").trim();
      if (!chapterNameKey) return;
      if (!byChapter[chapterNameKey]) {
        byChapter[chapterNameKey] = {
          name: chapterNameKey,
          chapterNo: chapter.textbookChapterNo || 999,
          chapters: [],
          hierarchical: true,
        };
        textbookGroups.push(byChapter[chapterNameKey]);
      }
      byChapter[chapterNameKey].chapters.push(chapter);
    });
  });
  return textbookGroups
    .sort(function (a, b) {
      return asNumber(a.chapterNo, 999) - asNumber(b.chapterNo, 999);
    })
    .map(function (group) {
      var avg = Math.round(
        group.chapters.reduce(function (sum, chapter) {
          return sum + asNumber(chapter.mastery, 0);
        }, 0) / Math.max(group.chapters.length, 1),
      );
      return decorateMasteryGroup({
        name: group.name,
        avg_mastery: avg,
        avg_class: masteryAvgClass(avg),
        chapters: group.chapters,
        hierarchical: true,
      });
    });
}

function mergeRadarDimensions(items) {
  var byChapter = {};
  var ordered = [];
  asList(items).forEach(function (item) {
    if (!item || !item.name) return;
    var key = item.textbookChapterName || item.name;
    if (!byChapter[key]) {
      byChapter[key] = {
        name: key,
        values: [],
        scores: [],
        level: item.level,
        textbookChapterNo: item.textbookChapterNo || 999,
      };
      ordered.push(byChapter[key]);
    }
    byChapter[key].values.push(asNumber(item.value, 0));
    byChapter[key].scores.push(asNumber(item.score, asNumber(item.value, 0) * 100));
  });
  return ordered
    .sort(function (a, b) {
      return asNumber(a.textbookChapterNo, 999) - asNumber(b.textbookChapterNo, 999);
    })
    .map(function (item) {
      var score = Math.round(
        item.scores.reduce(function (sum, current) {
          return sum + current;
        }, 0) / Math.max(item.scores.length, 1),
      );
      return {
        name: item.name,
        value: score / 100,
        score: score,
        level: item.level,
        rateText: score + "%",
      };
    });
}

function normalizeRadar(dimensions) {
  var dims = mergeRadarDimensions(asList(dimensions).map(function (item) {
    var source = asObject(item);
    var taxonomyPath = asList(source.taxonomy_path || source.taxonomyPath).map(function (name) {
      return String(name || "").trim();
    }).filter(Boolean);
    var topic = normalizeLearningTopic(source.label || source.name || source.key || "", taxonomyPath);
    if (!topic) return null;
    var score = asNumber(source.score, NaN);
    var value =
      typeof source.value === "number"
        ? source.value
        : Number.isFinite(score)
          ? score / 100
          : 0;
    return {
      name: topic.name,
      textbookChapterNo: topic.textbookChapterNo,
      textbookChapterName: topic.textbookChapterName,
      value: value || 0,
      score: Math.round(asNumber(source.score, asNumber(value, 0) * 100)),
      level: String(source.level || source.status || "observed"),
      rateText: String(source.rate_text || source.rateText || ""),
    };
  }).filter(Boolean));
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
  var hasOverall =
    (overall && typeof overall === "object")
      ? overall.score !== undefined && overall.score !== null && overall.score !== ""
      : overall !== undefined && overall !== null && overall !== "";
  var overallConfidence = asNumber(overallPayload.confidence, 0);
  var overallStatus = String(overallPayload.status || "");
  var overallClass = String(overallPayload.class_name || overallPayload.className || "");
  if (overall && typeof overall === "object") overall = overall.score;
  var rawGroups = asList(mastery.groups).map(function (group) {
    var item = asObject(group);
    var chapters = asList(item.chapters).map(function (chapter) {
      var c = asObject(chapter);
      var rate = Math.round(asNumber(c.mastery, asNumber(c.score, 0)));
      var taxonomyPath = asList(c.taxonomy_path || c.taxonomyPath).map(function (name) {
        return String(name || "").trim();
      }).filter(Boolean);
      var topic = normalizeLearningTopic(c.name || "", taxonomyPath);
      if (!topic && c.textbook_chapter_name) {
        topic = {
          name: chapterName(c.name || ""),
          textbookChapterNo: asNumber(c.textbook_chapter_no, 999),
          textbookChapterName: String(c.textbook_chapter_name || ""),
          textbookSectionName: String(c.textbook_section_name || ""),
          taxonomyPath: taxonomyPath,
        };
      }
      if (!topic) return null;
      return {
        name: topic.name,
        mastery: rate,
        color: String(c.color || ""),
        taxonomyPath: topic.taxonomyPath,
        textbookChapterNo: topic.textbookChapterNo,
        textbookChapterName: topic.textbookChapterName,
        textbookSectionName: topic.textbookSectionName,
      };
    }).filter(Boolean);
    return {
      name: item.name,
      avgMastery: Math.round(asNumber(item.avg_mastery, 0)),
      avgClass: String(item.avg_class || item.avgClass || ""),
      chapters: chapters,
    };
  }).filter(function (group) {
    return group.chapters.length;
  });
  var knowledgeSummary = normalizeKnowledgeSummary(mastery.knowledge_summary || mastery.knowledgeSummary);
  var groups = buildMasteryDisplayGroups(rawGroups);
  if (!groups.length && knowledgeSummary.textbookChapters.length) {
    groups = buildMasteryDisplayGroups([
      {
        name: "教材目录进度",
        avg_mastery: 0,
        chapters: knowledgeSummary.textbookChapters.map(function (chapter) {
          var evaluated = asNumber(chapter.evaluatedTopics, 0);
          var mastered = asNumber(chapter.masteredTopics, 0);
          var developing = asNumber(chapter.developingTopics, 0);
          var weak = asNumber(chapter.weakTopics, 0);
          var score = 0;
          if (evaluated > 0) {
            score = Math.round(
              (mastered * 100 + developing * 55 + weak * 25) / evaluated,
            );
          }
          return {
            name: chapter.chapterName,
            mastery: score,
            color: score >= 70 ? "#40d99d" : score >= 40 ? "#7fd9ff" : "#ff7185",
            textbookChapterNo: chapter.chapterNo,
            textbookChapterName: chapter.chapterName,
            textbookSectionName: "",
            taxonomyPath: [chapter.chapterName],
          };
        }),
      },
    ]);
  }
  return {
    hasOverall: hasOverall,
    overall: Math.round(asNumber(overall, 0)),
    overallConfidence: overallConfidence,
    overallStatus: overallStatus,
    overallStatusLabel: masteryStatusLabel(overallStatus, overallConfidence),
    overallClass: overallClass,
    groups: groups,
    hotspots: asList(mastery.hotspots).map(function (hotspot) {
      var item = asObject(hotspot);
      var rate = Math.round(asNumber(item.mastery, asNumber(item.score, 0)));
      var taxonomyPath = asList(item.taxonomy_path || item.taxonomyPath);
      var topic = normalizeLearningTopic(item.name || "", taxonomyPath);
      if (!topic) return null;
      return {
        name: topic.name,
        mastery: rate,
        rateText: rate + "%",
      };
    }).filter(Boolean),
    knowledgeSummary: knowledgeSummary,
    reviewSummary: asObject(mastery.review_summary),
  };
}

function firstLearningTopicFromValues(values, taxonomyPath) {
  var path = asList(taxonomyPath).map(function (name) {
    return String(name || "").trim();
  }).filter(Boolean);
  for (var i = 0; i < values.length; i++) {
    var topic = normalizeLearningTopic(values[i], path);
    if (topic) return topic;
  }
  return null;
}

function learningSignalHotspotScore(source) {
  var item = asObject(source);
  var occurrenceCount = asNumber(
    item.occurrence_count || item.occurrenceCount,
    asList(item.occurrence_timeline || item.occurrenceTimeline).length,
  );
  var confidence = asNumber(item.confidence, 0);
  if (occurrenceCount >= 2) return 25;
  if (confidence > 0) return Math.max(20, Math.round((1 - Math.min(confidence, 0.9)) * 60));
  return 35;
}

function buildLearningSignalHotspots(body, learningState) {
  var rawBrain = asObject(asObject(body).learning_brain);
  var analytics = asObject(asObject(body).long_term_analytics);
  var recurrentErrors = asList(analytics.recurrent_errors || analytics.recurrentErrors);
  var recurrentByKey = {};
  recurrentErrors.forEach(function (item) {
    var row = asObject(item);
    var key = String(row.concept_id || "") + "::" + String(row.error_code || "");
    recurrentByKey[key] = row;
  });
  var rows = [];
  asList(rawBrain.weak_points || rawBrain.weakPoints).forEach(function (weak) {
    var item = asObject(weak);
    var key = String(item.concept_id || "") + "::" + String(item.error_code || "");
    var recurrent = recurrentByKey[key] || {};
    var recommended = asObject(item.recommended_training);
    var topic = firstLearningTopicFromValues(
      [
        item.label,
        item.concept_label,
        recommended.concept_label,
        item.display_title,
        item.current_truth,
        item.concept_id,
      ],
      item.taxonomy_path || item.taxonomyPath,
    );
    if (!topic) return;
    rows.push({
      name: topic.name,
      mastery: learningSignalHotspotScore(Object.assign({}, item, recurrent)),
      rateText: learningSignalHotspotScore(Object.assign({}, item, recurrent)) + "%",
      occurrenceCount: asNumber(
        recurrent.occurrence_count || item.occurrence_count || item.occurrenceCount,
        asList(item.occurrence_timeline || item.occurrenceTimeline).length,
      ),
    });
  });
  asList(asObject(learningState).knowledgeState).forEach(function (state) {
    var row = asObject(state);
    if (["weak", "recurring", "needs_revalidation", "unstable"].indexOf(row.state) < 0) return;
    var topic = firstLearningTopicFromValues(
      [row.label, row.nodeId, row.node_id, row.key],
      row.taxonomyPath || row.taxonomy_path,
    );
    if (!topic) return;
    rows.push({
      name: topic.name,
      mastery: row.state === "needs_revalidation" ? 30 : 35,
      rateText: (row.state === "needs_revalidation" ? 30 : 35) + "%",
      occurrenceCount: asNumber(row.evidenceCount || row.evidence_count, 0),
    });
  });
  var byName = {};
  rows.forEach(function (item) {
    if (!item.name) return;
    var existing = byName[item.name];
    if (!existing || item.occurrenceCount > existing.occurrenceCount || item.mastery < existing.mastery) {
      byName[item.name] = item;
    }
  });
  return Object.keys(byName)
    .map(function (name) {
      return byName[name];
    })
    .sort(function (a, b) {
      return b.occurrenceCount - a.occurrenceCount || a.mastery - b.mastery;
    })
    .slice(0, 5);
}

function buildLearningSignalReviewSummary(body, learningState) {
  var queue = asObject(asObject(body).revalidation_queue || asObject(body).revalidationQueue);
  var queueItems = asList(queue.items).filter(function (item) {
    var status = String(asObject(item).status || "active");
    return status !== "done" && status !== "completed" && status !== "dismissed";
  });
  var explicitTotal = asNumber(queue.total_due || queue.totalDue, NaN);
  var totalDue = Number.isFinite(explicitTotal) ? explicitTotal : queueItems.length;
  if (!totalDue && queueItems.length) totalDue = queueItems.length;
  if (!totalDue) {
    totalDue = asList(asObject(learningState).knowledgeState).filter(function (item) {
      return String(asObject(item).state || "") === "needs_revalidation";
    }).length;
  }
  var explicitOverdue = asNumber(queue.overdue_count || queue.overdueCount, NaN);
  var overdueCount = Number.isFinite(explicitOverdue)
    ? explicitOverdue
    : queueItems.filter(function (item) {
        var row = asObject(item);
        return row.overdue === true || String(row.status || "") === "overdue";
      }).length;
  return {
    total_due: totalDue,
    overdue_count: overdueCount,
  };
}

function enrichMasteryFromLearningSignals(mastery, body, learningState) {
  var result = Object.assign({}, asObject(mastery));
  if (!asList(result.hotspots).length) {
    result.hotspots = buildLearningSignalHotspots(body, learningState);
  }
  var review = asObject(result.reviewSummary);
  if (
    asNumber(review.total_due || review.totalDue, 0) <= 0 &&
    asNumber(review.overdue_count || review.overdueCount, 0) <= 0
  ) {
    result.reviewSummary = buildLearningSignalReviewSummary(body, learningState);
  }
  return result;
}

function normalizeKnowledgeSummary(source) {
  var summary = asObject(source);
  var chapters = asList(summary.textbook_chapters || summary.textbookChapters).map(function (item) {
    var chapter = asObject(item);
    return {
      chapterNo: asNumber(chapter.chapter_no || chapter.chapterNo, 0),
      chapterName: String(chapter.chapter_name || chapter.chapterName || ""),
      sectionCount: asNumber(chapter.section_count || chapter.sectionCount, 0),
      evaluatedTopics: asNumber(chapter.evaluated_topics || chapter.evaluatedTopics, 0),
      masteredTopics: asNumber(chapter.mastered_topics || chapter.masteredTopics, 0),
      developingTopics: asNumber(chapter.developing_topics || chapter.developingTopics, 0),
      weakTopics: asNumber(chapter.weak_topics || chapter.weakTopics, 0),
      topTopics: asList(chapter.top_topics || chapter.topTopics).map(function (name) {
        return String(name || "").trim();
      }).filter(Boolean),
      status: String(chapter.status || "unseen"),
    };
  }).filter(function (chapter) {
    return chapter.chapterNo > 0 && chapter.chapterName;
  });
  return {
    totalNodes: asNumber(summary.total_nodes || summary.totalNodes, 0),
    codedNodes: asNumber(summary.coded_nodes || summary.codedNodes, 0),
    leafNodes: asNumber(summary.leaf_nodes || summary.leafNodes, 0),
    uniqueCodes: asNumber(summary.unique_codes || summary.uniqueCodes, 0),
    duplicateCodeRows: asNumber(summary.duplicate_code_rows || summary.duplicateCodeRows, 0),
    totalTextbookChapters: asNumber(summary.total_textbook_chapters || summary.totalTextbookChapters, chapters.length),
    evaluatedTopics: asNumber(summary.evaluated_topics || summary.evaluatedTopics, 0),
    evaluatedLeafPoints: asNumber(summary.evaluated_leaf_points || summary.evaluatedLeafPoints, 0),
    masteredTopics: asNumber(summary.mastered_topics || summary.masteredTopics, 0),
    developingTopics: asNumber(summary.developing_topics || summary.developingTopics, 0),
    weakTopics: asNumber(summary.weak_topics || summary.weakTopics, 0),
    unmeasuredLeafPoints: asNumber(summary.unmeasured_leaf_points || summary.unmeasuredLeafPoints, 0),
    textbookChapters: chapters,
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
    M01: "知识点不熟",
    M02: "关键词误读",
    M03: "概念混淆",
    M04: "选项陷阱",
    M05: "审题方向错误",
    M06: "多选漏选",
    M07: "多选错选",
    M08: "规范数字混淆",
    M09: "题干条件提取不完整",
    M10: "用常识替代规范判断",
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

function looksLikePromptTopic(value) {
  var text = String(value || "").trim();
  if (!text) return false;
  return (
    text.indexOf("我想练习") >= 0 ||
    text.indexOf("请严格围绕") >= 0 ||
    text.indexOf("当前学习锚点") >= 0 ||
    text.indexOf("training_mode") >= 0 ||
    text.indexOf("mixed_rev") >= 0 ||
    text.indexOf("那出") >= 0 ||
    /(先做|做|出)\s*\d+\s*道?题/.test(text) ||
    (text.indexOf("题目") >= 0 &&
      (text.indexOf("练习") >= 0 || text.indexOf("相关") >= 0))
  );
}

function compactPrescriptionTopic(value) {
  var raw = cleanLearningText(value).trim();
  if (!raw || looksLikePromptTopic(raw)) return "";
  var topic = compactLearningTopic(raw).replace(/\s+/g, "");
  if (!topic || looksLikePromptTopic(topic)) return "";
  if (topic.length > 24) return "";
  return topic;
}

function mistakeQuestionTitle(value) {
  var text = cleanLearningText(value).trim();
  if (text.indexOf("我想练习") >= 0) {
    var topic = compactLearningTopic(text);
    return topic ? topic + "相关错题" : "一次错题记录";
  }
  return text || "一次错题记录";
}

function stateLabel(value) {
  var labels = {
    weak: "需要重点补",
    stable: "较稳定",
    observed: "已观察",
    improving: "正在改善",
    unstable: "还不稳定",
    active: "仍需跟进",
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
  if (
    key === "weak" ||
    key === "recurring" ||
    key === "not_verified" ||
    key === "unstable" ||
    key === "active"
  )
    return "warn";
  if (key === "stable" || key === "verified" || key === "improving") return "good";
  return "neutral";
}

function evidenceMetaLabel(refs) {
  var count = asList(refs).filter(Boolean).length;
  return count > 0 ? count + " 条证据" : "";
}

function abilityDimensionLabel(value) {
  var labels = {
    question_reading: "审题与题干边界",
    code_application: "规范应用",
    calculation: "计算与阈值判断",
    expression: "案例表达",
    transfer: "迁移应用",
    review_execution: "复盘执行",
    recurrence: "同类错误复发",
    explained: "系统解析跟进",
    still_confused: "仍未理解",
  };
  var key = String(value || "").trim();
  return labels[key] || compactLearningTopic(key) || key;
}

function learningStateHeadline(layer, state, label, dimension) {
  var stateKey = String(state || "").trim();
  var dimKey = String(dimension || "").trim();
  if (layer === "knowledge") {
    if (stateKey === "weak") return "需要优先补上";
    if (stateKey === "stable") return "掌握较稳定";
    if (stateKey === "observed") return "刚被系统观察到";
    if (stateKey === "needs_revalidation") return "需要再验证一次";
    return stateLabel(stateKey) || String(label || "知识状态");
  }
  if (layer === "ability") {
    if (stateKey === "weak") return abilityDimensionLabel(dimKey || label) + "还不稳";
    if (stateKey === "stable") return abilityDimensionLabel(dimKey || label) + "较稳定";
    if (stateKey === "needs_revalidation") return abilityDimensionLabel(dimKey || label) + "需要复测";
    return stateLabel(stateKey) || abilityDimensionLabel(dimKey || label);
  }
  if (layer === "behavior") {
    if (stateKey === "recurring") return "同类错误正在复发";
    if (stateKey === "delivered") return "系统已经讲解过";
    if (stateKey === "verified") return "训练效果已验证";
    if (stateKey === "not_verified") return "还没有通过验证";
    if (stateKey === "still_confused") return "仍有疑惑没有解开";
    return stateLabel(stateKey) || abilityDimensionLabel(dimKey || label);
  }
  return stateLabel(stateKey) || String(label || "");
}

function learningStateActionLabel(layer, state, dimension) {
  var stateKey = String(state || "").trim();
  var dimKey = String(dimension || "").trim();
  if (layer === "knowledge") {
    if (stateKey === "weak") return "先回到这一知识点的条件边界";
    if (stateKey === "needs_revalidation") return "用一道新题确认是否还记得";
    return "继续用作答记录稳定这个判断";
  }
  if (layer === "ability") {
    if (dimKey === "question_reading") return "先圈题干限制词，再判断选项";
    if (dimKey === "code_application") return "先定位规范条文和适用条件";
    if (dimKey === "calculation") return "先写清阈值和计算条件";
    if (dimKey === "expression") return "按采分点组织答案表达";
    if (dimKey === "transfer") return "换一个场景再练一次";
    return "用一组短练习把能力补齐";
  }
  if (layer === "behavior") {
    if (stateKey === "recurring") return "今天用同类题验证是否真正改掉";
    if (stateKey === "delivered") return "看完解析后再用新题复测";
    if (stateKey === "not_verified") return "需要完成验证题才能闭环";
    return "继续观察最近几次作答变化";
  }
  return "";
}

function isBlockedSourceStatus(status) {
  var sourceStatus = asObject(status);
  var blockedReason = String(
    sourceStatus.blocked_reason || sourceStatus.reason || "",
  ).trim();
  if (blockedReason) return true;
  if (sourceStatus.degraded === true && blockedReason) return true;
  if (sourceStatus.enabled === false || sourceStatus.feature_enabled === false) return true;
  var stage = String(sourceStatus.stage || sourceStatus.flag_stage || "").trim();
  return stage === "off";
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

function prescriptionTitleLabel(conceptLabel, status) {
  var concept = compactLearningTopic(conceptLabel);
  if (concept) return "围绕「" + concept + "」先完成一轮定向训练";
  return status === "degraded" ? "先来一次起步测评" : "今日先完成一轮定向训练";
}

function evidenceCountLabel(count) {
  var n = asNumber(count, 0);
  return n > 0 ? "基于 " + n + " 条学习证据" : "";
}

function degradedPrescriptionTitle(source, evidenceCount) {
  var directTitle = compactPrescriptionTopic(asObject(source).title || "");
  if (asNumber(evidenceCount, 0) > 0) {
    return directTitle || "补一题可诊断练习";
  }
  return "先来一次起步测评";
}

function degradedPrescriptionCta(evidenceCount) {
  return asNumber(evidenceCount, 0) > 0 ? "补一题诊断" : "先来一次起步测评";
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
  var featureFlags = asObject(body.feature_flags);
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
  var activeSourceCount = sources.filter(function (item) {
    return item.tone === "active";
  }).length;
  var realEvidenceSourceCount = [
    gradingCount,
    conversationCount,
    attemptCount,
    scoringCount,
    behaviorCount,
    graphCount,
    difficultyCount,
  ].filter(function (count) {
    return asNumber(count, 0) > 0;
  }).length;
  var blocked =
    isBlockedSourceStatus(sourceStatus) ||
    isBlockedSourceStatus(asObject(scoringPointMap).sourceStatus) ||
    featureFlags.enabled === false ||
    featureFlags.state_projection === false ||
    featureFlags.action_loop === false;
  var isVisible = !blocked && activeSourceCount > 0 && realEvidenceSourceCount > 0;
  return {
    title: "学习状态推断引擎",
    summary: totalSignalCount
      ? "融合 " + totalSignalCount + " 条历史学习证据"
      : "完成一次批改后开始推断",
    subtitle: "把答题记录、案例解析、采分点、错因与时间信号收束成今日行动",
    sources: isVisible ? sources : [],
    sourceStatus: sourceStatus,
    isEmpty: !isVisible,
    isVisible: isVisible,
  };
}

function normalizeGradingToBrainLoop(source) {
  var src = asObject(source);
  var currentAction = asObject(src.current_action || src.currentAction);
  var latestOutcome = asObject(src.latest_outcome || src.latestOutcome);
  return {
    status: String(src.status || ""),
    nextRequiredAction: String(src.next_required_action || src.nextRequiredAction || ""),
    evidenceRefs: asList(src.evidence_refs || src.evidenceRefs).map(function (ref) {
      return String(ref || "");
    }).filter(Boolean),
    currentAction: {
      title: String(currentAction.title || ""),
      actionType: String(currentAction.action_type || currentAction.actionType || ""),
      prescriptionAuthority: String(
        currentAction.prescription_authority || currentAction.prescriptionAuthority || "",
      ),
    },
    latestOutcome: {
      trainingIntentId: String(latestOutcome.training_intent_id || latestOutcome.trainingIntentId || ""),
      status: String(latestOutcome.status || ""),
      scoreRatio: latestOutcome.score_ratio !== undefined ? latestOutcome.score_ratio : latestOutcome.scoreRatio,
      verifiedAt: String(latestOutcome.verified_at || latestOutcome.verifiedAt || ""),
    },
    stages: asList(src.stages).map(function (stage, index) {
      var item = asObject(stage);
      return {
        key: String(item.key || "stage-" + index),
        label: String(item.label || ""),
        status: String(item.status || ""),
        authority: String(item.authority || ""),
        evidenceCount: asNumber(item.evidence_count || item.evidenceCount, 0),
        evidenceRefs: asList(item.evidence_refs || item.evidenceRefs).map(function (ref) {
          return String(ref || "");
        }).filter(Boolean),
        actionType: String(item.action_type || item.actionType || ""),
        nextRequiredAction: String(item.next_required_action || item.nextRequiredAction || ""),
      };
    }),
    authority: asObject(src.authority),
    sourceStatus: asObject(src.source_status || src.sourceStatus),
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
  var mistakeHistoryCards = normalizeMistakeHistoryCards(attempts);
  // Batch C Task 8: three-layer learning state + scoring point map + today's prescription.
  var learningState = normalizeLearningStateBatchC(body.learning_state);
  mastery = enrichMasteryFromLearningSignals(mastery, body, learningState);
  var radar = normalizeRadar(body.radar_dimensions);
  if (!asList(radar.dims).length) {
    radar = normalizeRadarFromLearningState(learningState);
  }
  var scoringPointMap = normalizeScoringPointMapBatchC(body.scoring_point_map);
  var prescription = normalizePrescriptionBatchC(
    body.training_prescription,
    body.today_prescription,
    nextTraining,
    learningState,
  );
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
    mistakeHistoryCards: mistakeHistoryCards,
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
    gradingToBrainLoop: normalizeGradingToBrainLoop(body.grading_to_brain_loop),
    degraded: Boolean(body.degraded) || degradedSources.length > 0,
    degradedSources: degradedSources,
  };
}

// ─── Batch C Task 8: three-layer learning state + scoring point map ───

function normalizeLearningStateBatchC(state) {
  var src = asObject(state);
  function mapLayer(items, dimensionKey, layer) {
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
      var evidenceRefs = asList(row.evidence_refs).map(function (ref) {
        return String(ref || "");
      });
      return {
        key: String(row[dimensionKey] || row.node_id || "row-" + index),
        nodeId: String(row.node_id || ""),
        dimension: dimension,
        label: label,
        state: state,
        stateLabel: stateLabel(state),
        stateHeadline: learningStateHeadline(layer, state, label, dimension),
        actionLabel: learningStateActionLabel(layer, state, dimension),
        stateTone: stateTone(state),
        evidenceCount: evidenceCount,
        evidenceText: evidenceCountLabel(evidenceCount),
        evidenceRefs: evidenceRefs,
        granularity: String(row.granularity || ""),
        lastObservedAt: String(row.last_observed_at || ""),
      };
    });
  }
  var knowledge = mapLayer(src.knowledge_state, "node_id", "knowledge");
  var ability = mapLayer(src.ability_state, "dimension", "ability");
  var behavior = mapLayer(src.behavior_state, "dimension", "behavior");
  return {
    knowledgeState: knowledge,
    abilityState: ability,
    behaviorState: behavior,
    sourceStatus: asObject(src.source_status),
    isEmpty:
      knowledge.length === 0 && ability.length === 0 && behavior.length === 0,
  };
}

function normalizeRadarFromLearningState(learningState) {
  var abilities = asList(asObject(learningState).abilityState);
  if (!abilities.length) return normalizeRadar([]);
  var dims = abilities.map(function (ability) {
    var evidenceCount = asNumber(ability.evidenceCount, 0);
    var confidence = asNumber(ability.confidence, 0);
    var state = String(ability.state || "");
    var value = 0.4;
    if (state === "stable" || state === "verified") value = 0.78;
    else if (state === "improving") value = 0.62;
    else if (state === "weak" || state === "recurring" || state === "not_verified") value = 0.32;
    if (confidence > 0) value = Math.max(0.1, Math.min(0.95, value * (0.7 + confidence * 0.3)));
    if (evidenceCount <= 0) value = Math.min(value, 0.3);
    var score = Math.round(value * 100);
    return {
      name: ability.label || ability.dimension,
      value: value,
      score: score,
      level: state,
      rateText: score + "%",
    };
  }).filter(function (item) {
    return item.name;
  });
  var strong = dims.filter(function (item) {
    return item.level === "strong" || item.level === "stable" || item.level === "verified";
  }).length;
  var weak = dims.filter(function (item) {
    return ["weak", "unstable", "needs_revalidation", "recurring", "not_verified"].indexOf(item.level) >= 0;
  }).length;
  var avg = dims.length
    ? Math.round(
        dims.reduce(function (sum, item) {
          return sum + item.score;
        }, 0) / dims.length,
      )
    : 0;
  return {
    dims: dims,
    strongCount: strong,
    normalCount: Math.max(0, dims.length - strong - weak),
    weakCount: weak,
    avgScore: avg,
    dimList: dims.map(function (item) {
      return {
        name: item.name,
        score: item.score,
        rateText: item.rateText,
        level: item.level,
      };
    }),
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

function normalizePrescriptionBatchC(source, todayPrescription, nextTraining, learningState) {
  var today = asObject(todayPrescription);
  if (today.title || today.why_this_now || today.primary_action) {
    var todayEvidenceRefs = asList(today.evidence_refs).map(function (ref) {
      return String(ref || "");
    });
    var primaryAction = asObject(today.primary_action);
    return {
      status: today.degraded ? "degraded" : "active",
      title: String(today.title || "今日处方"),
      titleLabel: today.degraded ? "先补证据" : String(today.title || "今日处方"),
      subtitle: String(today.subtitle || ""),
      reason: String(today.why_this_now || ""),
      authority: String(today.prescription_authority || "training_intent"),
      conceptId: "",
      conceptLabel: "",
      abilityDimension: "",
      abilityDimensionLabel: "",
      behaviorState: "",
      behaviorStateLabel: "",
      meta: [
        { key: "source", label: today.source === "dry_run_fallback" ? "临时学情" : "训练意图" },
        { key: "evidence", label: evidenceMetaLabel(todayEvidenceRefs.length) },
      ].filter(function (item) {
        return item.label;
      }),
      evidenceCount: todayEvidenceRefs.length,
      evidenceRefs: today.degraded ? [] : todayEvidenceRefs,
      steps: [],
      successCriteria: {},
      intent: { training_intent_id: String(primaryAction.intent_id || "") },
      ctaLabel: today.degraded ? degradedPrescriptionCta(todayEvidenceRefs.length) : "开始训练",
    };
  }
  var direct = asObject(source);
  var directTopic = compactPrescriptionTopic(
    direct.display_topic || direct.concept_label || "",
  );
  if (direct.source === "training_intent" || direct.status || direct.title) {
    var directStatus = String(direct.status || "degraded");
    if (!directTopic || directStatus === "degraded") directStatus = "degraded";
    var directEvidenceCount = asNumber(
      direct.evidence_count,
      asList(direct.evidence_refs).length,
    );
    var directMeta = [
      direct.error_label,
      evidenceMetaLabel(directEvidenceCount),
    ]
      .filter(Boolean)
      .map(function (label, index) {
        return { key: "meta-" + index, label: String(label || "") };
      });
    return {
      status: directStatus,
      title: String(direct.title || "今日处方"),
      titleLabel:
        directStatus === "degraded"
          ? degradedPrescriptionTitle(direct, directEvidenceCount)
          : prescriptionTitleLabel(directTopic, directStatus),
      subtitle:
        directStatus === "degraded"
          ? String(direct.subtitle || "")
          : String(direct.subtitle || direct.error_label || ""),
      reason:
        directStatus === "degraded"
          ? String(direct.why_this || direct.subtitle || "")
          : String(direct.why_this || ""),
      conceptId: String(direct.concept_id || ""),
      conceptLabel: directTopic,
      abilityDimension: String(direct.ability_dimension || ""),
      abilityDimensionLabel: abilityDimensionLabel(direct.ability_dimension),
      behaviorState: String(direct.behavior_state || ""),
      behaviorStateLabel: stateLabel(direct.behavior_state),
      meta: directMeta,
      evidenceCount: directEvidenceCount,
      evidenceRefs:
        directStatus === "degraded"
          ? []
          : asList(direct.evidence_refs).map(function (ref) {
              return String(ref || "");
            }),
      steps: asList(direct.question_plan || direct.prescription_steps).map(function (
        step,
        index,
      ) {
        var src = asObject(step);
        return {
          key: String(src.phase || "phase-" + index),
          phase: String(src.phase || ""),
          phaseLabel: String(src.phase_label || "") || prescriptionPhaseLabel(src.phase),
          label: String(src.label || "") || prescriptionPhaseLabel(src.phase),
          questionCount: asNumber(src.question_count, 0),
        };
      }),
      successCriteria: asObject(direct.success_criteria),
      intent: asObject(direct.intent),
      ctaLabel: directStatus === "degraded" ? degradedPrescriptionCta(directEvidenceCount) : "开始训练",
    };
  }

  var v2 = null;
  for (var i = 0; i < nextTraining.length; i++) {
    var candidate = asObject(nextTraining[i].intent);
    if (asNumber(candidate.intent_version, 0) === 2) {
      v2 = candidate;
      break;
    }
  }
  if (v2) {
    var conceptLabel = compactPrescriptionTopic(v2.concept_label);
    var status = String(v2.status || "active");
    if (!conceptLabel || status === "degraded") status = "degraded";
    var v2EvidenceCount = asList(v2.evidence_refs).length;
    var behaviorMeta =
      String(v2.behavior_state || "").trim() === "recurring"
        ? "同类错误复发"
        : stateLabel(v2.behavior_state);
    var meta = [
      abilityDimensionLabel(v2.ability_dimension),
      behaviorMeta,
      evidenceMetaLabel(v2.evidence_refs),
    ].filter(Boolean).map(function (label, index) {
      return { key: "meta-" + index, label: label };
    });
    return {
      status: status,
      title: String(v2.concept_label || "今日处方"),
      titleLabel:
        status === "degraded"
          ? degradedPrescriptionTitle(v2, v2EvidenceCount)
          : prescriptionTitleLabel(conceptLabel, status),
      subtitle: status === "degraded" ? "" : String(v2.error_label || v2.reason || ""),
      reason: status === "degraded" ? "" : String(v2.reason || ""),
      conceptId: String(v2.concept_id || ""),
      conceptLabel: conceptLabel,
      abilityDimension: String(v2.ability_dimension || ""),
      abilityDimensionLabel: abilityDimensionLabel(v2.ability_dimension),
      behaviorState: String(v2.behavior_state || ""),
      behaviorStateLabel: stateLabel(v2.behavior_state),
      meta: meta,
      evidenceCount: v2EvidenceCount,
      evidenceRefs:
        status === "degraded"
          ? []
          : asList(v2.evidence_refs).map(function (ref) {
              return String(ref || "");
            }),
      steps: asList(v2.prescription_steps).map(function (step, index) {
        var src = asObject(step);
        return {
          key: String(src.phase || "phase-" + index),
          phase: String(src.phase || ""),
          phaseLabel: prescriptionPhaseLabel(src.phase),
          label: prescriptionPhaseLabel(src.phase),
          questionCount: asNumber(src.question_count, 0),
        };
      }),
      successCriteria: asObject(v2.success_criteria),
      intent: v2,
      ctaLabel: status === "degraded" ? degradedPrescriptionCta(v2EvidenceCount) : "开始训练",
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
    evidenceCount: 0,
    evidenceRefs: [],
    meta: [],
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

function normalizeMistakeHistoryCards(attempts) {
  return asList(attempts)
    .map(function (item, index) {
      var attempt = asObject(item);
      var resultLabel = String(attempt.resultLabel || attempt.result_label || "");
      var tone = String(attempt.tone || "");
      var diagnosis = cleanLearningText(attempt.diagnosis || "");
      var whyWrong = cleanLearningText(
        attempt.diagnosisDetail ||
          attempt.diagnosis_detail ||
          attempt.explanation ||
          attempt.why_it_matters ||
          diagnosis,
      );
      var answerLine = cleanLearningText(attempt.answerLine || attempt.answer_line || "");
      var questionTitle = mistakeQuestionTitle(
        attempt.title ||
          attempt.questionTitle ||
          attempt.question_title ||
          attempt.questionText ||
          attempt.question_text ||
          "一次错题记录",
      );
      var isWrong =
        tone === "wrong" ||
        resultLabel.indexOf("错") >= 0 ||
        resultLabel.indexOf("误") >= 0 ||
        Boolean(diagnosis || whyWrong);
      if (!isWrong) return null;
      return {
        key: String(attempt.key || attempt.attemptKey || "mistake-" + index),
        attemptRef: String(attempt.attemptRef || attempt.attempt_ref || ""),
        timeLabel: String(attempt.timeLabel || attempt.time_label || ""),
        resultLabel: resultLabel || "答错",
        tone: tone || "wrong",
        questionTitle: questionTitle,
        answerLine: answerLine || "当时作答待补充",
        whereWrong: diagnosis || "这道题的作答和标准答案不一致",
        whyWrong: whyWrong || diagnosis || "打开当时解析查看完整讲解",
        detailCta: "查看当时解析",
      };
    })
    .filter(Boolean)
    .slice(0, 3);
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
  var gradingLoop = asObject(vm.gradingToBrainLoop);
  var hasRadar = asList(radar.dims).length > 0;
  var hasMasteryOverall = mastery.hasOverall === true;
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
    overviewScore: hasMasteryOverall
      ? mastery.overall
      : hasRadar
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
    knowledgeSummary: asObject(mastery.knowledgeSummary),
    textbookChapters: asList(asObject(mastery.knowledgeSummary).textbookChapters),
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
    mistakeHistoryCards: asList(vm.mistakeHistoryCards),
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
    engineEvidenceVisible: Boolean(asObject(vm.evidenceEngine).isVisible),
    gradingLoopStatus: String(gradingLoop.status || ""),
    gradingLoopNextRequiredAction: String(gradingLoop.nextRequiredAction || ""),
    gradingLoopEvidenceRefs: asList(gradingLoop.evidenceRefs),
    gradingLoopCurrentAction: asObject(gradingLoop.currentAction),
    gradingLoopLatestOutcome: asObject(gradingLoop.latestOutcome),
    gradingLoopStages: asList(gradingLoop.stages),
    gradingLoopAuthority: asObject(gradingLoop.authority),
    gradingLoopSourceStatus: asObject(gradingLoop.sourceStatus),
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
    prescriptionTopic: String(asObject(vm.prescription).conceptLabel || ""),
    prescriptionMeta: asList(asObject(vm.prescription).meta),
    prescriptionSteps: asList(asObject(vm.prescription).steps),
    prescriptionCtaLabel: String(asObject(vm.prescription).ctaLabel || ""),
    prescriptionEvidenceCount: asNumber(asObject(vm.prescription).evidenceCount, 0),
    prescriptionEvidenceRefs: asList(asObject(vm.prescription).evidenceRefs),
    prescriptionAuthority: String(asObject(vm.prescription).authority || ""),
  };
}

module.exports = {
  buildLearningReportViewModel: buildLearningReportViewModel,
  toReportPageData: toReportPageData,
};
