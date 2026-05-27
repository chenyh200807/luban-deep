// utils/taxonomy.js — compiled taxonomy authority 的小程序展示副本。
//
// 主权威：deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json。
// 本文件只做前端显示，不参与章节/主题身份判断。chapter code 形如
// "1A412030" 或 "1A411011-02-d"，取前 5 位 "1A412" 去查 label。
//
// fallback 由调用方传入，因为不同 surface 对 "未知章节" 有不同语义：
//   - assessment 使用 "综合能力" (合理但 test_report_snapshot_dedupe 视
//     之为 meaningless，禁止 report.js 用)
//   - report 使用 "未归类能力" 等更具体的措辞
// 不在本模块硬编码 fallback，留给 caller 控制。

var CHAPTER_CODE_LABELS = {
  "1A410": "建筑工程技术",
  "1A411": "建筑设计与构造",
  "1A412": "主要建筑工程材料的性能与应用",
  "1A413": "建筑工程施工技术",
  "1A422": "第4章 相关法规",
  "1A425": "相关标准",
  "1A431": "建筑工程项目管理实务",
  "1A432": "工程招标投标与合同管理",
  "1A433": "施工进度管理",
  "1A434": "施工质量管理",
  "1A435": "施工成本管理",
  "1A436": "施工安全管理",
  "1A437": "绿色建造及施工现场环境管理",
  "1A438": "施工资源管理",
};

function _isChapterCode(text) {
  return /^1A\d{3,6}(?:-\d{2})?(?:-[a-z])?$/i.test(text);
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
