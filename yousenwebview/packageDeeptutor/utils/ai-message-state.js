// utils/ai-message-state.js — 统一 AI 消息的正文/题卡渲染状态
var md = require("./markdown");
var mcqDetect = require("./mcq-detect");
var renderSchema = require("./render-schema");

function toInlineContent(text) {
  return [{ type: "text", text: String(text || "") }];
}

function normalizeStructuredTableCell(cell) {
  var raw = cell && typeof cell === "object" ? cell : {};
  var text = String(raw.text || "");
  return {
    text: text,
    content: toInlineContent(text),
    align: raw.align || "left",
    highlight: raw.highlight === true,
  };
}

function normalizeStructuredChartSeries(series) {
  var raw = series && typeof series === "object" ? series : {};
  var values = Array.isArray(raw.values) ? raw.values : [];
  return {
    name: String(raw.name || ""),
    summary: String(raw.summary || raw.value || values.join(" / ") || ""),
    value: String(raw.value || ""),
    color: String(raw.color || ""),
    values: values.map(function (item) {
      return String(item || "");
    }),
  };
}

function normalizeStructuredChartTable(table) {
  if (!table || typeof table !== "object") return null;
  return {
    headers: Array.isArray(table.headers) ? table.headers.map(normalizeStructuredTableCell) : [],
    rows: Array.isArray(table.rows)
      ? table.rows.map(function (row) {
          return Array.isArray(row) ? row.map(normalizeStructuredTableCell) : [];
        })
      : [],
    caption: String(table.caption || ""),
    mobileStrategy: String(table.mobileStrategy || "scroll"),
  };
}

function buildStructuredRenderableBlocks(canonical) {
  var blocks = canonical && Array.isArray(canonical.blocks) ? canonical.blocks : [];
  var out = [];

  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    if (!block || block.type === renderSchema.BLOCK_TYPES.mcq) continue;

    if (block.type === renderSchema.BLOCK_TYPES.table) {
      var headers = Array.isArray(block.headers) ? block.headers : [];
      var rows = Array.isArray(block.rows) ? block.rows : [];
      out.push({
        id: "structured-table-" + i,
        type: "table",
        isStructured: true,
        headers: headers.map(normalizeStructuredTableCell),
        rows: rows.map(function (row) {
          return Array.isArray(row) ? row.map(normalizeStructuredTableCell) : [];
        }),
        caption: String(block.caption || ""),
        mobileStrategy: String(block.mobileStrategy || "scroll"),
      });
      continue;
    }

    if (block.type === renderSchema.BLOCK_TYPES.steps) {
      var steps = Array.isArray(block.steps) ? block.steps : [];
      out.push({
        id: "structured-steps-" + i,
        type: "steps",
        isStructured: true,
        title: String(block.title || ""),
        steps: steps.map(function (step, stepIndex) {
          var rawStep = step && typeof step === "object" ? step : {};
          return {
            index: rawStep.index || stepIndex + 1,
            title: String(rawStep.title || rawStep.text || rawStep.label || ""),
            detail: String(rawStep.detail || rawStep.summary || rawStep.content || ""),
            status: String(rawStep.status || "todo"),
          };
        }),
      });
      continue;
    }

    if (block.type === renderSchema.BLOCK_TYPES.recap) {
      out.push({
        id: "structured-recap-" + i,
        type: "recap",
        isStructured: true,
        title: String(block.title || "教学总结"),
        summary: String(block.summary || ""),
        bullets: Array.isArray(block.bullets)
          ? block.bullets.map(function (item) {
              return String(item || "");
            })
          : [],
      });
      continue;
    }

    if (block.type === renderSchema.BLOCK_TYPES.chart) {
      out.push({
        id: "structured-chart-" + i,
        type: "chart",
        isStructured: true,
        chartType: String(block.chartType || "line"),
        title: String(block.title || ""),
        summary: String(block.summary || ""),
        series: Array.isArray(block.series) ? block.series.map(normalizeStructuredChartSeries) : [],
        axes: {
          x: String(block.axes && block.axes.x ? block.axes.x : ""),
          y: String(block.axes && block.axes.y ? block.axes.y : ""),
        },
        legend: Array.isArray(block.legend)
          ? block.legend.map(function (item) {
              return String(item || "");
            })
          : [],
        caption: String(block.caption || ""),
        fallbackTable: normalizeStructuredChartTable(block.fallbackTable),
      });
      continue;
    }

    if (
      block.type === renderSchema.BLOCK_TYPES.formula_inline ||
      block.type === renderSchema.BLOCK_TYPES.formula_block
    ) {
      out.push({
        id: "structured-formula-" + i,
        type: block.type,
        isStructured: true,
        latex: String(block.latex || ""),
        displayText: String(block.displayText || block.latex || ""),
        svgUrl: String(block.svgUrl || ""),
        copyText: String(block.copyText || block.latex || block.displayText || ""),
      });
      continue;
    }
  }

  return out;
}

function buildPresentationState(presentation) {
  if (!presentation || typeof presentation !== "object") return null;
  var canonical = renderSchema.createCanonicalMessage(presentation);
  var blocks = Array.isArray(canonical.blocks) ? canonical.blocks : [];
  var mcqBlock = null;

  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    if (!block || block.type !== renderSchema.BLOCK_TYPES.mcq) continue;
    if (!Array.isArray(block.questions) || !block.questions.length) continue;
    mcqBlock = block;
    break;
  }

  return {
    canonical: canonical,
    renderBlocks: buildStructuredRenderableBlocks(canonical),
    cards: mcqBlock ? mcqBlock.questions : null,
    hint: mcqBlock ? mcqBlock.submitHint || "请选择后提交答案" : "",
    receipt: mcqBlock ? mcqBlock.receipt || "" : "",
    interactiveReady: mcqBlock ? mcqBlock.reviewMode !== true : false,
    hasStructuredContent: blocks.length > 0,
  };
}

function deriveAiMessageRenderState(input) {
  var content = String((input && input.content) || "");
  var presentation =
    input && input.presentation && typeof input.presentation === "object"
      ? input.presentation
      : null;
  var parseBlocks = !!(input && input.parseBlocks);
  var presentationState = buildPresentationState(presentation);
  var renderableContent = presentationState && presentationState.canonical
    ? String(
        presentationState.canonical.fallbackText ||
          mcqDetect.stripReceipt(content),
      )
    : mcqDetect.stripReceipt(content);
  var canonicalMessage =
    presentationState && presentationState.canonical
      ? presentationState.canonical
      : renderSchema.createCanonicalMessage({
          blocks: [],
          fallbackText: renderableContent,
          meta: {
            streamingMode: parseBlocks ? "parsed" : "plain",
          },
        });
  var markdownBlocks =
    parseBlocks && !(presentationState && presentationState.hasStructuredContent)
      ? md.parseWithIds(renderableContent || "")
      : null;

  return renderSchema.createRenderModel({
    renderableContent: renderableContent,
    blocks: presentationState && presentationState.hasStructuredContent
      ? presentationState.renderBlocks
      : markdownBlocks,
    mcqCards: presentationState ? presentationState.cards : null,
    mcqHint: presentationState ? presentationState.hint : "",
    mcqReceipt: presentationState ? presentationState.receipt || "" : "",
    mcqInteractiveReady: presentationState
      ? presentationState.interactiveReady
      : false,
    visibleBlocks: canonicalMessage.blocks,
    plainTextFallback: renderableContent,
    hasStructuredContent: !!canonicalMessage.blocks.length,
    streamPhase: "complete",
  });
}

module.exports = {
  deriveAiMessageRenderState: deriveAiMessageRenderState,
};
