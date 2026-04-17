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
        text: _asString(opt.text || ""),
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
      text: _asString(rawOptions[key] || ""),
      selected: false,
    });
  }
  return options;
}

function normalizeMcqQuestion(rawQuestion, fallbackIndex) {
  var q = rawQuestion && typeof rawQuestion === "object" ? rawQuestion : {};
  var followupContext =
    q.followupContext && typeof q.followupContext === "object"
      ? q.followupContext
      : q.followup_context && typeof q.followup_context === "object"
        ? q.followup_context
        : null;
  var questionId = _trimmedString(
    q.questionId ||
      q.question_id ||
      (followupContext && followupContext.question_id) ||
      "",
  );
  return {
    index: _positiveInt(q.index, fallbackIndex),
    stem: _asString(q.stem || "请选择正确选项"),
    hint: _asString(q.hint || ""),
    questionType:
      _normalizeEnum(
        q.questionType || q.question_type,
        ["single_choice", "multi_choice"],
        "single_choice",
      ),
    options: normalizeMcqOptions(q.options),
    followupContext: followupContext,
    questionId: questionId,
    hasContext: !!questionId,
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
    submitHint: _asString(block.submitHint || block.submit_hint || "请选择后提交答案"),
    receipt: _asString(block.receipt || ""),
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
    text: _asString(block.text || block.content || ""),
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
    fallbackText: _asString(message.fallbackText || message.fallback_text || ""),
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
};
