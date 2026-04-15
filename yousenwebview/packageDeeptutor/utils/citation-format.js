// utils/citation-format.js — 将引用压缩成易读的“来源标签”

var CHAPTER_MAP = {
  "1A410": "建筑工程技术",
  "1A411": "建筑构造",
  "1A412": "装饰装修",
  "1A413": "结构设计",
  "1A414": "工程材料",
  "1A415": "建筑设备",
  "1A416": "智能化",
  "1A420": "施工管理",
  "1A421": "施工组织",
  "1A422": "进度控制",
  "1A423": "质量控制",
  "1A424": "安全管理",
  "1A425": "成本控制",
  "1A426": "合同管理",
  "1A430": "法规标准",
  "1A431": "建筑法规",
  "1A432": "标准规范",
  "1A434": "施工质量管理",
};

var STANDARD_RE = /(GB\/?T?|JGJ\/?T?|JGJ|CECS|DB\d{2,4})\s*[- ]?\s*(\d+(?:\.\d+)?(?:-\d{4})?)/i;
var CLAUSE_RE = /(?:§\s*|第)?(\d+(?:\.\d+){1,4})(?:条|节)?/;
var NODE_RE = /(1A\d{3}(?:\d{3})?)/;
var HEADING_RE = /#{1,6}\s*([^\n#]+)/g;
var OPAQUE_DOC_RE = /^(?:q\s*)?\d{4,}$/i;

function getChapterName(code) {
  return CHAPTER_MAP[code] || code;
}

function _clean(text) {
  return String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[*_`>#]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function _pickFirst() {
  for (var i = 0; i < arguments.length; i += 1) {
    var value = _clean(arguments[i]);
    if (value) return value;
  }
  return "";
}

function _extractStandard(docId, snippet) {
  var source = String(docId || "") + " " + String(snippet || "");
  var match = source.match(STANDARD_RE);
  if (!match) return "";
  return (match[1].toUpperCase() + " " + match[2]).replace(/\s+/g, " ").trim();
}

function _extractClause(snippet) {
  var match = String(snippet || "").match(CLAUSE_RE);
  return match ? match[1] : "";
}

function _extractHeadings(snippet) {
  var headings = [];
  var match;
  var source = String(snippet || "");
  while ((match = HEADING_RE.exec(source))) {
    var text = _clean(match[1]);
    if (text && headings.indexOf(text) === -1) headings.push(text);
    if (headings.length >= 2) break;
  }
  return headings;
}

function _extractNodeCode(docId, chunkId, snippet) {
  var source = [docId, chunkId, snippet].join(" ");
  var match = source.match(NODE_RE);
  return match ? match[1] : "";
}

function _isOpaqueDocId(docId) {
  var value = _clean(docId);
  if (!value) return false;
  if (value === "unknown") return true;
  return OPAQUE_DOC_RE.test(value);
}

function _sourceKindLabel(citation) {
  var sourceType = String(citation.source_type || "").toLowerCase();
  var sourceTable = String(citation.source_table || "").toLowerCase();
  if (sourceType === "exam" || sourceTable === "questions_bank" || sourceTable === "exam") {
    return "真题";
  }
  if (sourceType === "spec") return "规范";
  if (sourceType === "textbook") return "教材";
  if (sourceTable === "knowledge_cards") return "知识卡片";
  return "";
}

function _buildSourceMeta(citation) {
  var docId = String(citation.doc_id || "");
  var chunkId = String(citation.chunk_id || "");
  var snippet = String(citation.snippet || "");
  var sourceLabel = _clean(citation.source_label);
  var nodeCode = _pickFirst(citation.node_code, _extractNodeCode(docId, chunkId, snippet));
  var chapterCode = nodeCode ? nodeCode.slice(0, 5) : "";
  var chapterName = chapterCode ? getChapterName(chapterCode) : "";
  var examYear = _clean(citation.exam_year);
  var kind = _sourceKindLabel(citation);
  var parts = [];

  if (kind) parts.push(kind);
  if (sourceLabel) {
    parts.push(sourceLabel);
  } else if (kind === "真题" && examYear) {
    parts.push(examYear + "年真题");
  }
  if (chapterName) parts.push(chapterName);

  return parts.filter(Boolean);
}

function _buildTitle(citation) {
  var docId = String(citation.doc_id || "");
  var chunkId = String(citation.chunk_id || "");
  var snippet = String(citation.snippet || "");
  var sourceMeta = _buildSourceMeta(citation);

  if (sourceMeta.length) {
    return sourceMeta.join(" · ");
  }

  var standard = _extractStandard(docId, snippet);
  if (standard) {
    var clause = _extractClause(snippet) || _extractClause(docId);
    return clause ? standard + " · 第" + clause + "条" : standard;
  }

  var nodeCode = _extractNodeCode(docId, chunkId, snippet);
  if (nodeCode) {
    var chapterCode = nodeCode.slice(0, 5);
    var chapterName = getChapterName(chapterCode);
    var sourceLabel = _sourceKindLabel(citation) || (/^EXAM_/i.test(docId) ? "真题" : "教材");
    if (nodeCode.length >= 8) {
      return sourceLabel + " · " + chapterName + " · " + nodeCode.slice(0, 8);
    }
    return sourceLabel + " · " + chapterName;
  }

  var headings = _extractHeadings(snippet);
  if (headings.length) {
    return "教材 · " + headings.join(" · ");
  }

  var cleanedDoc = _clean(docId);
  if (cleanedDoc && !_isOpaqueDocId(cleanedDoc)) {
    return cleanedDoc;
  }

  if (_sourceKindLabel(citation)) {
    return _sourceKindLabel(citation) + "来源";
  }

  return _clean(snippet).slice(0, 30) || "参考资料";
}

function formatCitation(citation) {
  var next = citation || {};
  return {
    key: next.key || "",
    title: _buildTitle(next),
  };
}

function formatCitations(citations) {
  if (!Array.isArray(citations)) return [];
  return citations.map(formatCitation);
}

module.exports = {
  CHAPTER_MAP: CHAPTER_MAP,
  getChapterName: getChapterName,
  formatCitation: formatCitation,
  formatCitations: formatCitations,
};
