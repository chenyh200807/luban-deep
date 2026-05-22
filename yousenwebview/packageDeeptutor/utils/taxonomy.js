// utils/taxonomy.js — chapter taxonomy 单一权威。
//
// 把 chapter code (1A411..1A432) 映射到对用户可读的中文章节名。原本
// 这份映射只活在 assessment.js 内部，report.js 自定义了 "知识点 " + code
// 的输出，导致：
//
//   1. 报告页面对学生显示 "知识点 1A412030 100"，把内部 chapter code
//      直接暴露到 UI（test_report_radar_authority.js 中明确不允许）。
//   2. assessment.js 与 report.js 的 chapter 名解析行为不一致，违反
//      single-authority 原则。
//
// 把 CHAPTER_CODE_LABELS + displayChapterName 抽到这里作为唯一来源，
// report.js / assessment.js 都引用。chapter code 形如 "1A412030"（8 位），
// 取前 5 位 "1A412" 去查 label。
//
// fallback 由调用方传入，因为不同 surface 对 "未知章节" 有不同语义：
//   - assessment 使用 "综合能力" (合理但 test_report_snapshot_dedupe 视
//     之为 meaningless，禁止 report.js 用)
//   - report 使用 "未归类能力" 等更具体的措辞
// 不在本模块硬编码 fallback，留给 caller 控制。

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
