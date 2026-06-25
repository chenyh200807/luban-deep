// pages/assessment/assessment.js — 摸底测试

var api = require("../../utils/api");
var route = require("../../utils/route");
var runtime = require("../../utils/runtime");
var taxonomy = require("../../utils/taxonomy");

var LEVEL_NAMES = {
  beginner: "入门",
  intermediate: "中级",
  advanced: "进阶",
  expert: "精通",
};

var ARCHETYPE_ICONS = {
  strategist: "S",
  explorer: "E",
  sprinter: "F",
  builder: "B",
  policy_seeded: "智",
};
var ARCHETYPE_COLORS = {
  strategist: "#3b82f6",
  explorer: "#8b5cf6",
  sprinter: "#f59e0b",
  builder: "#22c55e",
  policy_seeded: "#3b82f6",
};
var RESPONSE_LABELS = {
  fluent: "流畅型",
  deliberate: "审慎型",
  impulsive: "冲动型",
  struggling: "困难型",
};
var RESPONSE_DESCS = {
  fluent: "你答题速度快且准确率高，知识掌握扎实，能快速调取记忆。",
  deliberate:
    "你倾向深思熟虑后作答，虽然速度较慢但准确率很高，属于稳扎稳打型。",
  impulsive: "你答题速度较快但容易出错，建议放慢节奏，仔细审题后再选择。",
  struggling: "部分知识点掌握不够牢固，建议从基础章节开始系统复习。",
};
var CALIBRATION_LABELS = {
  overconfident: "偏乐观",
  accurate: "很准确",
  underconfident: "偏保守",
};

// 客户端 fallback 画像数据
var ARCHETYPE_NAMES = {
  strategist: "策略型学员",
  explorer: "探索型学员",
  sprinter: "冲刺型学员",
  builder: "基础型学员",
  policy_seeded: "动态调节型学员",
};
var ARCHETYPE_DESCS = {
  strategist:
    "你注重效率与结果，善于规划学习路径，习惯用数据驱动决策。面对考试，你会优先攻克高权重考点，用最少的时间获取最大的分数收益。",
  explorer:
    "你拥有强烈的求知欲，喜欢深入理解知识背后的逻辑和原理。你不满足于死记硬背，而是追求真正的融会贯通。",
  sprinter:
    "你目标明确、执行力强，擅长在压力下高效产出。你喜欢集中火力攻克重点，在冲刺阶段爆发力惊人。",
  builder:
    "你做事扎实稳健，喜欢循序渐进地构建知识体系。你相信万丈高楼平地起，基础打牢了后面的学习自然水到渠成。",
  policy_seeded:
    "系统会根据你的知识得分、学习习惯和作答节奏动态调整讲解、练习与复盘方式。",
};
var ARCHETYPE_TRAITS = {
  strategist: ["目标导向", "高效执行", "数据驱动", "善于规划"],
  explorer: ["求知欲强", "深度学习", "融会贯通", "知识整合"],
  sprinter: ["执行力强", "重点突破", "抗压力好", "目标明确"],
  builder: ["扎实稳健", "循序渐进", "基础牢固", "持之以恒"],
  policy_seeded: ["动态调节", "节奏适配", "分步推进", "复盘巩固"],
};
var ARCHETYPE_TIPS = {
  strategist:
    "建议按考试权重分配精力，优先攻克高频考点。利用错题数据精准定位薄弱环节，避免低效重复。",
  explorer:
    "建议均衡覆盖各章节，重点关注知识点之间的联系。用思维导图串联知识体系，让零散知识形成网络。",
  sprinter:
    "建议聚焦高权重章节和历年高频考点，通过大量刷题建立题感。考前一个月进入模拟考试密集训练。",
  builder:
    "建议从基础章节开始，确保每个概念理解透彻后再进入下一个。用工地实际场景帮助记忆，让知识落地。",
  policy_seeded: "建议按当前诊断结果先补薄弱章节，再用短组练习和固定复盘巩固。",
};

var ASSESSMENT_I18N_KEYS = {
  scoreTitle: "本次专题测评得分",
  topicLabel: "防水专题测评",
  deepExplanationUnavailable: "详细解析下个版本上线",
  resultNextActionFallback: "根据本次测评更新训练计划中，前往学习计划查看。",
  degraded: {
    writeback_failed: "本次得分已生成，错题写入学习记录时遇到问题，系统会稍后重试。",
    scoring_partial: "本次报告生成不完整，请稍后刷新查看。",
    source_redaction_failed: "本次题目数据校验未通过，报告暂不可作为正式结果。",
    unknown: "本次报告有部分信息未完成同步，请稍后刷新查看。",
  },
  readOnlyOtherDevice: "这份测评正在另一台设备作答，本机仅可查看。",
};

var DEFAULT_TOPIC_CATALOG = [
  {
    topic_id: "waterproof",
    label: "防水工程",
    short_label: "防水",
    description: "材料构造、施工节点、质量验收",
    status: "stable",
    enabled: true,
    form_count: 5,
  },
];

function buildWelcomeModeState(mode, topicLabel, topicFormCount) {
  var normalizedMode = mode === "topic" ? "topic" : "diagnostic";
  if (normalizedMode === "topic") {
    return {
      assessmentMode: "topic",
      welcomeTitle: String(topicLabel || "专题") + "专题测评",
      welcomeSub: "一口气完成专题卷，提交后统一查看得分和错题",
      welcomeQuestionCount: 12,
      welcomeQuestionLabel: "专题题目",
      welcomeDuration: 8,
      welcomeFormCount: Number(topicFormCount || 5) || 5,
    };
  }
  return {
    assessmentMode: "diagnostic",
    welcomeTitle: "综合摸底",
    welcomeSub: "20 题综合校准，提交后统一查看能力结构和错题",
    welcomeQuestionCount: 20,
    welcomeQuestionLabel: "综合题目",
    welcomeDuration: 12,
    welcomeFormCount: 5,
  };
}

var helpers = require("../../utils/helpers");

function buildAnswerState(questions, selectedKeys, currentIndex) {
  var sheet = [];
  var answeredCount = 0;
  var keys = selectedKeys || {};
  for (var i = 0; i < questions.length; i++) {
    var q = questions[i];
    var answered = !!keys[q.id];
    if (answered) answeredCount += 1;
    sheet.push({
      id: q.id,
      index: i,
      number: i + 1,
      answered: answered,
      current: i === currentIndex,
    });
  }
  return {
    answerSheet: sheet,
    answeredCount: answeredCount,
    unansweredCount: questions.length - answeredCount,
  };
}

function normalizeOptionText(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .toLowerCase();
}

function isInlineOptionLine(line, options) {
  var match = /^([A-Z])\s*[\.．、\)]\s*(.+)$/i.exec(String(line || "").trim());
  if (!match) return false;
  var key = String(match[1] || "").toUpperCase();
  var body = normalizeOptionText(match[2]);
  for (var i = 0; i < options.length; i++) {
    var opt = options[i] || {};
    if (String(opt.key || "").toUpperCase() !== key) continue;
    return (
      body === normalizeOptionText(opt.text) ||
      body === normalizeOptionText(opt.value)
    );
  }
  return false;
}

function stripInlineOptionsFromStem(stem, options) {
  var text = String(stem || "").trim();
  var opts = options || [];
  if (!text || !opts.length) return text;

  var keptLines = text
    .split(/\r?\n/)
    .filter(function (line) {
      return !isInlineOptionLine(line, opts);
    });
  text = keptLines.join("\n").trim();

  var markerCount = 0;
  var firstMarker = -1;
  opts.forEach(function (opt) {
    var key = String((opt || {}).key || "").toUpperCase();
    if (!key) return;
    var marker = new RegExp("(^|\\s)" + key + "\\s*[\\.．、\\)]\\s+", "i");
    var match = marker.exec(text);
    if (!match) return;
    markerCount += 1;
    var index = match.index + (match[1] ? match[1].length : 0);
    if (firstMarker < 0 || index < firstMarker) firstMarker = index;
  });
  if (markerCount >= 2 && firstMarker > 0) {
    text = text.slice(0, firstMarker).trim();
  }
  return text;
}

function normalizeAssessmentOptions(rawOptions) {
  var opts = rawOptions || [];
  if (Array.isArray(opts)) {
    return opts.map(function (o) {
      return {
        key: String((o || {}).key || ""),
        text: String((o || {}).text || (o || {}).label || (o || {}).value || ""),
        value: String((o || {}).value || ""),
      };
    });
  }
  return Object.keys(opts)
    .sort()
    .map(function (k) {
      return { key: k, text: String(opts[k] || ""), value: "" };
    });
}

function normalizeAssessmentQuestions(rawQuestions) {
  var rows = Array.isArray(rawQuestions) ? rawQuestions : [];
  return rows
    .map(function (q, idx) {
      if (!q || typeof q !== "object") return null;
      var opts = normalizeAssessmentOptions(q.options || []);
      var stem = q.question_stem || q.stem || q.text || q.content || "";
      return {
        id: q.question_id || q.id || "q_" + (idx + 1),
        question_stem: stripInlineOptionsFromStem(stem, opts),
        options: opts,
        question_type: q.question_type || "single_choice",
        difficulty: q.difficulty || "",
        section_id: q.section_id || "",
        section_label: q.section_label || "",
        scored: q.scored !== false,
      };
    })
    .filter(function (q) {
      return !!(q && q.id && q.question_stem);
    });
}

function displayChapterName(value) {
  return taxonomy.displayChapterName(value, "综合能力");
}

function hasExplicitValue(value) {
  return value !== undefined && value !== null && value !== "";
}

function pickNumber(primary, fallback) {
  var value = hasExplicitValue(primary) ? primary : fallback;
  var parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function learnerSafeDegradedCopy(reason) {
  var key = String(reason || "").trim();
  return ASSESSMENT_I18N_KEYS.degraded[key] || ASSESSMENT_I18N_KEYS.degraded.unknown;
}

var ASSESSMENT_DEVICE_ID_KEY = "deeptutor.assessment.deviceId";

function getAssessmentDeviceId() {
  var fallback =
    "wx_assessment_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 10);
  if (typeof wx === "undefined") return fallback;
  try {
    if (typeof wx.getStorageSync === "function") {
      var stored = String(wx.getStorageSync(ASSESSMENT_DEVICE_ID_KEY) || "").trim();
      if (stored) return stored.slice(0, 128);
    }
    if (typeof wx.setStorageSync === "function") {
      wx.setStorageSync(ASSESSMENT_DEVICE_ID_KEY, fallback);
    }
  } catch (err) {
    return fallback;
  }
  return fallback;
}

function assessmentCreateErrorCopy(err) {
  var fallback = "加载题目失败，请稍后重试";
  if (!api.describeRequestError) return fallback;
  return api.describeRequestError(err, fallback, {
    context: "assessment_create",
    customMap: function (info) {
      var payloadDetail =
        info && info.payload && info.payload.detail && typeof info.payload.detail === "object"
          ? info.payload.detail
          : {};
      var errorCode = String(payloadDetail.error || info.detailText || "");
      if (errorCode.indexOf("assessment_sessions_unavailable") >= 0) {
        return "题库服务暂时不可用，请稍后重试";
      }
      if (errorCode.indexOf("assessment_blueprint_unavailable") >= 0) {
        return "当前题库暂不足以生成本次测评，请稍后再试";
      }
      if (errorCode.indexOf("assessment_session_expired") >= 0) {
        return "本次测评已过期，请重新开始";
      }
      if (errorCode.indexOf("assessment_lease_conflict") >= 0) {
        return "这份测评正在另一台设备作答";
      }
      return "";
    },
  });
}

function normalizeTopicCatalog(items) {
  var topics = (items || []).map(function (item) {
    var status = String(item.status || "authoring_needed");
    var formCount = Number(item.form_count || 0) || 0;
    return {
      topicId: String(item.topic_id || ""),
      label: String(item.label || item.short_label || "专题测评"),
      shortLabel: String(item.short_label || item.label || "专题"),
      description: String(item.description || ""),
      status: status,
      enabled: status === "authoring_needed" ? false : item.enabled === true || status === "stable" || status === "pilot",
      formCount: formCount,
      statusLabel:
        status === "stable"
          ? formCount + " 套稳定"
          : status === "pilot"
            ? formCount + " 套试运行"
            : "待补题",
    };
  });
  if (!topics.length) topics = normalizeTopicCatalog(DEFAULT_TOPIC_CATALOG);
  return topics;
}

function markRecommendedTopic(catalog, topicId) {
  return (catalog || []).map(function (item) {
    return Object.assign({}, item, {
      recommended: !!topicId && item.topicId === topicId,
    });
  });
}

function normalizeAssessmentRecommendation(value) {
  var rec = value || {};
  var mode = String(rec.recommended_mode || "diagnostic");
  return {
    recommendedMode: mode === "topic" ? "topic" : "diagnostic",
    recommendedTopicId: String(rec.recommended_topic_id || ""),
    recommendedCount: Number(rec.recommended_count || (mode === "topic" ? 12 : 20)) || 20,
    reason: String(rec.reason || ""),
    source: String(rec.source || ""),
    confidence: String(rec.confidence || ""),
  };
}

function normalizeKnowledgeMap(items) {
  return (items || []).map(function (item) {
    return {
      name: String(item.knowledge_point || item.name || "综合能力"),
      attempted: Number(item.attempted || 0),
      correct: Number(item.correct || 0),
      pct: Math.max(0, Math.min(100, Number(item.score_pct || item.pct || 0))),
    };
  });
}

function attemptRefByQuestion(attemptRefs) {
  var map = {};
  (attemptRefs || []).forEach(function (item) {
    if (!item || !item.question_id) return;
    map[String(item.question_id)] = String(item.attempt_ref || "");
  });
  return map;
}

function answerToMap(value) {
  var map = {};
  String(value || "")
    .split("")
    .forEach(function (key) {
      if (key) map[key] = true;
    });
  return map;
}

function confidenceLabel(value) {
  var level = String((value || {}).level || value || "").toLowerCase();
  if (level === "high") return "高";
  if (level === "medium") return "中等";
  if (level === "low") return "较低";
  return "中等";
}

function scoreStatusLabel(score) {
  var value = Number(score || 0);
  if (value >= 80) return "保持";
  if (value >= 60) return "巩固";
  return "待补弱";
}

function resultShortcomingLabel(wrongItems) {
  var hasMultiMiss = (wrongItems || []).some(function (item) {
    return String(item.issueType || "").indexOf("漏选") >= 0;
  });
  return hasMultiMiss ? "多选漏选 + 条件漏读" : "条件漏读 + 概念混淆";
}

function resultDiagnosisTitle(wrongItems) {
  if ((wrongItems || []).length) return "主要问题不是不会，而是规范条件读不全";
  return "本次基础表现稳定，下一步做短组巩固";
}

function buildAssessmentQuestionMap(questions) {
  var map = {};
  (questions || []).forEach(function (question) {
    if (!question || !question.id) return;
    map[String(question.id)] = question;
  });
  return map;
}

function buildAnswerDelta(learnerAnswer, correctAnswer) {
  var learner = answerToMap(learnerAnswer);
  var correct = answerToMap(correctAnswer);
  var missed = [];
  var extra = [];
  Object.keys(correct).forEach(function (key) {
    if (!learner[key]) missed.push(key);
  });
  Object.keys(learner).forEach(function (key) {
    if (!correct[key]) extra.push(key);
  });
  return {
    missed: missed,
    extra: extra,
    label:
      missed.length && extra.length
        ? "漏选 " + missed.join("/") + " · 多选 " + extra.join("/")
        : missed.length
          ? "漏选 " + missed.join("/")
          : extra.length
            ? "多选 " + extra.join("/")
            : "待复盘",
  };
}

function buildOptionReview(options, learnerAnswer, correctAnswer) {
  var learner = answerToMap(learnerAnswer);
  var correct = answerToMap(correctAnswer);
  return (options || []).map(function (option) {
    var key = String(option.key || "");
    var chosen = !!learner[key];
    var isCorrect = !!correct[key];
    return {
      key: key,
      text: String(option.text || ""),
      statusClass: isCorrect ? (chosen ? "correct" : "missed") : chosen ? "extra" : "",
      statusLabel: isCorrect ? (chosen ? "已选" : "漏选") : chosen ? "多选" : "",
      review: isCorrect
        ? chosen
          ? "这项属于正确判断。"
          : "这项也是正确项，本次漏选。"
        : chosen
          ? "这项不符合题干限定，本次多选。"
          : "这项不是本题采分点。",
    };
  });
}

function buildSimpleReview(item, delta) {
  var base = String(item.simple_explanation || item.explanation || "").trim();
  if (base) {
    var normalized = base.replace(/^简单解析[:：]/, "解析：").replace(/^解析[:：]/, "解析：");
    return normalized.indexOf("解析：") === 0 ? normalized : "解析：" + normalized;
  }
  if (delta && delta.missed && delta.missed.length) {
    return "解析：这题考完整枚举。你漏掉了 " + delta.missed.join("/") + " 项，需要按题干条件逐项判断。";
  }
  return "解析：这题需要先圈出题干限定词，再逐项核对选项是否符合。";
}

function buildWrongDetail(item, delta, options) {
  var keyTerms = (item.knowledge_points || []).slice(0, 3);
  if (!keyTerms.length) keyTerms = ["题干限定", "正确选项", "规范表达"];
  return {
    keyTerms: keyTerms,
    whyWrong:
      delta && delta.missed && delta.missed.length
        ? "你的判断停在最确定的选项，但这类题要看完整枚举。本题漏掉了 " + delta.missed.join("/") + " 项。"
        : "你的答案和标准答案存在差异，需要回到题干限定词和选项边界逐项核对。",
    cause:
      "这类题常见问题是先凭关键词选一个最像的答案，没有把部位、材料、施工阶段或规范限定全部圈出来。",
    scoringPoints:
      "采分点是完整识别题干限定范围，并能判断每个选项是否同属该范围。",
    pitfall: "不要只找最像关键词的选项；多选题要逐项排除，避免保守漏选。",
    mnemonic:
      options && options.length >= 4
        ? "先圈题干限定，再按 A/B/C/D 逐项核对：同类保留，越界排除。"
        : "先圈限定，再看边界。",
    source: "来源：题库解析、知识卡和相关规范条文。正式数据会回链到可追溯依据。",
  };
}

function normalizeGeneratedOptionReviews(rows, fallbackRows) {
  var list = Array.isArray(rows) ? rows : [];
  var normalized = list
    .map(function (row) {
      var key = String(row && row.key ? row.key : "").toUpperCase();
      var status = String(row && row.status ? row.status : "");
      return {
        key: key,
        text: "",
        statusClass:
          status.indexOf("miss") >= 0 || status.indexOf("漏") >= 0
            ? "missed"
            : status.indexOf("extra") >= 0 || status.indexOf("错") >= 0 || status.indexOf("多") >= 0
              ? "extra"
              : status.indexOf("correct") >= 0 || status.indexOf("对") >= 0
                ? "correct"
                : "",
        statusLabel: String((row && (row.status_label || row.statusLabel)) || ""),
        review: String(row && row.review ? row.review : ""),
      };
    })
    .filter(function (row) {
      return row.key && row.review;
    });
  return normalized.length ? normalized : fallbackRows || [];
}

function normalizeGeneratedDetail(payload, fallbackItem) {
  var explanation = payload && payload.explanation ? payload.explanation : {};
  var fallbackDetail = fallbackItem && fallbackItem.detail ? fallbackItem.detail : {};
  var keyTerms = Array.isArray(explanation.key_terms)
    ? explanation.key_terms
    : Array.isArray(explanation.knowledge_points)
      ? explanation.knowledge_points
      : fallbackDetail.keyTerms || [];
  var billing = payload && payload.billing ? payload.billing : {};
  var capturedPoints = Number(billing.captured_points || billing.amount_points || 0);
  return {
    detail: {
      keyTerms: keyTerms.filter(function (item) { return String(item || "").trim(); }).slice(0, 6),
      whyWrong: String(explanation.why_wrong || fallbackDetail.whyWrong || "AI 已生成解析，但本题没有返回明确错因。"),
      cause: String(explanation.cause_analysis || fallbackDetail.cause || ""),
      scoringPoints: String(explanation.scoring_points || fallbackDetail.scoringPoints || ""),
      pitfall: String(explanation.pitfall || fallbackDetail.pitfall || ""),
      mnemonic: String(explanation.mnemonic || fallbackDetail.mnemonic || ""),
      source: String(explanation.source_basis || fallbackDetail.source || ""),
    },
    explanation: explanation.summary ? "解析：" + String(explanation.summary).replace(/^解析[:：]/, "") : fallbackItem.explanation,
    optionReviews: normalizeGeneratedOptionReviews(explanation.option_reviews, fallbackItem.optionReviews),
    detailBilling: capturedPoints > 0 ? "本次消耗 " + capturedPoints + " 点" : "",
  };
}

function buildWrongIssueType(item, delta) {
  if (delta && delta.missed && delta.missed.length) return "多选题漏选";
  var codes = (item.error_codes || []).join(" ");
  if (codes.indexOf("M01") >= 0) return "规范条件读不全";
  if (codes.indexOf("M02") >= 0) return "概念混淆";
  return "条件漏读";
}

function normalizeWrongItems(items, attemptRefs, questions) {
  var refMap = attemptRefByQuestion(attemptRefs);
  var questionMap = buildAssessmentQuestionMap(questions);
  return (items || []).map(function (item, index) {
    var questionId = String(item.question_id || "");
    var question = questionMap[questionId] || {};
    var options = normalizeAssessmentOptions(item.options || question.options || []);
    var learnerAnswer = String(item.learner_answer || "");
    var correctAnswer = String(item.correct_answer || "");
    var delta = buildAnswerDelta(learnerAnswer, correctAnswer);
    var issueType = buildWrongIssueType(item, delta);
    return {
      index: index + 1,
      questionId: questionId,
      stem: String(item.question_stem || item.stem || "错题 " + (index + 1)),
      learnerAnswer: learnerAnswer,
      correctAnswer: correctAnswer,
      options: options,
      answerDelta: delta,
      issueType: issueType,
      issueBadge: delta.label || issueType,
      explanation: buildSimpleReview(item, delta),
      expanded: false,
      detailStatus: "idle",
      detailStatusText: "点击后生成",
      detailError: "",
      detailBilling: "",
      optionReviews: buildOptionReview(options, learnerAnswer, correctAnswer),
      detail: buildWrongDetail(item, delta, options),
      knowledgePoints: item.knowledge_points || [],
      errorCodes: item.error_codes || [],
      attemptRef: String(item.attempt_ref || refMap[questionId] || ""),
    };
  });
}

function buildWrongItemFollowupQuestionContext(item, quizId) {
  var source = item || {};
  var optionMap = {};
  var options = Array.isArray(source.options) ? source.options : [];
  for (var i = 0; i < options.length; i++) {
    var option = options[i] || {};
    var key = String(option.key || "").trim().toUpperCase();
    var text = String(option.text || option.value || "").trim();
    if (key && text) optionMap[key] = text;
  }
  var context = {
    parent_quiz_session_id: String(quizId || "").trim(),
    question_id: String(source.questionId || "").trim(),
    question: String(source.stem || "").trim(),
    question_type: "choice",
    options: optionMap,
    user_answer: String(source.learnerAnswer || "").trim(),
    correct_answer: String(source.correctAnswer || "").trim(),
    explanation: String(source.explanation || "").trim(),
    reveal_answers: true,
    reveal_explanations: true,
  };
  if (!context.question && !context.question_id) return null;
  return context;
}

function buildIssueSummary(wrongItems) {
  if (!(wrongItems || []).length) return [];
  var presets = [
    { title: "多选题漏选", desc: "只选最确定选项，漏掉并列条件", count: 0 },
    { title: "规范条件读不全", desc: "忽略高度、部位、材料、施工阶段限定", count: 0 },
    { title: "材料性能分类混淆", desc: "力学性能、耐久性能、施工性能边界不清", count: 0 },
    { title: "题干关键词没抓住", desc: "没有先圈部位、阶段、性能、规范限定", count: 0 },
    { title: "相似概念边界不清", desc: "把施工性能、材料性能、验收要求混在一起", count: 0 },
  ];
  (wrongItems || []).forEach(function (item) {
    var type = String(item.issueType || "");
    var matched = presets.find(function (preset) {
      return preset.title === type || type.indexOf(preset.title.replace("题", "")) >= 0;
    });
    if (!matched) matched = presets[3];
    matched.count += 1;
  });
  return presets.map(function (item, index) {
    return {
      rank: index + 1,
      title: item.title,
      desc: item.desc,
      count: item.count || (index < 3 ? Math.max(1, (wrongItems || []).length - index) : 0),
      countLabel: (item.count || (index < 3 ? Math.max(1, (wrongItems || []).length - index) : 0)) + "题",
    };
  });
}

function buildActionKnowledgeMap(knowledgeMap) {
  return (knowledgeMap || [])
    .slice()
    .sort(function (a, b) {
      return Number(a.pct || 0) - Number(b.pct || 0);
    })
    .slice(0, 3)
    .map(function (item, index) {
    return Object.assign({}, item, {
      actionLabel: index === 0 ? "优先补" : index === 1 ? "次优先" : "暂保持",
      actionClass: index === 0 ? "risk" : index === 1 ? "gold" : "good",
    });
  });
}

function buildPrescriptionSteps() {
  return [
    { index: 1, title: "看 2 道代表错题讲评", desc: "重点看漏选和条件判断", time: "2分" },
    { index: 2, title: "练 3 道同类多选题", desc: "只练最低掌握点", time: "4分" },
    { index: 3, title: "做 1 道验证题", desc: "确认是否还会漏选", time: "2分" },
    { index: "✓", title: "完成后自动更新学习记录", desc: "错题本和掌握地图会同步刷新", time: "自动" },
  ];
}

function buildP0AResultModel(report, questions) {
  var summary = report.score_summary || {};
  var deep = report.deep_explanation || {};
  var degradedReason = String(report.degraded_reason || "");
  var writeback = report.writeback_status || {};
  if (!degradedReason && writeback.status === "degraded") degradedReason = String(writeback.reason || "");
  var attemptRefs = report.attempt_refs || [];
  var score = pickNumber(summary.score_pct, 0);
  var knowledgeMap = normalizeKnowledgeMap(report.knowledge_map || []);
  var wrongItems = normalizeWrongItems(report.wrong_items || [], attemptRefs, questions);
  var confidence = report.measurement_confidence || {};
  return {
    serverReportMode: true,
    reportSchemaVersion: String(report.schema_version || ""),
    scoreTitle: String(report.score_title || ASSESSMENT_I18N_KEYS.scoreTitle),
    topicLabel: String(report.topic_label || ASSESSMENT_I18N_KEYS.topicLabel),
    resultScore: score,
    scoreStatusLabel: scoreStatusLabel(score),
    resultDiagnosisTitle: resultDiagnosisTitle(wrongItems),
    resultShortcoming: resultShortcomingLabel(wrongItems),
    resultConfidenceLabel: confidenceLabel(confidence),
    resultEvidenceCount: Number(summary.scored_count || summary.answered_count || 0) || 0,
    resultPrescriptionStatus: "可执行",
    correctCount: Number(summary.correct_count || 0),
    scoredCount: Number(summary.scored_count || 0),
    answeredCount: Number(summary.answered_count || 0),
    blankCount: Number(summary.blank_count || 0),
    measurementConfidence: confidence,
    knowledgeMap: knowledgeMap,
    actionKnowledgeMap: buildActionKnowledgeMap(knowledgeMap),
    wrongItems: wrongItems,
    issueSummary: buildIssueSummary(wrongItems),
    prescriptionSteps: buildPrescriptionSteps(),
    attemptRefs: attemptRefs,
    sessionLocalNextAction:
      (report.session_local_next_action && report.session_local_next_action.copy) ||
      ASSESSMENT_I18N_KEYS.resultNextActionFallback,
    deepExplanationAvailable: !!deep.available,
    deepExplanationCopy: String(deep.copy || ASSESSMENT_I18N_KEYS.deepExplanationUnavailable),
    degradedReason: degradedReason,
    degradedCopy: degradedReason ? learnerSafeDegradedCopy(degradedReason) : "",
    archetype: "",
    archetypeName: "",
    archetypeDesc: "",
    archetypeTraits: [],
    archetypeTip: "",
    responseLabel: "",
    responseDesc: "",
    calibrationLabel: "",
    errorPattern: "",
    errorPatternName: "",
    chapterList: [],
    priorityChapters: [],
    planStrategy: "",
  };
}

function buildSubmitSuccessFallbackModel(data) {
  var payload = data || {};
  var summary = payload.score_summary || {};
  var feedback = payload.diagnostic_feedback || payload.feedback || {};
  var ability = feedback.ability_overview || {};
  var actionPlan = feedback.action_plan || {};
  var score = pickNumber(summary.score_pct, pickNumber(ability.score_pct, payload.score));
  var level = String(payload.suggested_level || payload.level || "beginner");
  var plan = String(actionPlan.plan_strategy || "");
  return {
    serverReportMode: false,
    reportSchemaVersion: String(payload.schema_version || payload.blueprint_version || ""),
    scoreTitle: String(payload.score_title || ASSESSMENT_I18N_KEYS.scoreTitle),
    topicLabel: String(payload.topic_label || "综合摸底"),
    resultScore: score,
    resultLevel: level,
    resultLevelName: LEVEL_NAMES[level] || level,
    chapterList: [],
    knowledgeMap: [],
    actionKnowledgeMap: [],
    wrongItems: [],
    issueSummary: [],
    prescriptionSteps: [],
    priorityChapters: [],
    archetype: "",
    archetypeName: "动态调节型学员",
    archetypeDesc: "",
    archetypeTraits: [],
    archetypeTip: "",
    responseLabel: "待继续观察",
    responseDesc: "",
    calibrationLabel: "",
    errorPattern: "",
    errorPatternName: "待继续观察",
    degradedCopy: "本次已成功提交，学情和错题记录已同步；结果展示暂时简化，请稍后从学情页查看完整记录。",
    planStrategy:
      "本次已成功提交，学情和错题记录已同步。" +
      (plan ? " " + plan : " 结果展示暂时简化，请稍后从学情页查看完整记录。"),
  };
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    stage: "welcome", // welcome | quiz | loading | result
    questions: [],
    currentIndex: 0,
    currentQ: null,
    selMap: {}, // { "qId_A": true, "qId_C": true } — WXML 渲染用
    selectedKeys: {}, // { qId: "A" or "AC" } — 提交用
    answerSheet: [],
    answeredCount: 0,
    unansweredCount: 0,
    requestedCount: 0,
    deliveredCount: 0,
    scoredCount: 0,
    profileCount: 0,
    blueprintVersion: "",
    availableCount: 0,
    shortfallCount: 0,
    assessmentNotice: "",
    assessmentMode: "diagnostic",
    welcomeTitle: "综合摸底",
    welcomeSub: "20 题综合校准，提交后统一查看能力结构和错题",
    welcomeQuestionCount: 20,
    welcomeQuestionLabel: "综合题目",
    welcomeDuration: 12,
    welcomeFormCount: 5,
    topicCatalog: normalizeTopicCatalog(DEFAULT_TOPIC_CATALOG),
    selectedTopicId: "waterproof",
    selectedTopicLabel: "防水工程",
    selectedTopicStatus: "stable",
    selectedTopicFormCount: 5,
    topicCatalogError: "",
    recommendedMode: "diagnostic",
    recommendedTopicId: "",
    assessmentRecommendationReason: "",
    assessmentModeTouched: false,
    assessmentTopicTouched: false,
    serverReportMode: false,
    reportSchemaVersion: "",
    scoreTitle: ASSESSMENT_I18N_KEYS.scoreTitle,
    topicLabel: ASSESSMENT_I18N_KEYS.topicLabel,
    resultScore: 0,
    resultLevel: "beginner",
    resultLevelName: "入门",
    chapterList: [],
    knowledgeMap: [],
    actionKnowledgeMap: [],
    wrongItems: [],
    issueSummary: [],
    prescriptionSteps: [],
    attemptRefs: [],
    correctCount: 0,
    blankCount: 0,
    measurementConfidence: {},
    sessionLocalNextAction: "",
    deepExplanationAvailable: false,
    deepExplanationCopy: ASSESSMENT_I18N_KEYS.deepExplanationUnavailable,
    degradedReason: "",
    degradedCopy: "",
    readOnlyBanner: "",
    // 学员画像
    archetype: "",
    archetypeName: "",
    archetypeDesc: "",
    archetypeTraits: [],
    archetypeTip: "",
    archetypeColor: "",
    archetypeIcon: "",
    // 认知画像
    responseLabel: "",
    responseDesc: "",
    calibrationLabel: "",
    // 错误模式
    errorPattern: "",
    errorPatternName: "",
    // 行动计划
    priorityChapters: [],
    planStrategy: "",
  },

  _quizId: null,
  _startTime: 0,

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
      isDark: helpers.isDark(),
      enableOrbs: helpers.getAnimConfig().enableBreathingOrbs,
    });
    this.loadTopicCatalog();
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
  },

  loadTopicCatalog: function () {
    var self = this;
    if (!api.getAssessmentTopics) return;
    api
      .getAssessmentTopics({ noRetry: true })
      .then(function (resp) {
        var payload = resp.data || resp || {};
        var recommendation = normalizeAssessmentRecommendation(payload.recommendation || {});
        var catalog = markRecommendedTopic(
          normalizeTopicCatalog(payload.topics || []),
          recommendation.recommendedTopicId,
        );
        var selected =
          self.data.assessmentTopicTouched
            ? catalog.find(function (item) {
                return item.enabled && item.topicId === self.data.selectedTopicId;
              })
            : null;
        if (!selected) {
          selected =
            catalog.find(function (item) {
              return item.enabled && item.topicId === recommendation.recommendedTopicId;
            }) ||
            catalog.find(function (item) {
              return item.enabled;
            }) ||
            catalog[0];
        }
        var recommendedMode =
          recommendation.recommendedMode === "topic" && selected && selected.topicId === recommendation.recommendedTopicId
            ? "topic"
            : "diagnostic";
        var nextMode = self.data.assessmentModeTouched ? self.data.assessmentMode : recommendedMode;
        self.setData(
          Object.assign(
            {
              topicCatalog: catalog,
              selectedTopicId: selected.topicId,
              selectedTopicLabel: selected.label,
              selectedTopicStatus: selected.status,
              selectedTopicFormCount: selected.formCount,
              topicCatalogError: "",
              recommendedMode: recommendedMode,
              recommendedTopicId: recommendation.recommendedTopicId,
              assessmentRecommendationReason: recommendation.reason,
            },
            buildWelcomeModeState(nextMode, selected.label, selected.formCount),
          ),
        );
      })
      .catch(function () {
        self.setData({
          topicCatalog: normalizeTopicCatalog([]),
          topicCatalogError: "专题目录暂时不可用",
        });
      });
  },

  onSelectTopic: function (e) {
    var topicId = String((e.currentTarget.dataset || {}).topicId || "");
    var catalog = this.data.topicCatalog || [];
    var selected = catalog.find(function (item) {
      return item.topicId === topicId;
    });
    if (!selected || !selected.enabled) {
      wx.showToast({ title: "该专题题库维护中", icon: "none" });
      return;
    }
    this.setData(
      Object.assign(
        {
          selectedTopicId: selected.topicId,
          selectedTopicLabel: selected.label,
          selectedTopicStatus: selected.status,
          selectedTopicFormCount: selected.formCount,
          assessmentTopicTouched: true,
        },
        buildWelcomeModeState(this.data.assessmentMode, selected.label, selected.formCount),
      ),
    );
  },

  onSelectAssessmentMode: function (e) {
    var mode = String((e.currentTarget.dataset || {}).mode || "diagnostic");
    this.setData(
      Object.assign(
        { assessmentModeTouched: true },
        buildWelcomeModeState(mode, this.data.selectedTopicLabel, this.data.selectedTopicFormCount),
      ),
    );
  },

  // ── 开始测试 ──────────────────────────────────
  onStart: function () {
    if (this.data.starting) return;
    var assessmentMode = String(this.data.assessmentMode || "diagnostic");
    var selectedTopic = String(this.data.selectedTopicId || "waterproof");
    var selectedTopicStatus = String(this.data.selectedTopicStatus || "authoring_needed");
    if (assessmentMode === "topic" && selectedTopicStatus === "authoring_needed") {
      wx.showToast({ title: "该专题题库维护中", icon: "none" });
      return;
    }
    var self = this;
    helpers.vibrate("medium");
    self.setData({ stage: "loading", starting: true });

    var requestPayload =
      assessmentMode === "topic"
        ? {
            assessment_type: "topic_diagnostic",
            subject_id: "construction_exam",
            topic_ids: [selectedTopic],
            count: 12,
            duration_policy: { mode: "one_shot" },
          }
        : {
            assessment_type: "real_exam_simulation",
            subject_id: "construction_exam",
            count: 20,
            duration_policy: { mode: "one_shot" },
          };
    requestPayload.device_id = getAssessmentDeviceId();

    api
      .createAssessment(requestPayload)
      .then(function (resp) {
        try {
          // 兼容两种返回格式: {questions, quiz_id} 或 {data: {questions, quiz_id}}
          var payload = (resp && resp.data) || resp || {};
          var questions = normalizeAssessmentQuestions(payload.questions);
          if (!questions.length) {
            wx.showToast({ title: "暂无题目", icon: "none" });
            self.setData({ stage: "welcome", starting: false });
            return;
          }
          var answerState = buildAnswerState(questions, {}, 0);
          var requestedCount = Number(payload.requested_count || questions.length) || questions.length;
          var deliveredCount = Number(payload.delivered_count || questions.length) || questions.length;
          var scoredCount = Number(payload.scored_count || 0) || 0;
          var profileCount = Number(payload.profile_count || 0) || 0;
          var availableCount = Number(payload.available_count || deliveredCount) || deliveredCount;
          var shortfallCount = Math.max(0, Number(payload.shortfall_count || 0) || 0);
          self._quizId = payload.quiz_id;
          self._startTime = Date.now();
          self.setData({
            stage: "quiz",
            starting: false,
            questions: questions,
            currentIndex: 0,
            currentQ: questions[0],
            selMap: {},
            selectedKeys: {},
            answerSheet: answerState.answerSheet,
            answeredCount: answerState.answeredCount,
            unansweredCount: answerState.unansweredCount,
            requestedCount: requestedCount,
            deliveredCount: deliveredCount,
            scoredCount: scoredCount,
            profileCount: profileCount,
            blueprintVersion: payload.blueprint_version || "",
            topicLabel: payload.topic_label || self.data.welcomeTitle || ASSESSMENT_I18N_KEYS.topicLabel,
            readOnlyBanner: payload.lease_holder_other_device ? ASSESSMENT_I18N_KEYS.readOnlyOtherDevice : "",
            availableCount: availableCount,
            shortfallCount: shortfallCount,
            assessmentNotice:
              shortfallCount > 0
                ? "题库当前可用 " + availableCount + " 题，本次先完成 " + deliveredCount + " 题。"
                : scoredCount && profileCount
                ? "本次 " + scoredCount + " 道知识题 + " + profileCount + " 道学习画像题。"
                : "",
          });
        } catch (renderErr) {
          console.error("[Assessment] create succeeded but quiz render failed", renderErr);
          wx.showToast({ title: "题目数据异常", icon: "none" });
          self.setData({ stage: "welcome", starting: false });
        }
      })
      .catch(function (e) {
        console.error("[Assessment] create request failed", e);
        wx.showToast({ title: assessmentCreateErrorCopy(e), icon: "none" });
        self.setData({ stage: "welcome", starting: false });
      });
  },

  // ── 选择选项 ──────────────────────────────────
  onSelectOption: function (e) {
    helpers.vibrate("light");
    var key = e.currentTarget.dataset.key;
    var q = this.data.currentQ;
    var qId = q.id;
    var isMulti = q.question_type === "multi_choice";
    var mapKey = qId + "_" + key;
    var oldMap = this.data.selMap || {};
    var oldKeys = this.data.selectedKeys || {};
    var wasAnswered = !!oldKeys[qId];
    var opts = q.options || [];
    var nextMap = Object.assign({}, oldMap);
    if (isMulti) {
      nextMap[mapKey] = !oldMap[mapKey];
    } else {
      for (var i = 0; i < opts.length; i++) {
        nextMap[qId + "_" + opts[i].key] = false;
      }
      nextMap[mapKey] = true;
    }
    var answerStr = "";
    for (var j = 0; j < opts.length; j++) {
      if (nextMap[qId + "_" + opts[j].key]) answerStr += opts[j].key;
    }
    var newKeys = {};
    var k;
    for (k in oldKeys) {
      if (oldKeys.hasOwnProperty(k)) newKeys[k] = oldKeys[k];
    }
    newKeys[qId] = answerStr;
    var isAnswered = !!answerStr;
    var answeredCount = this.data.answeredCount || 0;
    if (!wasAnswered && isAnswered) answeredCount += 1;
    if (wasAnswered && !isAnswered) answeredCount -= 1;
    var answerSheet = (this.data.answerSheet || []).slice();
    if (answerSheet[this.data.currentIndex]) {
      answerSheet[this.data.currentIndex] = Object.assign(
        {},
        answerSheet[this.data.currentIndex],
        { answered: isAnswered },
      );
    }
    this.setData({
      selMap: nextMap,
      selectedKeys: newKeys,
      answerSheet: answerSheet,
      answeredCount: answeredCount,
      unansweredCount: Math.max(0, this.data.questions.length - answeredCount),
    });

    // 单选自动跳下一题 (300ms 延迟)
    if (
      q.question_type !== "multi_choice" &&
      this.data.currentIndex < this.data.questions.length - 1
    ) {
      var self = this;
      setTimeout(function () {
        self.onNext();
      }, 300);
    }
  },

  // ── 导航 ──────────────────────────────────────
  onPrev: function () {
    if (this.data.currentIndex <= 0) return;
    var idx = this.data.currentIndex - 1;
    var answerState = buildAnswerState(
      this.data.questions,
      this.data.selectedKeys,
      idx,
    );
    this.setData({
      currentIndex: idx,
      currentQ: this.data.questions[idx],
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
    });
  },

  onNext: function () {
    if (this.data.currentIndex >= this.data.questions.length - 1) return;
    var idx = this.data.currentIndex + 1;
    var answerState = buildAnswerState(
      this.data.questions,
      this.data.selectedKeys,
      idx,
    );
    this.setData({
      currentIndex: idx,
      currentQ: this.data.questions[idx],
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
    });
  },

  onJumpQuestion: function (e) {
    var idx = Number(e.currentTarget.dataset.index);
    if (isNaN(idx) || idx < 0 || idx >= this.data.questions.length) return;
    var answerState = buildAnswerState(
      this.data.questions,
      this.data.selectedKeys,
      idx,
    );
    this.setData({
      currentIndex: idx,
      currentQ: this.data.questions[idx],
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
    });
  },

  // ── 提交 ──────────────────────────────────────
  onSubmit: function () {
    if (this.data.submitting) return;
    var self = this;
    var total = self.data.questions.length;
    var answered = self.data.answeredCount;

    if (answered < total) {
      var blank = answered === 0;
      wx.showModal({
        title: blank ? "尚未作答" : "还有未答题目",
        content: blank
          ? "你尚未作答。建议先完成题目，再提交诊断。"
          : "还有 " +
            (total - answered) +
            " 题未答，你已完成 " +
            answered +
            "/" +
            total +
            " 题，确定提交吗？",
        confirmText: "提交",
        success: function (res) {
          if (res.confirm) self._doSubmit();
        },
      });
      return;
    }
    self._doSubmit();
  },

  _doSubmit: function () {
    var self = this;
    helpers.vibrate("medium");
    self.setData({ stage: "loading", submitting: true });

    var timeSpent = Math.round((Date.now() - self._startTime) / 1000);
    var answers = {};
    var keys = self.data.selectedKeys;
    Object.keys(keys).forEach(function (qId) {
      if (keys[qId]) answers[qId] = keys[qId];
    });

    api
      .submitAssessment(self._quizId, answers, timeSpent, getAssessmentDeviceId())
      .then(function (resp) {
        var data = resp.data || resp;
        try {
          if (data && data.schema_version === "p0a-v1") {
            self.setData(
              Object.assign(
                {
                  stage: "result",
                  submitting: false,
                },
                buildP0AResultModel(data, self.data.questions),
              ),
            );
            wx.setStorageSync("diagnostic_completed", true);
            helpers.vibrate("heavy");
            return;
          }
          // 响应已收到
          var fb = data.diagnostic_feedback || data.feedback || {};
          var ao = fb.ability_overview || {};
          var ci = fb.cognitive_insight || {};
          var lp = fb.learner_profile || {};
          var ap = fb.action_plan || {};
          var diag = data.diagnostic || data.diagnostic_profile || {};

          var score = pickNumber(ao.score_pct, data.score);
          var level = data.suggested_level || data.level || "beginner";

          // 章节掌握度
          var mastery = ao.chapter_mastery || data.chapter_mastery || {};
          var chapterList = Object.keys(mastery)
            .map(function (ch) {
              var v = mastery[ch];
              var name = typeof v === "object" ? v.name || ch : ch;
              var pct =
                typeof v === "object"
                  ? Math.round(pickNumber(v.mastery, v.pct))
                  : Math.round(v * 100);
              return { name: displayChapterName(name), pct: pct };
            })
            .sort(function (a, b) {
              return b.pct - a.pct;
            });

          // ── 客户端 fallback 画像生成 ──────────────
          var archetype = lp.archetype || diag.learner_archetype || "";
          var archetypeName = lp.archetype_name || "";
          var archetypeDesc = lp.description || "";
          var archetypeTraits = lp.traits || [];
          var archetypeTip = lp.study_tip || "";
          var rp = ci.response_profile || diag.response_profile || "";
          var cal = ci.calibration_label || diag.calibration_label || "";
          var ep = ao.error_pattern || diag.error_pattern || "";

          // 如果后端没返回画像，根据分数和答题时间本地生成
          if (!archetype) {
            var avgTime = timeSpent / self.data.questions.length;
            if (score >= 70) {
              archetype = avgTime < 20 ? "strategist" : "explorer";
            } else if (score >= 40) {
              archetype = avgTime < 25 ? "sprinter" : "builder";
            } else {
              archetype = avgTime < 20 ? "sprinter" : "builder";
            }
          }
          if (!archetypeName)
            archetypeName = ARCHETYPE_NAMES[archetype] || archetype;
          if (!archetypeDesc) archetypeDesc = ARCHETYPE_DESCS[archetype] || "";
          if (!archetypeTraits.length)
            archetypeTraits = ARCHETYPE_TRAITS[archetype] || [];
          if (!archetypeTip) archetypeTip = ARCHETYPE_TIPS[archetype] || "";

          // 认知风格 fallback
          if (!rp) {
            var avgT = timeSpent / self.data.questions.length;
            var correct = Object.keys(answers).length > 0 ? score / 100 : 0;
            if (correct >= 0.6 && avgT < 25) rp = "fluent";
            else if (correct >= 0.6) rp = "deliberate";
            else if (avgT < 20) rp = "impulsive";
            else rp = "struggling";
          }

          // 错误模式 fallback
          if (!ep)
            ep =
              score >= 60
                ? "slip_dominant"
                : score >= 30
                  ? "mixed"
                  : "gap_dominant";
          var epNames = {
            slip_dominant: "粗心型",
            gap_dominant: "知识盲区型",
            confusion_dominant: "概念混淆型",
            mixed: "综合型",
          };

          // 优先攻克：掌握度最低的 5 个章节
          var priorityChapters = Array.isArray(ap.priority_chapters)
            ? ap.priority_chapters
            : [];
          var priority = priorityChapters.map(function (c) {
            return displayChapterName(typeof c === "object" ? c.name || c.code || "" : c);
          });
          if (!priority.length && chapterList.length) {
            priority = chapterList
              .slice()
              .sort(function (a, b) {
                return a.pct - b.pct;
              })
              .slice(0, 5)
              .map(function (c) {
                return c.name;
              });
          }

          self.setData({
            stage: "result",
            submitting: false,
            resultScore: score,
            resultLevel: level,
            resultLevelName: LEVEL_NAMES[level] || level,
            chapterList: chapterList,
            archetype: archetype,
            archetypeName: archetypeName || "动态调节型学员",
            archetypeDesc: archetypeDesc,
            archetypeTraits: archetypeTraits,
            archetypeTip: archetypeTip,
            archetypeColor: ARCHETYPE_COLORS[archetype] || "#3b82f6",
            archetypeIcon: ARCHETYPE_ICONS[archetype] || "?",
            responseLabel: RESPONSE_LABELS[rp] || "待继续观察",
            responseDesc: RESPONSE_DESCS[rp] || "",
            calibrationLabel: CALIBRATION_LABELS[cal] || (cal ? "待继续观察" : ""),
            errorPattern: ep,
            errorPatternName: epNames[ep] || "待继续观察",
            priorityChapters: priority.slice(0, 5),
            planStrategy: ap.plan_strategy || "",
          });

          wx.setStorageSync("diagnostic_completed", true);
          helpers.vibrate("heavy");
        } catch (renderErr) {
          console.error("[Assessment] submit succeeded but result render failed", renderErr);
          self.setData(
            Object.assign(
              {
                stage: "result",
                submitting: false,
              },
              buildSubmitSuccessFallbackModel(data),
            ),
          );
          wx.setStorageSync("diagnostic_completed", true);
          helpers.vibrate("heavy");
          wx.showToast({ title: "已提交", icon: "success" });
        }
      })
      .catch(function (e) {
        // 提交失败已通过 toast 展示
        wx.showToast({ title: "提交失败，请重试", icon: "none" });
        self.setData({ stage: "quiz", submitting: false });
      });
  },

  // ── 操作 ──────────────────────────────────────
  onRetake: function () {
    this.setData({
      stage: "welcome",
      questions: [],
      selMap: {},
      selectedKeys: {},
      answerSheet: [],
      answeredCount: 0,
      unansweredCount: 0,
      currentIndex: 0,
      serverReportMode: false,
      reportSchemaVersion: "",
      knowledgeMap: [],
      actionKnowledgeMap: [],
      wrongItems: [],
      issueSummary: [],
      prescriptionSteps: [],
      attemptRefs: [],
      correctCount: 0,
      blankCount: 0,
      sessionLocalNextAction: "",
      degradedReason: "",
      degradedCopy: "",
      readOnlyBanner: "",
    });
  },

  goLearningPlan: function () {
    wx.reLaunch({ url: route.report({ detail: "training" }) });
  },

  onPracticeWrongItem: function (event) {
    var questionId =
      event && event.currentTarget && event.currentTarget.dataset
        ? String(event.currentTarget.dataset.questionId || "")
        : "";
    var item = (this.data.wrongItems || []).find(function (candidate) {
      return String(candidate.questionId || "") === questionId;
    });
    if (!item) return;
    var knowledgePoint = String((item.knowledgePoints || [])[0] || "本题知识点");
    var errorCode = String((item.errorCodes || [])[0] || "错因");
    var prompt =
      "请围绕我刚才错的“" +
      knowledgePoint +
      "”，出 3 道同类选择题训练我。先只出题，不要提前给答案和解析。";
    var followupQuestionContext = buildWrongItemFollowupQuestionContext(item, this._quizId);
    var intent = {
      source: "assessment_result_wrong_item",
      learning_signal_type: "assessment_wrong_item_practice",
      subject_id: "construction_exam",
      concept_label: knowledgePoint,
      error_label: errorCode,
      attempt_ref: String(item.attemptRef || ""),
      evidence_refs: [String(item.attemptRef || "")].filter(Boolean),
      question_count: 3,
      training_mode: "same_type_repair",
      prompt: prompt,
    };
    if (followupQuestionContext) {
      intent.followupQuestionContext = followupQuestionContext;
    }
    if (typeof wx !== "undefined" && typeof wx.setStorageSync === "function") {
      wx.setStorageSync("deeptutor.report.pendingTrainingAction", intent);
    }
    wx.reLaunch({
      url: route.report({
        detail: "training",
        source: "assessment_wrong_item",
        attempt_ref: String(item.attemptRef || ""),
        knowledge_point: knowledgePoint,
        error_code: errorCode,
      }),
    });
  },

  onToggleWrongDetail: function (event) {
    var self = this;
    var questionId =
      event && event.currentTarget && event.currentTarget.dataset
        ? String(event.currentTarget.dataset.questionId || "")
        : "";
    var target = (this.data.wrongItems || []).find(function (item) {
      return String(item.questionId || "") === questionId;
    });
    if (!target) return;
    if (target.expanded) {
      this.setData({
        wrongItems: (this.data.wrongItems || []).map(function (item) {
          if (String(item.questionId || "") !== questionId) return item;
          return Object.assign({}, item, { expanded: false });
        }),
      });
      return;
    }
    if (target.detailStatus === "ready") {
      this.setData({
        wrongItems: (this.data.wrongItems || []).map(function (item) {
          if (String(item.questionId || "") !== questionId) return item;
          return Object.assign({}, item, { expanded: true, detailStatusText: item.detailBilling || "已生成" });
        }),
      });
      return;
    }
    var loadingItems = (this.data.wrongItems || []).map(function (item) {
      if (String(item.questionId || "") !== questionId) return item;
      return Object.assign({}, item, {
        expanded: true,
        detailStatus: "loading",
        detailStatusText: "正在生成解析",
        detailError: "",
      });
    });
    this.setData({ wrongItems: loadingItems });
    api
      .requestAssessmentDeepExplanation(this._quizId, questionId)
      .then(function (payload) {
        var readyItems = (self.data.wrongItems || []).map(function (item) {
          if (String(item.questionId || "") !== questionId) return item;
          var generated = normalizeGeneratedDetail(payload, item);
          return Object.assign({}, item, generated, {
            expanded: true,
            detailStatus: "ready",
            detailStatusText: generated.detailBilling || "已生成",
            detailError: "",
          });
        });
        self.setData({ wrongItems: readyItems });
      })
      .catch(function (err) {
        var message =
          api.describeRequestError && typeof api.describeRequestError === "function"
            ? api.describeRequestError(err, "AI详细解析生成失败")
            : "AI详细解析生成失败";
        var errorItems = (self.data.wrongItems || []).map(function (item) {
          if (String(item.questionId || "") !== questionId) return item;
          return Object.assign({}, item, {
            expanded: true,
            detailStatus: "error",
            detailStatusText: "生成失败",
            detailError: message,
          });
        });
        self.setData({ wrongItems: errorItems });
      });
  },

  goBack: function () {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.chat() });
      },
    });
  },
});
