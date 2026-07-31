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
  return renderSchema.sanitizeAuthorityMarkdownText
    ? renderSchema.sanitizeAuthorityMarkdownText(source)
    : source;
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

// 单一权威：小程序端**真的**有渲染分支的 canonical block 类型。
// mcq 走 mcqCards 单独渲染，其余见 buildStructuredRenderableBlocks() 的分支。
// canonical schema 还允许 paragraph/heading/callout/quote/code/list/image，
// 它们在小程序端没有结构化渲染分支，只能靠 fallbackText（正文）承载——
// 所以判断"能否吞掉正文"时必须以本表为准，不能另起一份名单（见下方事故说明）。
var STRUCTURED_RENDERED_BLOCK_TYPES = {};
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.mcq] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.table] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.steps] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.recap] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.chart] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.formula_inline] = true;
STRUCTURED_RENDERED_BLOCK_TYPES[renderSchema.BLOCK_TYPES.formula_block] = true;

// 这些块渲染出来就是正文本身（题干/步骤/总结），再渲染一遍 fallbackText 会重复。
var PROSE_SUBSUMING_BLOCK_TYPES = {};
PROSE_SUBSUMING_BLOCK_TYPES[renderSchema.BLOCK_TYPES.mcq] = true;
PROSE_SUBSUMING_BLOCK_TYPES[renderSchema.BLOCK_TYPES.steps] = true;
PROSE_SUBSUMING_BLOCK_TYPES[renderSchema.BLOCK_TYPES.recap] = true;

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
    reviewMode: !!(mcqBlock && mcqBlock.reviewMode),
    hasStructuredContent: blocks.length > 0,
    hasNonMcqStructuredContent: renderBlocks.length > 0,
    hasOnlyMcqContent: !!mcqBlock && renderBlocks.length === 0,
  };
}

function sanitizePresentationForState(presentation) {
  if (!presentation || typeof presentation !== "object") return null;
  return renderSchema.createCanonicalMessage(presentation);
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

// 只有当「每个块都真的渲染得出来」且「其中至少有一个块就是正文本身」时，
// 才允许吞掉 fallbackText。任何一个没有渲染分支的类型都必须保留正文——
// 宁可重复也绝不丢答案（fail-open），未来新增的未知类型同样按保留处理。
//
// 事故记忆（2026-07-31 线上「答案不显示」）：这里原先是一份独立维护的「豁免名单」
// {table, formula_block, chart, image}，遇到名单外的类型就 return false 吞掉正文；
// 而 buildStructuredRenderableBlocks 只渲染 {table,steps,recap,chart,formula_*}。
// 两份名单的差集 {paragraph,heading,callout,quote,code,list} 于是既被吞掉正文、
// 又渲染不出块，导致服务端发了 3000+ 字的答案而客户端一个字都不显示。
// 现在两处共用 STRUCTURED_RENDERED_BLOCK_TYPES，名单无法再各自漂移。
function shouldRenderStructuredFallback(presentationState, fallbackText) {
  if (!presentationState || !presentationState.canonical) return true;
  var blocks = Array.isArray(presentationState.canonical.blocks)
    ? presentationState.canonical.blocks
    : [];
  if (!blocks.length) return true;
  if (presentationState.hasOnlyMcqContent) return false;

  var sawProseSubsumingBlock = false;
  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    var type = block && block.type;
    // 没有渲染分支的类型（含未知的新类型）：正文是它唯一的载体，必须保留。
    if (!STRUCTURED_RENDERED_BLOCK_TYPES[type]) return true;
    if (PROSE_SUBSUMING_BLOCK_TYPES[type]) sawProseSubsumingBlock = true;
  }
  // 全是 table/chart/formula 这类图示型块时，它们不承载正文，正文必须并存。
  return !sawProseSubsumingBlock;
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
    mcqReviewMode: presentationState ? presentationState.reviewMode : false,
    originalContent: shouldFoldOriginal ? normalizedFallbackContent : "",
    originalCollapsed: true,
    visibleBlocks: canonicalMessage.blocks,
    plainTextFallback: renderableContent,
    hasStructuredContent: useStructuredBlocks,
    streamPhase: "complete",
    progressiveDisclosure: renderSchema.sanitizeProgressiveDisclosure
      ? renderSchema.sanitizeProgressiveDisclosure(input && (input.progressiveDisclosure || input.progressive_disclosure))
      : null,
  });
}

module.exports = {
  deriveAiMessageRenderState: deriveAiMessageRenderState,
  coerceUserVisibleContent: coerceUserVisibleContent,
  sanitizePresentationForState: sanitizePresentationForState,
};
