// utils/markdown.js — Markdown 解析器（微信小程序）
// 支持：标题 · 加粗/斜体 · 有序/无序/圆圈列表 · 代码块 · 行内代码
//       表格 · 引用块 · 核心结论/注意高亮 · 水平线 · 段落

// ── 常量 ──────────────────────────────────────────────────
var CIRCLED_RE = /[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]/g;
var CIRCLED_SPLIT_RE = /(?=[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])/;
var CIRCLED_PREFIX_RE = /^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*/;

// 核心高亮关键词映射
var CALLOUT_VARIANTS = {
  conclusion: ["核心结论", "最终答案", "答案", "结论", "心得"],
  warning: ["注意", "注意事项", "易错点", "陷阱", "警告", "易混淆"],
  highlight: [
    "关键要点",
    "重点",
    "考点",
    "要点",
    "考点提示",
    "知识点",
    "踩分点",
  ],
  tip: ["小技巧", "记忆口诀", "速记", "助记", "口诀"],
};
var _allCalloutKeywords = [];
Object.keys(CALLOUT_VARIANTS).forEach(function (v) {
  CALLOUT_VARIANTS[v].forEach(function (kw) {
    _allCalloutKeywords.push(kw);
  });
});
_allCalloutKeywords.sort(function (a, b) {
  return b.length - a.length;
});
var CALLOUT_RE = new RegExp(
  "^\\*\\*\\s*(" +
    _allCalloutKeywords.join("|") +
    ")\\s*[：:]?\\s*\\*\\*\\s*[：:]?\\s*(.*)",
);

function _findCalloutVariant(keyword) {
  var variants = Object.keys(CALLOUT_VARIANTS);
  for (var i = 0; i < variants.length; i++) {
    if (CALLOUT_VARIANTS[variants[i]].indexOf(keyword) !== -1)
      return variants[i];
  }
  return "highlight";
}

// ── 主解析函数 ────────────────────────────────────────────
function parse(text) {
  if (!text || typeof text !== "string") return [];

  var lines = text.replace(/\r\n?/g, "\n").split("\n");
  var blocks = [];
  var i = 0;

  while (i < lines.length) {
    var line = lines[i];

    // ── 代码块 ────────────────────────────────────────
    if (line.startsWith("```")) {
      var language = line.slice(3).trim() || "text";
      var codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      blocks.push({
        type: "code_block",
        language: language,
        content: codeLines.join("\n"),
      });
      i++;
      continue;
    }

    // ── 标题 H1-H3 ───────────────────────────────────
    var hMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (hMatch) {
      blocks.push({
        type: "heading",
        level: hMatch[1].length,
        content: parseInline(hMatch[2]),
        raw: hMatch[2],
      });
      i++;
      continue;
    }

    // ── 水平线 ────────────────────────────────────────
    if (/^---+$/.test(line) || /^\*\*\*+$/.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // ── 表格（管道分隔）───────────────────────────────
    if (line.trim().indexOf("|") !== -1 && _looksLikeTableRow(line)) {
      var tableLines = [];
      while (
        i < lines.length &&
        lines[i].trim().indexOf("|") !== -1 &&
        _looksLikeTableRow(lines[i])
      ) {
        tableLines.push(lines[i]);
        i++;
      }
      var table = _parseTable(tableLines);
      if (table) {
        blocks.push(table);
        continue;
      }
      for (var t = 0; t < tableLines.length; t++) {
        blocks.push({
          type: "paragraph",
          content: parseInline(tableLines[t]),
          raw: tableLines[t],
        });
      }
      continue;
    }

    // ── 引用块 ────────────────────────────────────────
    if (line.startsWith("> ") || line === ">") {
      var quoteLines = [];
      while (
        i < lines.length &&
        (lines[i].startsWith("> ") || lines[i] === ">")
      ) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      blocks.push({
        type: "blockquote",
        lines: quoteLines.map(function (ql) {
          return parseInline(ql);
        }),
        raw: quoteLines.join("\n"),
      });
      continue;
    }

    // ── 无序列表 ──────────────────────────────────────
    if (/^[-*+]\s+/.test(line)) {
      var items = [];
      while (i < lines.length && /^[-*+]\s+/.test(lines[i])) {
        var itemText = lines[i].replace(/^[-*+]\s+/, "");
        items.push({
          content: parseInline(itemText),
          raw: itemText,
        });
        i++;
      }
      blocks.push({ type: "ul", items: items });
      continue;
    }

    // ── 有序列表 ──────────────────────────────────────
    if (/^\d+\.\s+/.test(line)) {
      var olItems = [];
      var order = 1;
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        var olText = lines[i].replace(/^\d+\.\s+/, "");
        olItems.push({
          index: order++,
          content: parseInline(olText),
          raw: olText,
        });
        i++;
      }
      blocks.push({ type: "ol", items: olItems });
      continue;
    }

    // ── 圆圈序号列表 ─────────────────────────────────
    if (CIRCLED_PREFIX_RE.test(line)) {
      var cItems = [];
      while (i < lines.length && CIRCLED_PREFIX_RE.test(lines[i])) {
        var cleaned = lines[i]
          .replace(CIRCLED_PREFIX_RE, "")
          .replace(/[；;]\s*$/, "");
        cItems.push({
          index: cItems.length + 1,
          content: parseInline(cleaned),
          raw: cleaned,
        });
        i++;
      }
      blocks.push({ type: "ol", items: cItems });
      continue;
    }

    // ── 空行 ──────────────────────────────────────────
    if (line.trim() === "") {
      if (blocks.length > 0 && blocks[blocks.length - 1].type !== "blank") {
        blocks.push({ type: "blank" });
      }
      i++;
      continue;
    }

    // ── 段落（连续非空行应收拢为同一段）──────────────────
    var paragraphLines = [line];
    i++;
    while (i < lines.length && !_startsNewBlock(lines[i])) {
      paragraphLines.push(lines[i]);
      i++;
    }
    var paragraphText = _joinParagraphLines(paragraphLines);
    blocks.push({
      type: "paragraph",
      content: parseInline(paragraphText),
      raw: paragraphText,
    });
  }

  while (blocks.length > 0 && blocks[blocks.length - 1].type === "blank") {
    blocks.pop();
  }

  var result = _splitInlineCircledNums(blocks);
  result = _detectCallouts(result);
  return result;
}

function _startsNewBlock(line) {
  if (typeof line !== "string") return true;
  if (line.trim() === "") return true;
  if (line.startsWith("```")) return true;
  if (/^(#{1,6})\s+(.+)$/.test(line)) return true;
  if (/^---+$/.test(line) || /^\*\*\*+$/.test(line)) return true;
  if (line.trim().indexOf("|") !== -1 && _looksLikeTableRow(line)) return true;
  if (line.startsWith("> ") || line === ">") return true;
  if (/^[-*+]\s+/.test(line)) return true;
  if (/^\d+\.\s+/.test(line)) return true;
  if (CIRCLED_PREFIX_RE.test(line)) return true;
  return false;
}

function _joinParagraphLines(lines) {
  var parts = Array.isArray(lines) ? lines : [];
  var result = "";
  for (var i = 0; i < parts.length; i++) {
    var line = String(parts[i] || "").trim();
    if (!line) continue;
    if (!result) {
      result = line;
      continue;
    }
    result += _needsInlineSpace(result.charAt(result.length - 1), line.charAt(0))
      ? " " + line
      : line;
  }
  return result;
}

function _needsInlineSpace(prevChar, nextChar) {
  if (!prevChar || !nextChar) return false;
  if (/\s/.test(prevChar) || /\s/.test(nextChar)) return false;
  if (_isCjkChar(prevChar) || _isCjkChar(nextChar)) return false;
  if (_isOpeningPunctuation(prevChar) || _isClosingPunctuation(nextChar)) return false;
  return /[A-Za-z0-9]/.test(prevChar) && /[A-Za-z0-9]/.test(nextChar);
}

function _isCjkChar(ch) {
  return /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(ch);
}

function _isOpeningPunctuation(ch) {
  return /[([{\u201c\u2018\u300a\u3008\u3010\u3014\uff08]/.test(ch);
}

function _isClosingPunctuation(ch) {
  return /[,.!?;:)\]}%\u201d\u2019\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f\u300b\u3009\u3011\u3015\uff09]/.test(ch);
}

// ── 表格解析 ──────────────────────────────────────────────

function _looksLikeTableRow(line) {
  var trimmed = line.trim();
  if (trimmed.charAt(0) === "|") return true;
  if (trimmed.indexOf(" | ") !== -1) return true;
  if (/^[\s|:-]+$/.test(trimmed) && trimmed.indexOf("|") !== -1) return true;
  return false;
}

function _parseTable(lines) {
  if (lines.length < 2) return null;

  var rows = lines.map(function (l) {
    l = l.trim();
    if (l.charAt(0) === "|") l = l.slice(1);
    if (l.charAt(l.length - 1) === "|") l = l.slice(0, -1);
    return l.split("|").map(function (cell) {
      return cell.trim();
    });
  });

  var hasSeparator = false;
  if (
    rows.length >= 2 &&
    rows[1].every(function (cell) {
      return /^[-:]+$/.test(cell);
    })
  ) {
    hasSeparator = true;
  }

  var headerRow = rows[0];
  var dataStart = hasSeparator ? 2 : 1;

  var headers = headerRow.map(function (cell) {
    return { content: parseInline(cell) };
  });

  var dataRows = [];
  for (var r = dataStart; r < rows.length; r++) {
    if (
      rows[r].every(function (cell) {
        return /^[-:]*$/.test(cell);
      })
    )
      continue;
    var rowCells = [];
    for (var c = 0; c < headers.length; c++) {
      var val = c < rows[r].length ? rows[r][c] : "";
      rowCells.push({ content: parseInline(val) });
    }
    dataRows.push(rowCells);
  }

  if (headers.length < 2 || dataRows.length < 1) return null;

  return {
    type: "table",
    headers: headers,
    rows: dataRows,
    colCount: headers.length,
  };
}

// ── 核心结论高亮检测 ──────────────────────────────────────

function _detectCallouts(blocks) {
  var result = [];
  for (var j = 0; j < blocks.length; j++) {
    var block = blocks[j];
    if (block.type !== "paragraph" || !block.raw) {
      result.push(block);
      continue;
    }

    var m = block.raw.match(CALLOUT_RE);
    if (!m) {
      result.push(block);
      continue;
    }

    var keyword = m[1];
    var bodyText = m[2].trim();
    var variant = _findCalloutVariant(keyword);

    result.push({
      type: "callout",
      variant: variant,
      label: keyword,
      content: bodyText ? parseInline(bodyText) : [],
      raw: block.raw,
    });
  }
  return result;
}

// ── 圆圈序号拆分 ─────────────────────────────────────────

function _splitInlineCircledNums(blocks) {
  var result = [];
  for (var j = 0; j < blocks.length; j++) {
    var block = blocks[j];
    if (block.type !== "paragraph" || !block.raw) {
      result.push(block);
      continue;
    }

    var matches = block.raw.match(CIRCLED_RE);
    if (!matches || matches.length < 2) {
      result.push(block);
      continue;
    }

    var firstPos = block.raw.indexOf(matches[0]);
    var prefix = block.raw
      .slice(0, firstPos)
      .replace(/[：:]\s*$/, "")
      .trim();
    var listPart = block.raw.slice(firstPos);

    if (prefix) {
      result.push({
        type: "paragraph",
        content: parseInline(prefix + "："),
        raw: prefix + "：",
      });
    }

    var parts = listPart.split(CIRCLED_SPLIT_RE).filter(function (p) {
      return p.trim();
    });
    var splitItems = parts.map(function (part, idx) {
      var cl = part
        .replace(CIRCLED_PREFIX_RE, "")
        .replace(/[；;。]\s*$/, "")
        .trim();
      return {
        index: idx + 1,
        content: parseInline(cl),
        raw: cl,
      };
    });

    if (splitItems.length >= 2) {
      result.push({ type: "ol", items: splitItems });
    } else {
      result.push(block);
    }
  }
  return result;
}

// ── 行内格式解析 ──────────────────────────────────────────

function parseInline(text) {
  if (!text || typeof text !== "string") return [{ type: "text", text: "" }];

  var spans = [];
  var pattern =
    /(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|__(.+?)__|`(.+?)`|\*(.+?)\*|_(.+?)_)/g;

  var lastIndex = 0;
  var match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      spans.push({ type: "text", text: text.slice(lastIndex, match.index) });
    }

    var full = match[1];
    if (full.startsWith("***")) {
      spans.push({ type: "bold_italic", text: match[2] });
    } else if (full.startsWith("**") || full.startsWith("__")) {
      spans.push({ type: "bold", text: match[3] || match[4] });
    } else if (full.startsWith("`")) {
      spans.push({ type: "code", text: match[5] });
    } else {
      spans.push({ type: "italic", text: match[6] || match[7] });
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    spans.push({ type: "text", text: text.slice(lastIndex) });
  }

  return spans.length > 0 ? spans : [{ type: "text", text: text }];
}

// ── 附加 ID ──────────────────────────────────────────────

function parseWithIds(text) {
  var blocks = parse(text);
  return blocks.map(function (block, idx) {
    block.id = "b" + idx;
    return block;
  });
}

module.exports = {
  parse: parse,
  parseInline: parseInline,
  parseWithIds: parseWithIds,
};
