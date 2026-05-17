// utils/ai-message-state.js — 统一 AI 消息的正文/题卡渲染状态
var md = require("./markdown");
var mcqDetect = require("./mcq-detect");
var markdownNormalize = require("./markdown-normalize");
var renderSchema = require("./render-schema");

var INTERNAL_FALLBACK = "暂时未生成适合直接展示的答案，请重试一次。";
var INTERNAL_PATTERNS = [
  /<\s*\|?\s*DSML\s*\|?/i,
  /\bDSML\b[\s\S]{0,80}\b(?:toolcalls?|invoke|parameter)\b/i,
  /\binvoke\s+name=["']?(?:readfile|read_file|writefile|write_file|listdir|list_dir)/i,
  /\bparameter\s+name=["']?filepath["']?/i,
  /\/app\/data\/tutorbot\/[\s\S]{0,240}\/workspace\/skills\/(?:memory|references)\//i,
  /\b(?:read_file|readfile|toolcall|web_search)\s+(?:path|query|args)=/i,
];

function coerceUserVisibleContent(text) {
  var source = String(text || "").trim();
  if (!source) return "";
  var normalized = source.replace(/\s+/g, " ");
  for (var i = 0; i < INTERNAL_PATTERNS.length; i++) {
    if (INTERNAL_PATTERNS[i].test(normalized)) {
      return INTERNAL_FALLBACK;
    }
  }
  return source;
}

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
  var renderBlocks = buildStructuredRenderableBlocks(canonical);

  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    if (!block || block.type !== renderSchema.BLOCK_TYPES.mcq) continue;
    if (!Array.isArray(block.questions) || !block.questions.length) continue;
    mcqBlock = block;
    break;
  }

  return {
    canonical: canonical,
    renderBlocks: renderBlocks,
    cards: mcqBlock ? mcqBlock.questions : null,
    hint: mcqBlock ? mcqBlock.submitHint || "请选择后提交答案" : "",
    receipt: mcqBlock ? mcqBlock.receipt || "" : "",
    interactiveReady: mcqBlock ? mcqBlock.reviewMode !== true : false,
    hasStructuredContent: blocks.length > 0,
    hasNonMcqStructuredContent: renderBlocks.length > 0,
    hasOnlyMcqContent: !!mcqBlock && renderBlocks.length === 0,
  };
}

function normalizeProjectionSignature(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*/g, "")
    .replace(/\s+/g, "")
    .replace(/[，。；：、,.!！?？()[\]（）【】《》"'“”‘’_\-—]/g, "")
    .toLowerCase();
}

function buildMcqProjectionSignature(cards) {
  var items = Array.isArray(cards) ? cards : [];
  var parts = [];
  for (var i = 0; i < items.length; i++) {
    var card = items[i] || {};
    parts.push(card.stem || "");
    var options = Array.isArray(card.options) ? card.options : [];
    for (var j = 0; j < options.length; j++) {
      parts.push(options[j] && options[j].key ? options[j].key : "");
      parts.push(options[j] && options[j].text ? options[j].text : "");
    }
  }
  return normalizeProjectionSignature(parts.join("\n"));
}

function hasMeaningfulFallbackOutsideMcq(fallbackText, cards) {
  var fallback = String(fallbackText || "").trim();
  if (!fallback) return false;
  var fallbackSignature = normalizeProjectionSignature(fallback);
  var mcqSignature = buildMcqProjectionSignature(cards);
  if (!fallbackSignature) return false;
  if (!mcqSignature) return true;
  if (fallbackSignature === mcqSignature || mcqSignature.indexOf(fallbackSignature) >= 0) {
    return false;
  }
  if (fallbackSignature.length > mcqSignature.length + 80) return true;
  return /结论|判断依据|核心考点|考试场景|采分点|易错点|解析|自查问题/.test(fallback);
}

function shouldRenderStructuredFallback(presentationState, fallbackText) {
  if (!presentationState || !presentationState.canonical) return true;
  var blocks = Array.isArray(presentationState.canonical.blocks)
    ? presentationState.canonical.blocks
    : [];
  if (!blocks.length) return true;
  if (presentationState.hasOnlyMcqContent) return false;

  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    var type = block && block.type;
    if (
      type === renderSchema.BLOCK_TYPES.table ||
      type === renderSchema.BLOCK_TYPES.formula_block ||
      type === renderSchema.BLOCK_TYPES.chart ||
      type === renderSchema.BLOCK_TYPES.image
    ) {
      continue;
    }
    return false;
  }
  return true;
}

function hasTeachingSemanticFallback(text) {
  return /(?:^|\n)\s*(?:#{1,6}\s*)?(?:核心结论|结论|判断依据|考试采分点|拿分要点|得分点|评分点|采分点|拉分关键|易错点提醒|易错提醒|易错点|失分点|扣分点|记忆口诀|小技巧|速记|助记|口诀|下一步建议|下一步学习|下一步|学习建议|复习建议|训练建议|行动建议|后续建议|建议下一步)(?:\s*[-—–]\s*[^：:\n]{1,18})?\s*(?:[：:]|\n|$)/.test(
    String(text || ""),
  );
}

function parseTeachingFallbackBlocks(text) {
  var blocks = md.parseWithIds(String(text || ""));
  var out = [];
  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    if (!block || block.type !== "callout") continue;
    var callout = Object.assign({}, block);
    var bodyParts = callout.content && callout.content.length
      ? [_inlineSpansToText(callout.content)]
      : [];
    var j = i + 1;
    while (j < blocks.length) {
      var next = blocks[j];
      if (!next || next.type === "heading" || next.type === "callout") break;
      if (next.type === "blank") {
        if (bodyParts.length && bodyParts[bodyParts.length - 1] !== "") bodyParts.push("");
        j++;
        continue;
      }
      var nextText = stringifyTeachingBodyBlock(next);
      if (!nextText) break;
      bodyParts.push(nextText);
      j++;
    }
    var bodyText = bodyParts.join("\n").trim();
    if (bodyText) {
      callout.content = md.parseInline(bodyText);
      callout.nodes = md.spansToRichTextNodes(callout.content);
    }
    out.push(callout);
  }
  return out;
}

function stringifyTeachingBodyBlock(block) {
  if (!block || typeof block !== "object") return "";
  if (block.type === "paragraph") return String(block.raw || block.text || "").trim();
  if ((block.type === "ul" || block.type === "ol") && Array.isArray(block.items)) {
    return block.items
      .map(function (item, idx) {
        var text = String((item && item.raw) || "").trim();
        if (!text) return "";
        if (block.type === "ol") return String((item && item.index) || idx + 1) + ". " + text;
        return "- " + text;
      })
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return "";
}

function _inlineSpansToText(spans) {
  return (Array.isArray(spans) ? spans : [])
    .map(function (span) {
      return String((span && span.text) || "");
    })
    .join("");
}

function deriveAiMessageRenderState(input) {
  var content = coerceUserVisibleContent((input && input.content) || "");
  var presentation =
    input && input.presentation && typeof input.presentation === "object"
      ? input.presentation
      : null;
  var parseBlocks = !!(input && input.parseBlocks);
  var presentationState = buildPresentationState(presentation);
  var fallbackContent =
    presentationState && presentationState.canonical
      ? presentationState.canonical.fallbackText || mcqDetect.stripReceipt(content)
      : mcqDetect.stripReceipt(content);
  var renderStructuredFallback = shouldRenderStructuredFallback(
    presentationState,
    fallbackContent,
  );
  var renderableContent = presentationState && presentationState.canonical
    ? String(renderStructuredFallback ? fallbackContent : "")
    : mcqDetect.stripReceipt(content);
  renderableContent = markdownNormalize.normalizeMarkdownForWechat(
    renderableContent || "",
  );
  var normalizedFallbackContent = markdownNormalize.normalizeMarkdownForWechat(
    fallbackContent || "",
  );
  var useStructuredBlocks = !!(
    presentationState && presentationState.hasNonMcqStructuredContent
  );
  var shouldAppendTeachingFallbackBlocks = !!(
    parseBlocks &&
    presentationState &&
    presentationState.canonical &&
    presentationState.cards &&
    presentationState.cards.length &&
    normalizedFallbackContent &&
    hasTeachingSemanticFallback(normalizedFallbackContent)
  );
  var teachingFallbackBlocks = shouldAppendTeachingFallbackBlocks
    ? parseTeachingFallbackBlocks(normalizedFallbackContent)
    : null;
  shouldAppendTeachingFallbackBlocks = !!(
    teachingFallbackBlocks && teachingFallbackBlocks.length
  );
  var shouldAppendFullFallbackBlocks = !!(
    parseBlocks &&
    presentationState &&
    presentationState.canonical &&
    !renderStructuredFallback &&
    !shouldAppendTeachingFallbackBlocks &&
    normalizedFallbackContent &&
    hasTeachingSemanticFallback(normalizedFallbackContent)
  );
  var fullFallbackBlocks = shouldAppendFullFallbackBlocks
    ? md.parseWithIds(normalizedFallbackContent)
    : null;
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
    shouldAppendTeachingFallbackBlocks
        ? teachingFallbackBlocks
      : shouldAppendFullFallbackBlocks
        ? fullFallbackBlocks
      : parseBlocks && !useStructuredBlocks
        ? md.parseWithIds(renderableContent || "")
      : null;
  var shouldFoldOriginal = !!(
    presentationState &&
    presentationState.cards &&
    presentationState.cards.length &&
    normalizedFallbackContent &&
    !renderableContent
  );

  return renderSchema.createRenderModel({
    renderableContent: shouldAppendTeachingFallbackBlocks ? "" : renderableContent,
    blocks: useStructuredBlocks
      ? presentationState.renderBlocks.concat(markdownBlocks || [])
      : markdownBlocks,
    mcqCards: presentationState ? presentationState.cards : null,
    mcqHint: presentationState ? presentationState.hint : "",
    mcqReceipt: presentationState ? presentationState.receipt || "" : "",
    mcqInteractiveReady: presentationState
      ? presentationState.interactiveReady
      : false,
    originalContent: shouldFoldOriginal ? normalizedFallbackContent : "",
    originalCollapsed: true,
    visibleBlocks: canonicalMessage.blocks,
    plainTextFallback: renderableContent,
    hasStructuredContent: useStructuredBlocks,
    streamPhase: "complete",
  });
}

module.exports = {
  deriveAiMessageRenderState: deriveAiMessageRenderState,
  coerceUserVisibleContent: coerceUserVisibleContent,
};
