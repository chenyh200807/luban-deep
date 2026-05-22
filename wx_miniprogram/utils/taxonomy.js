// utils/taxonomy.js — wx_miniprogram shadow contract 副本。
//
// 主权威：yousenwebview/packageDeeptutor/utils/taxonomy.js。
// 把 chapter code (1A411..1A432) 映射到对用户可读的中文章节名。

var CHAPTER_CODE_LABELS = {
  "1A411": "建筑设计与构造",
  "1A412": "结构设计与建筑材料",
  "1A413": "装配式建筑",
  "1A414": "建筑工程材料",
  "1A415": "建筑工程施工技术",
  "1A421": "项目组织管理",
  "1A422": "施工进度管理",
  "1A423": "施工质量管理",
  "1A424": "施工安全管理",
  "1A425": "合同与招投标管理",
  "1A426": "施工成本管理",
  "1A427": "资源与现场管理",
  "1A431": "建筑工程法规",
  "1A432": "建筑工程技术标准",
};

function _isChapterCode(text) {
  return /^1A\d{6}$/i.test(text);
}

function resolveChapterCodeLabel(value) {
  var text = String(value || "").trim();
  if (!_isChapterCode(text)) return null;
  return CHAPTER_CODE_LABELS[text.slice(0, 5).toUpperCase()] || null;
}

function displayChapterName(value, fallback) {
  var text = String(value || "").trim();
  var resolved = resolveChapterCodeLabel(text);
  if (resolved) return resolved;
  return text || fallback || "";
}

module.exports = {
  CHAPTER_CODE_LABELS: CHAPTER_CODE_LABELS,
  resolveChapterCodeLabel: resolveChapterCodeLabel,
  displayChapterName: displayChapterName,
};
