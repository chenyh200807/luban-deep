// utils/markdown-normalize.js
// 微信小程序答案 markdown 归一化：把高风险写法收敛成稳定的移动端子集

var LABELLED_ORDERED_ITEM_RE = /^\s*(\d+)\.\s+\*\*([^*\n]+?)\*\*([：:])\s*(.+)$/;
var LABELLED_BULLET_ITEM_RE = /^\s*([-*+])\s+\*\*([^*\n]+?)\*\*([：:])\s*(.+)$/;
var LABELLED_PARAGRAPH_RE = /^\s*\*\*([^*\n]+?)\*\*([：:])\s*(.+)$/;
var LABELLED_ORDERED_ONLY_RE = /^\s*(\d+)\.\s+\*\*([^*\n]+?)\*\*([：:])\s*$/;
var LABELLED_BULLET_ONLY_RE = /^\s*([-*+])\s+\*\*([^*\n]+?)\*\*([：:])\s*$/;
var LABELLED_PARAGRAPH_ONLY_RE = /^\s*\*\*([^*\n]+?)\*\*([：:])\s*$/;
var INDENTED_LIST_RE = /^\s{2,}((?:[-*+])|\d+\.)\s+/;
var ADJACENT_HEADING_RE = /([^\n\sA-Za-z0-9#])((?:#{1,6})(?!#)(?=[\u4e00-\u9fff\d]))/g;
var COMPACT_HEADING_RE = /^(\s*)(#{1,6})(?!#)(?=\S)/;
var COMPACT_HEADING_ORDERED_RE = /^(\s*#{1,6}\s+)(\d+)\.(?!\d)(?=\S)/;
var COMPACT_ORDERED_LIST_RE = /^(\s*)(\d+)\.(?!\d)(?=\S)/;
var COMPACT_DASH_BULLET_RE = /^(\s*)-(?!-)(?=\S)/;

function normalizeMarkdownForWechat(text) {
  var normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!normalized.trim()) return "";

  var lines = expandNonFenceLines(normalized.split("\n"));
  var out = [];
  var inFence = false;
  var previousBlank = false;

  for (var i = 0; i < lines.length; i++) {
    var line = String(lines[i] || "").replace(/\s+$/, "");
    var stripped = line.replace(/^\s+/, "");

    if (/^```/.test(stripped)) {
      inFence = !inFence;
      out.push(line);
      previousBlank = false;
      continue;
    }

    if (inFence) {
      out.push(line);
      previousBlank = false;
      continue;
    }

    line = line.replace(/\t/g, "  ");
    if (!line.trim()) {
      if (previousBlank) continue;
      out.push("");
      previousBlank = true;
      continue;
    }

    previousBlank = false;
    line = line.replace(INDENTED_LIST_RE, "$1 ");
    line = line.replace(COMPACT_HEADING_RE, "$1$2 ");
    line = line.replace(COMPACT_HEADING_ORDERED_RE, "$1$2. ");
    line = line.replace(COMPACT_ORDERED_LIST_RE, "$1$2. ");
    line = line.replace(COMPACT_DASH_BULLET_RE, "$1- ");
    line = line.replace(/\s*→\s*/g, " → ");
    line = normalizeLabelledItem(line);
    out.push(line.replace(/\s+$/, ""));
  }

  return out.join("\n").trim();
}

function expandNonFenceLines(lines) {
  var out = [];
  var inFence = false;
  for (var i = 0; i < lines.length; i++) {
    var line = String(lines[i] || "");
    var stripped = line.replace(/^\s+/, "");
    if (/^```/.test(stripped)) {
      out.push(line);
      inFence = !inFence;
      continue;
    }
    if (inFence) {
      out.push(line);
      continue;
    }
    var expanded = line.replace(ADJACENT_HEADING_RE, "$1\n$2").split("\n");
    for (var j = 0; j < expanded.length; j++) {
      out.push(expanded[j]);
    }
  }
  return out;
}

function normalizeLabelledItem(line) {
  var match = line.match(LABELLED_ORDERED_ONLY_RE);
  if (match) {
    return match[1] + ". **" + match[2].trim() + "：**";
  }

  match = line.match(LABELLED_ORDERED_ITEM_RE);
  if (match) {
    return match[1] + ". **" + match[2].trim() + "：** " + match[4].trim();
  }

  match = line.match(LABELLED_BULLET_ONLY_RE);
  if (match) {
    return match[1] + " **" + match[2].trim() + "：**";
  }

  match = line.match(LABELLED_BULLET_ITEM_RE);
  if (match) {
    return match[1] + " **" + match[2].trim() + "：** " + match[4].trim();
  }

  match = line.match(LABELLED_PARAGRAPH_ONLY_RE);
  if (match) {
    return "**" + match[1].trim() + "：**";
  }

  match = line.match(LABELLED_PARAGRAPH_RE);
  if (match) {
    return "**" + match[1].trim() + "：** " + match[3].trim();
  }

  return line;
}

module.exports = {
  normalizeMarkdownForWechat: normalizeMarkdownForWechat,
};
