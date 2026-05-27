// utils/taxonomy.js — compiled taxonomy authority 的小程序展示副本。
//
// 主权威：deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json。
// 本文件只做前端显示，不参与章节/主题身份判断。

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

var TEXTBOOK_CHAPTERS = [
  { no: 1, name: "建筑工程设计技术", sections: ["建筑物的构成与设计要求", "建筑构造设计的基本要求", "建筑结构体系和设计作用（荷载）", "建筑结构设计构造基本要求", "装配式建筑设计基本要求"], prefixes: ["1A411"], aliases: ["建筑设计与构造", "建筑设计", "建筑物分类与构成", "建筑构造设计要求"] },
  { no: 2, name: "主要建筑工程材料的性能与应用", sections: ["结构工程材料", "装饰装修工程材料", "建筑功能材料"], prefixes: ["1A412"], aliases: ["建筑工程材料"] },
  { no: 3, name: "建筑工程施工技术", sections: ["施工测量", "土石方工程施工", "地基与基础工程施工", "主体结构工程施工", "屋面与防水工程施工", "装饰装修工程施工", "智能建造新技术", "季节性施工技术"], prefixes: ["1A413"], aliases: ["建筑工程施工技术"] },
  { no: 4, name: "相关法规", sections: ["建筑工程建设相关规定", "安全生产及施工现场管理相关规定"], prefixes: ["1A421", "1A422"], aliases: [] },
  { no: 5, name: "相关标准", sections: ["建筑设计及质量控制相关规定", "地基基础工程相关规定", "主体结构工程相关规定", "装饰装修与屋面工程相关规定", "绿色建造的相关规定"], prefixes: ["1A425"], aliases: [] },
  { no: 6, name: "建筑工程企业资质与施工组织", sections: ["建筑工程企业资质", "施工项目管理机构", "施工组织设计", "施工平面布置", "施工临时用电", "施工临时用水", "施工检验与试验", "工程施工资料"], prefixes: ["1A431"], aliases: [] },
  { no: 7, name: "工程招标投标与合同管理", sections: ["工程招标投标", "工程合同管理"], prefixes: ["1A432"], aliases: [] },
  { no: 8, name: "施工进度管理", sections: ["施工进度控制方法应用", "施工进度计划编制与控制"], prefixes: ["1A433"], aliases: [] },
  { no: 9, name: "施工质量管理", sections: ["项目质量计划管理", "项目施工质量检查与检验", "工程质量通病防治", "工程质量验收管理"], prefixes: ["1A434"], aliases: [] },
  { no: 10, name: "施工成本管理", sections: ["施工成本计划及分解", "施工成本分析与控制", "施工成本管理绩效评价与考核"], prefixes: ["1A435"], aliases: [] },
  { no: 11, name: "施工安全管理", sections: ["施工安全生产管理计划", "施工安全生产检查", "施工安全生产管理要点", "常见施工生产安全事故及预防"], prefixes: ["1A436"], aliases: [] },
  { no: 12, name: "绿色建造及施工现场环境管理", sections: ["绿色建造及信息化技术应用管理", "绿色施工及环境保护", "施工现场消防"], prefixes: ["1A437"], aliases: [] },
  { no: 13, name: "施工资源管理", sections: ["材料与半成品管理", "机械设备管理", "劳动用工管理"], prefixes: ["1A438"], aliases: [] },
];

var NON_TOPIC_LABELS = [
  "这题", "那题", "本题", "该题", "此题", "题目", "当前题", "当前题目",
  "这个题", "那个题", "这道题", "那道题", "这一题", "那一题",
  "这道题目", "那道题目", "当前考点", "当前知识点", "考卷", "试卷",
  "卷子", "综合练习", "练习证据",
];

function _isChapterCode(text) {
  return /^1A\d{3,6}(?:-\d+)?(?:-[a-z]+)?$/i.test(text);
}

function resolveChapterCodeLabel(value) {
  var text = String(value || "").trim();
  if (!_isChapterCode(text)) return null;
  return CHAPTER_CODE_LABELS[text.slice(0, 5).toUpperCase()] || null;
}

function textbookChapterDisplayName(chapter) {
  return "第" + chapter.no + "章 " + chapter.name;
}

function isNonTopicLabel(value) {
  var text = String(value || "").trim();
  if (!text) return true;
  var compact = _compact(text);
  if (NON_TOPIC_LABELS.indexOf(compact) >= 0) return true;
  if (text.indexOf("/") >= 0 || text.indexOf("／") >= 0) return true;
  if (_isChapterCode(text) && !resolveTextbookChapterByCode(text)) return true;
  return false;
}

function resolveTextbookTopic(value, taxonomyPath) {
  var text = String(value || "").trim();
  if (isNonTopicLabel(text)) return null;
  var path = Array.isArray(taxonomyPath)
    ? taxonomyPath.map(function (name) { return String(name || "").trim(); }).filter(Boolean)
    : [];
  var chapter = _isChapterCode(text) ? resolveTextbookChapterByCode(text) : null;
  var section = "";
  if (!chapter) {
    [text].concat(path).some(function (candidate) {
      chapter = resolveTextbookChapterByLabel(candidate);
      if (chapter) {
        section = resolveSectionName(candidate, chapter);
        return true;
      }
      return false;
    });
  } else {
    section = resolveSectionName(text, chapter);
  }
  if (!chapter) return null;
  return {
    chapterNo: chapter.no,
    chapterName: textbookChapterDisplayName(chapter),
    sectionName: section,
  };
}

function resolveTextbookChapterByCode(value) {
  var text = String(value || "").trim().toUpperCase();
  for (var i = 0; i < TEXTBOOK_CHAPTERS.length; i += 1) {
    var chapter = TEXTBOOK_CHAPTERS[i];
    for (var j = 0; j < chapter.prefixes.length; j += 1) {
      if (text.indexOf(chapter.prefixes[j]) === 0) return chapter;
    }
  }
  return null;
}

function resolveTextbookChapterByLabel(value) {
  var compact = _stripNumberPrefix(_compact(value));
  if (!compact) return null;
  for (var i = 0; i < TEXTBOOK_CHAPTERS.length; i += 1) {
    var chapter = TEXTBOOK_CHAPTERS[i];
    var names = [chapter.name, textbookChapterDisplayName(chapter)]
      .concat(chapter.sections)
      .concat(chapter.aliases || []);
    for (var j = 0; j < names.length; j += 1) {
      if (compact === _stripNumberPrefix(_compact(names[j]))) return chapter;
    }
  }
  return null;
}

function resolveSectionName(value, chapter) {
  var compact = _stripNumberPrefix(_compact(value));
  for (var i = 0; i < chapter.sections.length; i += 1) {
    if (compact === _stripNumberPrefix(_compact(chapter.sections[i]))) {
      return chapter.sections[i];
    }
  }
  return "";
}

function displayChapterName(value, fallback) {
  var text = String(value || "").trim();
  if (isNonTopicLabel(text)) return "";
  var resolved = resolveChapterCodeLabel(text);
  if (resolved) return resolved;
  return text || fallback || "";
}

function _compact(value) {
  return String(value || "").replace(/[\s　，,。.!！?？:：;；“”"'‘’（）()【】[\]<>《》]/g, "");
}

function _stripNumberPrefix(value) {
  return String(value || "").replace(/^(?:第?\d+章)?\d+(?:\.\d+)?/, "");
}

module.exports = {
  CHAPTER_CODE_LABELS: CHAPTER_CODE_LABELS,
  TEXTBOOK_CHAPTERS: TEXTBOOK_CHAPTERS,
  isNonTopicLabel: isNonTopicLabel,
  resolveChapterCodeLabel: resolveChapterCodeLabel,
  resolveTextbookTopic: resolveTextbookTopic,
  textbookChapterDisplayName: textbookChapterDisplayName,
  displayChapterName: displayChapterName,
};
