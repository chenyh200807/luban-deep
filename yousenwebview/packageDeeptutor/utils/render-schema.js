// utils/render-schema.js — 内部教学渲染 schema 注册表与最小 normalizer

var SCHEMA_VERSION = 1;

var INTERNAL_RENDER_SCHEMAS = {
  canonical_message: { name: "canonical_message", version: SCHEMA_VERSION },
  mcq_block: { name: "mcq_block", version: SCHEMA_VERSION },
  table_block: { name: "table_block", version: SCHEMA_VERSION },
  formula_block: { name: "formula_block", version: SCHEMA_VERSION },
  chart_block: { name: "chart_block", version: SCHEMA_VERSION },
  steps_block: { name: "steps_block", version: SCHEMA_VERSION },
  recap_block: { name: "recap_block", version: SCHEMA_VERSION },
  render_model: { name: "render_model", version: SCHEMA_VERSION },
};

var BLOCK_TYPES = {
  paragraph: "paragraph",
  heading: "heading",
  list: "list",
  callout: "callout",
  quote: "quote",
  code: "code",
  table: "table",
  mcq: "mcq",
  formula_inline: "formula_inline",
  formula_block: "formula_block",
  chart: "chart",
  image: "image",
  steps: "steps",
  recap: "recap",
};

function _asString(value) {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return String(value);
}

var _AUTHORITY_TEXT_PATTERNS = [
  /\b(?:correct[_\s-]?answer|reference[_\s-]?answer|answer[_\s-]?key|grading[_\s-]?key|grading[_\s-]?authority|scoring[_\s-]?points?|grader[_\s-]?secret)\b/i,
  /(?:(?:正确答案|参考答案|标准答案)\s*[：:]\s*\S+|答案[是为]\s*\S+)/,
];

function _containsAuthorityText(text) {
  var value = _asString(text);
  for (var i = 0; i < _AUTHORITY_TEXT_PATTERNS.length; i += 1) {
    if (_AUTHORITY_TEXT_PATTERNS[i].test(value)) return true;
  }
  return false;
}

function sanitizeAuthorityText(value, fallback) {
  var text = _asString(value);
  if (!_containsAuthorityText(text)) return text;
  var lines = text.split(/\r?\n/);
  var kept = [];
  for (var i = 0; i < lines.length; i += 1) {
    if (_containsAuthorityText(lines[i])) continue;
    kept.push(lines[i]);
  }
  var sanitized = kept.join("\n").trim();
  return sanitized || _asString(fallback || "");
}

function sanitizeAuthorityMarkdownText(value) {
  return sanitizeAuthorityText(value, "");
}

function sanitizeMcqOptionText(value) {
  var text = _asString(value);
  text = text.replace(
    /(?:\s*[-—–|｜,，;；]\s*)?(?:采分点|评分点|得分点|scoring[_\s-]?points?)\s*[：:].*$/i,
    "",
  );
  text = sanitizeAuthorityText(text, "");
  return text.trim() || "选项内容已隐藏";
}

function _trimmedString(value) {
  return _asString(value).trim();
}

function _positiveInt(value, fallback) {
  var num = parseInt(value, 10);
  return num > 0 ? num : fallback;
}

function _normalizeEnum(value, allowed, fallback) {
  var raw = _trimmedString(value);
  if (allowed.indexOf(raw) !== -1) return raw;
  return fallback;
}

function _normalizeStringArray(items) {
  var arr = Array.isArray(items) ? items : [];
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    var value = _trimmedString(arr[i]);
    if (!value) continue;
    out.push(value);
  }
  return out;
}

function _normalizeObjectArray(items, normalizer) {
  var arr = Array.isArray(items) ? items : [];
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    var normalized = normalizer(arr[i], i + 1);
    if (!normalized) continue;
    out.push(normalized);
  }
  return out;
}

function _chartSeriesValueSummary(values) {
  var arr = Array.isArray(values) ? values : [];
  var parts = [];
  for (var i = 0; i < arr.length; i++) {
    var item = arr[i];
    if (item && typeof item === "object") {
      var label = _trimmedString(item.label || item.name || item.x || "");
      var value = _trimmedString(item.value || item.y || "");
      if (label || value) {
        parts.push(label && value ? label + ":" + value : label || value);
      }
      continue;
    }
    var text = _trimmedString(item);
    if (text) parts.push(text);
  }
  return parts.join(" / ");
}

function normalizeMcqOptions(rawOptions) {
  var options = [];
  if (Array.isArray(rawOptions)) {
    for (var i = 0; i < rawOptions.length; i++) {
      var opt = rawOptions[i];
      if (!opt || !opt.key) continue;
      options.push({
        key: _trimmedString(opt.key).toUpperCase(),
        text: sanitizeMcqOptionText(opt.text || ""),
        selected: !!opt.selected,
      });
    }
    return options;
  }
  if (!rawOptions || typeof rawOptions !== "object") return options;
  var keys = Object.keys(rawOptions).sort();
  for (var j = 0; j < keys.length; j++) {
    var key = keys[j];
    options.push({
      key: _trimmedString(key).toUpperCase(),
      text: sanitizeMcqOptionText(rawOptions[key] || ""),
      selected: false,
    });
  }
  return options;
}

function normalizeMcqReviewNotes(rawNotes) {
  var notes = rawNotes && typeof rawNotes === "object" ? rawNotes : {};
  var thinkPrompt = _trimmedString(notes.thinkPrompt || notes.think_prompt || "");
  var displayAnswer = _trimmedString(
    notes.displayAnswer ||
      notes.display_answer ||
      notes.answer ||
      notes.answerText ||
      notes.answer_text ||
      "",
  ).toUpperCase();
  var analysis = _trimmedString(
    notes.analysis ||
      notes.analysisText ||
      notes.analysis_text ||
      notes.teachingText ||
      notes.teaching_text ||
      "",
  );
  var optionAnalysis = _normalizeObjectArray(
    notes.optionAnalysis ||
      notes.option_analysis ||
      notes.choiceAnalysis ||
      notes.choice_analysis,
    function (item) {
      var raw = item && typeof item === "object" ? item : {};
      var key = _trimmedString(raw.key || raw.option || raw.option_key || raw.label || "").toUpperCase();
      var row = {
        key: key,
        text: _trimmedString(raw.text || raw.optionText || raw.option_text || ""),
        verdict: _trimmedString(raw.verdict || raw.status || ""),
        analysis: _trimmedString(raw.analysis || raw.reason || raw.explanation || ""),
      };
      return row.key || row.analysis ? row : null;
    },
  );
  var scoringPoints = _normalizeStringArray(notes.scoringPoints || notes.scoring_points);
  var pitfalls = _normalizeStringArray(
    notes.pitfalls ||
      notes.easyMistakes ||
      notes.easy_mistakes ||
      notes.commonMistakes ||
      notes.common_mistakes,
  );
  var mnemonic = _trimmedString(notes.mnemonic || notes.memoryTip || notes.memory_tip || "");
  if (
    !thinkPrompt &&
    !displayAnswer &&
    !analysis &&
    !optionAnalysis.length &&
    !scoringPoints.length &&
    !pitfalls.length &&
    !mnemonic
  ) return null;
  return {
    thinkPrompt: thinkPrompt,
    displayAnswer: displayAnswer,
    analysis: analysis,
    optionAnalysis: optionAnalysis,
    scoringPoints: scoringPoints,
    pitfalls: pitfalls,
    mnemonic: mnemonic,
  };
}

function normalizeMcqQuestion(rawQuestion, fallbackIndex) {
  var q = rawQuestion && typeof rawQuestion === "object" ? rawQuestion : {};
  var rawFollowup =
    q.followupContext && typeof q.followupContext === "object"
      ? q.followupContext
      : q.followup_context && typeof q.followup_context === "object"
        ? q.followup_context
        : null;
  var questionId = _trimmedString(
    q.questionId ||
      q.question_id ||
      (rawFollowup && rawFollowup.question_id) ||
      "",
  );
  return {
    index: _positiveInt(q.index, fallbackIndex),
    stem: sanitizeAuthorityText(q.stem || "请选择正确选项", "请选择正确选项"),
    hint: sanitizeAuthorityText(q.hint || "", ""),
    questionType:
      _normalizeEnum(
        q.questionType || q.question_type,
        ["single_choice", "multi_choice"],
        "single_choice",
    ),
    options: normalizeMcqOptions(q.options),
    followupContext: sanitizeFollowupContext(rawFollowup),
    questionId: questionId,
    hasContext: !!questionId,
    reviewNotes: normalizeMcqReviewNotes(q.reviewNotes || q.review_notes),
  };
}

function createMcqBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var rawQuestions = Array.isArray(block.questions) ? block.questions : [];
  var questions = [];
  for (var i = 0; i < rawQuestions.length; i++) {
    var question = normalizeMcqQuestion(rawQuestions[i], i + 1);
    if (!question.options || question.options.length < 2) continue;
    questions.push(question);
  }
  return {
    type: BLOCK_TYPES.mcq,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.mcq_block.version,
    questions: questions,
    submitHint: sanitizeAuthorityText(
      block.submitHint || block.submit_hint || "请选择后提交答案",
      "请选择后提交答案",
    ),
    receipt: sanitizeAuthorityText(block.receipt || "", ""),
    reviewMode: !!(block.reviewMode || block.review_mode),
  };
}

function _normalizeTableCell(rawCell) {
  if (rawCell && typeof rawCell === "object" && !Array.isArray(rawCell)) {
    return {
      text: _asString(rawCell.text || ""),
      align: _normalizeEnum(rawCell.align, ["left", "center", "right"], "left"),
      highlight: !!rawCell.highlight,
    };
  }
  return {
    text: _asString(rawCell || ""),
    align: "left",
    highlight: false,
  };
}

function _normalizeTableRow(rawRow) {
  var row = Array.isArray(rawRow) ? rawRow : [];
  var cells = [];
  for (var i = 0; i < row.length; i++) {
    cells.push(_normalizeTableCell(row[i]));
  }
  return cells;
}

function createTableBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var headers = _normalizeTableRow(block.headers);
  var rawRows = Array.isArray(block.rows) ? block.rows : [];
  var rows = [];
  for (var i = 0; i < rawRows.length; i++) {
    rows.push(_normalizeTableRow(rawRows[i]));
  }
  return {
    type: BLOCK_TYPES.table,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.table_block.version,
    headers: headers,
    rows: rows,
    caption: _asString(block.caption || ""),
    mobileStrategy: _normalizeEnum(
      block.mobileStrategy || block.mobile_strategy,
      ["scroll", "compact_cards"],
      "scroll",
    ),
  };
}

function createFormulaBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var type = _normalizeEnum(
    block.type || block.kind,
    [BLOCK_TYPES.formula_inline, BLOCK_TYPES.formula_block, "inline", "block"],
    BLOCK_TYPES.formula_block,
  );
  var normalizedType =
    type === "inline" ? BLOCK_TYPES.formula_inline : type === "block" ? BLOCK_TYPES.formula_block : type;
  var latex = _asString(block.latex || "");
  return {
    type: normalizedType,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.formula_block.version,
    latex: latex,
    displayText: _asString(block.displayText || block.display_text || latex),
    svgUrl: _asString(block.svgUrl || block.svg_url || ""),
    copyText: _asString(block.copyText || block.copy_text || latex),
  };
}

function normalizeChartSeriesItem(rawSeries, fallbackIndex) {
  var series = rawSeries && typeof rawSeries === "object" ? rawSeries : {};
  var values = Array.isArray(series.values)
    ? series.values
    : Array.isArray(series.data)
      ? series.data
      : [];
  var valueSummary = _chartSeriesValueSummary(values);
  return {
    name: _asString(series.name || series.label || series.title || "系列" + fallbackIndex),
    summary: _asString(series.summary || series.desc || series.description || series.value || valueSummary),
    value: _asString(series.value || ""),
    color: _asString(series.color || ""),
    values: values.map(function (item) {
      if (item && typeof item === "object") {
        return _trimmedString(item.label || item.name || item.x || item.value || item.y || "");
      }
      return _trimmedString(item);
    }).filter(function (item) {
      return !!item;
    }),
  };
}

function createChartBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var series = _normalizeObjectArray(block.series, normalizeChartSeriesItem);
  var fallbackTableSource = block.fallbackTable || block.fallback_table || null;
  var fallbackTable =
    fallbackTableSource && typeof fallbackTableSource === "object"
      ? createTableBlock(fallbackTableSource)
      : null;
  var title = _asString(block.title || "");
  var summary = _asString(block.summary || block.description || "");
  var caption = _asString(block.caption || "");
  var legend = _normalizeStringArray(block.legend);
  var hasContent =
    !!title ||
    !!summary ||
    !!caption ||
    series.length > 0 ||
    legend.length > 0 ||
    (fallbackTable && (fallbackTable.headers.length > 0 || fallbackTable.rows.length > 0));
  if (!hasContent) return null;
  return {
    type: BLOCK_TYPES.chart,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.chart_block.version,
    chartType: _normalizeEnum(
      block.chartType || block.chart_type,
      ["line", "bar", "pie", "timeline"],
      "line",
    ),
    title: title,
    summary: summary,
    series: series,
    axes: {
      x: _asString(block.axes && block.axes.x ? block.axes.x : block.xAxis || block.x_axis || ""),
      y: _asString(block.axes && block.axes.y ? block.axes.y : block.yAxis || block.y_axis || ""),
    },
    legend: legend,
    caption: caption,
    fallbackTable: fallbackTable,
  };
}

function createStepsBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var rawItems = Array.isArray(block.steps)
    ? block.steps
    : Array.isArray(block.items)
      ? block.items
      : [];
  var steps = [];
  for (var i = 0; i < rawItems.length; i++) {
    var item = rawItems[i];
    var normalized = item && typeof item === "object" ? item : { title: item };
    var title = _asString(normalized.title || normalized.text || normalized.label || "");
    var detail = _asString(normalized.detail || normalized.summary || normalized.content || "");
    if (!title && !detail) continue;
    steps.push({
      index: _positiveInt(normalized.index, i + 1),
      title: title || ("步骤" + (i + 1)),
      detail: detail,
      status: _normalizeEnum(normalized.status, ["done", "doing", "todo"], "todo"),
    });
  }
  var blockTitle = _asString(block.title || block.caption || "");
  if (!blockTitle && !steps.length) return null;
  return {
    type: BLOCK_TYPES.steps,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.steps_block.version,
    title: blockTitle,
    steps: steps,
  };
}

function createRecapBlock(rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  var bullets = _normalizeStringArray(block.bullets || block.points || block.items);
  var title = _asString(block.title || block.heading || "");
  var summary = _asString(block.summary || block.text || block.content || "");
  if (!title && !summary && !bullets.length) return null;
  return {
    type: BLOCK_TYPES.recap,
    schemaVersion: INTERNAL_RENDER_SCHEMAS.recap_block.version,
    title: title || "教学总结",
    summary: summary,
    bullets: bullets,
  };
}

function _createTextBlock(type, rawBlock) {
  var block = rawBlock && typeof rawBlock === "object" ? rawBlock : {};
  return {
    type: type,
    schemaVersion: SCHEMA_VERSION,
    text: sanitizeAuthorityText(
      block.text || block.content || "",
      type === BLOCK_TYPES.callout ? "完整解析需在评分后查看" : "",
    ),
  };
}

function normalizeBlock(rawBlock) {
  if (!rawBlock || typeof rawBlock !== "object") return null;
  var type = _trimmedString(rawBlock.type);
  if (!type) return null;
  if (type === BLOCK_TYPES.mcq) return createMcqBlock(rawBlock);
  if (type === BLOCK_TYPES.table) return createTableBlock(rawBlock);
  if (type === BLOCK_TYPES.formula_inline || type === BLOCK_TYPES.formula_block) {
    return createFormulaBlock(rawBlock);
  }
  if (type === BLOCK_TYPES.chart) return createChartBlock(rawBlock);
  if (type === BLOCK_TYPES.steps) return createStepsBlock(rawBlock);
  if (type === BLOCK_TYPES.recap) return createRecapBlock(rawBlock);
  if (
    type === BLOCK_TYPES.paragraph ||
    type === BLOCK_TYPES.heading ||
    type === BLOCK_TYPES.callout ||
    type === BLOCK_TYPES.quote ||
    type === BLOCK_TYPES.code ||
    type === BLOCK_TYPES.image
  ) {
    return _createTextBlock(type, rawBlock);
  }
  if (type === "summary") {
    return createRecapBlock(rawBlock);
  }
  if (type === BLOCK_TYPES.list) {
    return {
      type: BLOCK_TYPES.list,
      schemaVersion: SCHEMA_VERSION,
      items: _normalizeStringArray(rawBlock.items),
    };
  }
  return null;
}

function createCanonicalMessage(rawMessage) {
  var message = rawMessage && typeof rawMessage === "object" ? rawMessage : {};
  var rawBlocks = Array.isArray(message.blocks) ? message.blocks : [];
  var blocks = [];
  for (var i = 0; i < rawBlocks.length; i++) {
    var block = normalizeBlock(rawBlocks[i]);
    if (!block) continue;
    if (block.type === BLOCK_TYPES.mcq && !block.questions.length) continue;
    blocks.push(block);
  }
  return {
    schemaVersion: INTERNAL_RENDER_SCHEMAS.canonical_message.version,
    messageId: _asString(message.messageId || message.message_id || ""),
    blocks: blocks,
    fallbackText: sanitizeAuthorityMarkdownText(message.fallbackText || message.fallback_text || ""),
    meta: {
      streamingMode: _normalizeEnum(
        message.meta && message.meta.streamingMode,
        ["plain", "parsed", "text_first", "block_finalized"],
        "plain",
      ),
    },
    citations: Array.isArray(message.citations) ? message.citations : [],
  };
}

function createRenderModel(rawModel) {
  var model = rawModel && typeof rawModel === "object" ? rawModel : {};
  var renderableContent = _asString(model.renderableContent || "");
  var plainTextFallback = _asString(model.plainTextFallback || model.plain_text_fallback || renderableContent);
  var rawBlocks =
    model.blocks === null ? null : Array.isArray(model.blocks) ? model.blocks : [];
  var visibleBlocks = Array.isArray(model.visibleBlocks) ? model.visibleBlocks : [];
  var mcqCards =
    model.mcqCards === null
      ? null
      : Array.isArray(model.mcqCards)
        ? model.mcqCards
        : [];
  return {
    schemaVersion: INTERNAL_RENDER_SCHEMAS.render_model.version,
    renderableContent: renderableContent,
    blocks: rawBlocks,
    mcqCards: mcqCards,
    mcqHint: _asString(model.mcqHint || ""),
    mcqReceipt: _asString(model.mcqReceipt || ""),
    mcqInteractiveReady: !!model.mcqInteractiveReady,
    mcqReviewMode: !!model.mcqReviewMode,
    originalContent: _asString(model.originalContent || model.original_content || ""),
    originalCollapsed: model.originalCollapsed !== false,
    visibleBlocks: visibleBlocks,
    plainTextFallback: plainTextFallback,
    hasStructuredContent:
      typeof model.hasStructuredContent === "boolean"
        ? model.hasStructuredContent
        : visibleBlocks.length > 0,
    streamPhase: _normalizeEnum(
      model.streamPhase,
      ["idle", "streaming", "complete"],
      "idle",
    ),
    progressiveDisclosure: model.progressiveDisclosure || null,
  };
}

var _REDACTED_AUTHORITY_KEYS = [
  "correct_answer",
  "correctAnswer",
  "scoring_points",
  "scoringPoints",
  "explanation",
  "grading_key",
  "gradingKey",
  "grading_authority",
  "gradingAuthority",
  "reference_answer",
  "referenceAnswer",
  "answer_key",
  "answerKey",
  "grader_secret",
  "graderSecret",
];

function _isAuthorityKey(key) {
  return _REDACTED_AUTHORITY_KEYS.indexOf(key) >= 0;
}

function sanitizeFollowupContext(value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object") return value;
  if (Array.isArray(value)) {
    var arr = [];
    for (var i = 0; i < value.length; i += 1) {
      arr.push(sanitizeFollowupContext(value[i]));
    }
    return arr;
  }
  var out = {};
  var keys = Object.keys(value);
  for (var k = 0; k < keys.length; k += 1) {
    var key = keys[k];
    if (_isAuthorityKey(key)) continue;
    out[key] = sanitizeFollowupContext(value[key]);
  }
  return out;
}

function sanitizeProgressiveDisclosure(payload) {
  if (!payload || typeof payload !== "object") return null;
  var verdict = _asString(payload.verdict || "");
  var diagnosis = _asString(
    payload.one_line_diagnosis || payload.oneLineDiagnosis || "",
  );
  if (!verdict && !diagnosis) return null;
  function sanitizeAction(action) {
    if (!action || typeof action !== "object") return null;
    var slug = _asString(action.slug || "");
    var label = _asString(action.label || "");
    var role = _asString(action.role || "secondary");
    if (!slug || !label) return null;
    return {
      slug: slug,
      label: label,
      role: role === "primary" ? "primary" : "secondary",
    };
  }
  var primary = sanitizeAction(
    payload.primary_next_action || payload.primaryNextAction,
  );
  var rawSecondary = Array.isArray(
    payload.secondary_actions || payload.secondaryActions,
  )
    ? payload.secondary_actions || payload.secondaryActions
    : [];
  var secondary = [];
  for (var i = 0; i < rawSecondary.length && secondary.length < 2; i += 1) {
    var chip = sanitizeAction(rawSecondary[i]);
    if (chip) secondary.push(chip);
  }
  var sections = {};
  if (payload.sections && typeof payload.sections === "object") {
    var keys = Object.keys(payload.sections);
    for (var k = 0; k < keys.length; k += 1) {
      var key = keys[k];
      if (_isAuthorityKey(key)) continue;
      sections[key] = _asString(payload.sections[key] || "");
    }
  }
  var pacing = _asString(
    payload.difficulty_pacing || payload.difficultyPacing || "hold",
  );
  var allowedPacing = { hold: 1, suggest_consolidation: 1, suggest_step_up: 1 };
  if (!allowedPacing[pacing]) pacing = "hold";
  return {
    verdict: verdict.slice(0, 120),
    oneLineDiagnosis: diagnosis.slice(0, 80),
    primaryNextAction: primary,
    secondaryActions: secondary,
    sections: sections,
    difficultyPacing: pacing,
    gradingSource: _asString(
      payload.grading_source || payload.gradingSource || "",
    ),
  };
}

module.exports = {
  SCHEMA_VERSION: SCHEMA_VERSION,
  BLOCK_TYPES: BLOCK_TYPES,
  INTERNAL_RENDER_SCHEMAS: INTERNAL_RENDER_SCHEMAS,
  normalizeMcqOptions: normalizeMcqOptions,
  normalizeMcqQuestion: normalizeMcqQuestion,
  createMcqBlock: createMcqBlock,
  createTableBlock: createTableBlock,
  createFormulaBlock: createFormulaBlock,
  normalizeBlock: normalizeBlock,
  createCanonicalMessage: createCanonicalMessage,
  createRenderModel: createRenderModel,
  sanitizeProgressiveDisclosure: sanitizeProgressiveDisclosure,
  sanitizeFollowupContext: sanitizeFollowupContext,
  sanitizeAuthorityText: sanitizeAuthorityText,
  sanitizeAuthorityMarkdownText: sanitizeAuthorityMarkdownText,
};
