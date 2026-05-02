function _stripDecorators(text) {
  return String(text || "")
    .replace(/^[^\u4e00-\u9fa5A-Za-z0-9]+/u, "")
    .replace(/\s*\[[^\]]+\]\s*$/, "")
    .replace(/\(Step\s*\d+\)/gi, "")
    .replace(/\(FAST[^\)]*\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function _headline(text, fallback) {
  var cleaned = _stripDecorators(text);
  return cleaned || fallback;
}

function _matchAny(text, patterns) {
  var source = String(text || "");
  for (var i = 0; i < patterns.length; i++) {
    if (patterns[i].test(source)) return true;
  }
  return false;
}

function _safeString(value) {
  return String(value == null ? "" : value).trim();
}

function _hasChinese(text) {
  return /[\u4e00-\u9fa5]/.test(String(text || ""));
}

function _looksEnglishStatus(text) {
  var source = _safeString(text);
  if (!source) return false;
  return /[A-Za-z]/.test(source) && !_hasChinese(source);
}

function _looksInternalStatus(text) {
  return /HTTP_?\d+|Internal Server Error|provider error|raw provider|DataInspectionFailed|Authentication Fails|api key|read_file|write_file|list_dir|HEARTBEAT|traceback|stack trace|workspace/i.test(
    _safeString(text),
  );
}

function _truncate(text, limit) {
  var source = _safeString(text);
  var max = Number(limit || 0) || 0;
  if (!max || source.length <= max) return source;
  return source.slice(0, max).trim() + "...";
}

function _extractToolName(text) {
  var match = String(text || "").match(/\[([^\]]+)\]\s*$/);
  return match ? match[1] : "";
}

function _dedupe(items) {
  var seen = {};
  var next = [];
  for (var i = 0; i < items.length; i++) {
    var key = _safeString(items[i]);
    if (!key || seen[key]) continue;
    seen[key] = true;
    next.push(key);
  }
  return next;
}

function _safeToolLabel(name) {
  var toolName = _safeString(name);
  return TOOL_LABELS[toolName] || "";
}

function _displayToolLabel(name) {
  return _safeToolLabel(name) || "资料整理";
}

function _pickArgPreview(args) {
  var source = args && typeof args === "object" ? args : {};
  var keys = [
    "query",
    "q",
    "question",
    "prompt",
    "topic",
    "text",
    "keyword",
    "keywords",
    "instruction",
    "expression",
    "kb_name",
  ];
  for (var i = 0; i < keys.length; i++) {
    var raw = source[keys[i]];
    if (typeof raw === "string" && raw.trim()) return _truncate(raw, 42);
  }
  return "";
}

var TOOL_LABELS = {
  rag: "知识库检索",
  web_search: "联网扩展",
  reason: "深度推演",
  memory_search: "学习记录",
  memory_get: "学习档案",
  code_execution: "计算校验",
  paper_search: "论文检索",
  brainstorm: "思路展开",
  geogebra_analysis: "图形分析",
  retrieve_knowledge: "教材规范检索",
  retrieve_case_study: "案例线索检索",
  open_ref: "原文展开",
  case_chain: "案例推演",
  basic_calculator: "计算核验",
  calculate_excavation_volume: "土方核算",
  calculate_claim_value: "索赔核算",
  calculate_deduction_point: "评分核算",
  calculate_prepayment: "预付款核算",
  grade_answer: "答案批改",
  generate_practice_question: "练习生成",
  handle_chat_support: "学习建议",
  take_note: "笔记整理",
  update_mistake_book: "错题归档",
};

var TOOL_COPY = {
  retrieve_knowledge: {
    badge: "检索依据",
    headline: "正在查找教材和规范依据",
    subline: "优先核对教材表述、规范条文和相关考点。",
    tone: "search",
  },
  retrieve_case_study: {
    badge: "拆解案例",
    headline: "正在调取相关案例和规则线索",
    subline: "会先梳理题干时间线，再抓责任边界和得分点。",
    tone: "plan",
  },
  open_ref: {
    badge: "查看原文",
    headline: "正在展开原文段落",
    subline: "调出完整条文，方便你核对上下文。",
    tone: "search",
  },
  case_chain: {
    badge: "拆解案例",
    headline: "正在梳理案例时间线和责任关系",
    subline: "先把事件顺序理清，再判断责任主体和作答结构。",
    tone: "plan",
  },
  basic_calculator: {
    badge: "计算核对",
    headline: "正在核对公式、单位和边界值",
    subline: "会顺手检查单位换算、适用条件和常见易错点。",
    tone: "calc",
  },
  calculate_excavation_volume: {
    badge: "计算挖方",
    headline: "正在计算土方量和放坡系数",
    subline: "会核对断面尺寸、放坡比和工作面宽度。",
    tone: "calc",
  },
  calculate_claim_value: {
    badge: "计算索赔",
    headline: "正在核算索赔金额和工期",
    subline: "会对照合同条款，区分可索赔与不可索赔项。",
    tone: "calc",
  },
  calculate_deduction_point: {
    badge: "计算扣分",
    headline: "正在核算扣分项和分值分布",
    subline: "会对照评分标准，逐条标出扣分依据。",
    tone: "calc",
  },
  calculate_prepayment: {
    badge: "计算预付",
    headline: "正在核算预付款和扣回进度",
    subline: "会核对起扣点、扣回比例和累计已扣金额。",
    tone: "calc",
  },
  grade_answer: {
    badge: "批改答案",
    headline: "正在对照评分标准批改",
    subline: "会先核对结论，再标出关键得分点和失分原因。",
    tone: "review",
  },
  generate_practice_question: {
    badge: "生成练习",
    headline: "正在生成更贴合你的练习",
    subline: "会优先照顾你的薄弱点和最近练习状态。",
    tone: "compose",
  },
  handle_chat_support: {
    badge: "整理建议",
    headline: "正在整理更合适的建议",
    subline: "会先判断你的需求，再给可执行的下一步。",
    tone: "compose",
  },
  take_note: {
    badge: "记笔记",
    headline: "正在帮你记录关键要点",
    subline: "会把核心结论和易混点整理成笔记。",
    tone: "compose",
  },
  update_mistake_book: {
    badge: "错题归档",
    headline: "正在更新你的错题本",
    subline: "会标注错因和对应知识点，方便下次复盘。",
    tone: "compose",
  },
  memory_search: {
    badge: "回忆记录",
    headline: "正在翻阅你的学习记录",
    subline: "看看之前做过的题和掌握情况，给出更精准的建议。",
    tone: "search",
  },
  memory_get: {
    badge: "回忆记录",
    headline: "正在调取你的学习档案",
    subline: "了解你的薄弱点和进步轨迹，帮你查漏补缺。",
    tone: "search",
  },
  rag: {
    badge: "知识召回",
    headline: "正在回忆教材、规范和你的资料依据",
    subline: "优先从知识库里抓最贴近问题的证据片段。",
    tone: "search",
  },
  web_search: {
    badge: "联网扩展",
    headline: "正在补充最新外部信息",
    subline: "用来核对时效性信息、政策变化和外部事实。",
    tone: "search",
  },
  reason: {
    badge: "深度推演",
    headline: "正在补做关键推导和交叉验证",
    subline: "会换角度复核条件冲突、边界和结论可靠性。",
    tone: "compose",
  },
  _default: {
    badge: "调用能力",
    headline: "正在补充关键证据和中间结果",
    subline: "先把必要依据补齐，再继续组织结论。",
    tone: "search",
  },
};

var STAGE_COPY = {
  analyze: {
    badge: "理解问题",
    headline: "正在识别题型和关键条件",
    subline: "先判断你真正要问的点，再选择合适的解答路径。",
    tone: "analyze",
  },
  thinking: {
    badge: "理解问题",
    headline: "正在识别题型和关键条件",
    subline: "先判断你真正要问的点，再选择合适的解答路径。",
    tone: "analyze",
  },
  plan: {
    badge: "拆解步骤",
    headline: "正在梳理解题顺序和关键判断点",
    subline: "会先搭好回答骨架，避免遗漏条件和边界。",
    tone: "plan",
  },
  acting: {
    badge: "调取能力",
    headline: "正在调用更合适的能力链路",
    subline: "后台会补证据、做核对，再把结果送回答案组织阶段。",
    tone: "plan",
  },
  observing: {
    badge: "综合判断",
    headline: "正在整合证据并排除冲突",
    subline: "把检索结果、条件边界和中间结论合并起来再判断。",
    tone: "compose",
  },
  responding: {
    badge: "组织答案",
    headline: "正在整理最终回答",
    subline: "把结论、依据和记忆点压缩成更好吸收的表达。",
    tone: "compose",
  },
  retrieve: {
    badge: "检索依据",
    headline: "正在查找教材和规范依据",
    subline: "优先核对教材表述、规范条文和相关考点。",
    tone: "search",
  },
  tool: TOOL_COPY._default,
  generate: {
    badge: "深度推演",
    headline: "正在逐步推导和验证",
    subline: "会多角度交叉验证，确保结论站得住脚。",
    tone: "compose",
  },
  agent: {
    badge: "综合判断",
    headline: "正在整合线索并形成判断",
    subline: "会顺手复核条件冲突、易混点和作答边界。",
    tone: "compose",
  },
  grade: {
    badge: "批改中",
    headline: "正在对照标准答案逐条批改",
    subline: "会标出得分点和失分原因，给出针对性建议。",
    tone: "review",
  },
  synthesize: {
    badge: "收尾整合",
    headline: "正在整合已有分析内容",
    subline: "把已完成的部分组织好，确保结论完整。",
    tone: "compose",
  },
  retry: {
    badge: "重新连接",
    headline: "刚才通道不稳定，正在重试",
    subline: "会尽量续上当前回答，不让你从头再来。",
    tone: "retry",
  },
  fallback: {
    badge: "切换模式",
    headline: "已切到更稳的处理路径",
    subline: "优先保证能继续回答，再补足必要依据。",
    tone: "retry",
  },
  complete: {
    badge: "完成",
    headline: "处理完成",
    subline: "",
    tone: "compose",
  },
  _default: {
    badge: "AI 正在处理",
    headline: "正在理解你的问题",
    subline: "先判断问题核心，再查依据并组织回答。",
    tone: "analyze",
  },
};

var EN_STATUS_COPY = [
  {
    re: /compress(?:ing|ed)?\s+conversation\s+history|conversation\s+history/i,
    headline: "正在整理历史对话脉络",
    detail: "会先压缩上下文，再把关键线索并回当前回答。",
  },
  {
    re: /analy(?:s|z)(?:e|ing)|understand(?:ing)?|identify(?:ing)?/i,
    headline: "正在识别问题核心与关键条件",
    detail: "先判断你真正要问的点，再选择更合适的回答路径。",
  },
  {
    re: /plan(?:ning)?|decompos(?:e|ing)|break(?:ing)?\s+down/i,
    headline: "正在拆解步骤和作答结构",
    detail: "会先搭好回答骨架，避免遗漏条件和边界。",
  },
  {
    re: /retriev(?:e|ing)|search(?:ing)?|knowledge|context|rag/i,
    headline: "正在调取相关知识依据",
    detail: "优先从知识库和上下文里抓取最贴近问题的证据。",
  },
  {
    re: /web\s*search|browse|current\s+info|latest\s+info/i,
    headline: "正在补充外部信息",
    detail: "会核对时效性事实、政策变化和外部资料。",
  },
  {
    re: /reason(?:ing)?|infer(?:ring)?|deduc(?:e|ing)|step[\s-]*by[\s-]*step/i,
    headline: "正在逐步推导和交叉验证",
    detail: "会多角度复核条件冲突、边界和结论可靠性。",
  },
  {
    re: /tool|function\s+call|calling/i,
    headline: "正在调用后台能力补充证据",
    detail: "先把必要依据补齐，再继续组织最终回答。",
  },
  {
    re: /synthesi(?:s|zing)|summari(?:s|z)(?:e|ing)|organi(?:s|z)(?:e|ing)|draft(?:ing)?|respond(?:ing)?|writ(?:e|ing)/i,
    headline: "正在整理最终回答",
    detail: "把结论、依据和记忆点压缩成更好吸收的表达。",
  },
  {
    re: /observ(?:e|ing)|evaluat(?:e|ing)|review(?:ing)?|merge|reconcil/i,
    headline: "正在整合线索并校验冲突",
    detail: "把检索结果、条件边界和中间结论合并起来再判断。",
  },
  {
    re: /retry|reconnect|fallback/i,
    headline: "刚才通道不稳定，正在重试",
    detail: "会尽量续上当前回答，不让你从头再来。",
  },
  {
    re: /complete(?:d)?|done|finish(?:ed|ing)?/i,
    headline: "后台处理已完成",
    detail: "必要证据和推导已经补齐，正在准备给你最终结果。",
  },
];

function _translateEnglishStatus(text) {
  var source = _safeString(text);
  if (!_looksEnglishStatus(source)) return "";
  for (var i = 0; i < EN_STATUS_COPY.length; i++) {
    if (EN_STATUS_COPY[i].re.test(source)) {
      return EN_STATUS_COPY[i];
    }
  }
  return {
    headline: STAGE_COPY._default.headline,
    detail: STAGE_COPY._default.subline,
  };
}

function _normalizeUnknownHeader(raw) {
  var text = String(raw || "");
  if (_looksInternalStatus(text)) {
    return {
      badge: "AI 正在处理",
      headline: STAGE_COPY._default.headline,
      subline: STAGE_COPY._default.subline,
      tone: "analyze",
    };
  }
  var translated = _translateEnglishStatus(text);
  if (translated) {
    return {
      badge: "AI 正在处理",
      headline: translated.headline,
      subline: translated.detail,
      tone: "analyze",
    };
  }
  if (_matchAny(text, [/教材/, /规范/, /条文/, /知识库/, /查一下/])) {
    return {
      badge: "检索依据",
      headline: "先查教材和规范依据",
      subline: "优先核对教材表述、规范条文和相关考点。",
      tone: "search",
    };
  }
  if (_matchAny(text, [/案例题/, /时间线/, /逐步拆解/, /责任/])) {
    return {
      badge: "拆解案例",
      headline: "正在梳理案例线索和作答结构",
      subline: "先拆清时间线、责任关系和关键得分点。",
      tone: "plan",
    };
  }
  if (_matchAny(text, [/算一下/, /计算/, /核算/, /公式/, /工期/])) {
    return {
      badge: "计算核对",
      headline: "正在核对公式、单位和边界值",
      subline: "会顺手检查单位换算、适用条件和常见易错点。",
      tone: "calc",
    };
  }
  if (_matchAny(text, [/批改/, /评分标准/, /对照答案/])) {
    return {
      badge: "批改答案",
      headline: "正在对照评分标准批改",
      subline: "会先核对结论，再标出关键得分点和失分原因。",
      tone: "review",
    };
  }
  if (_matchAny(text, [/练习/, /薄弱点/, /出一道/])) {
    return {
      badge: "生成练习",
      headline: "正在生成更贴合你的练习",
      subline: "会优先照顾你的薄弱点和最近练习状态。",
      tone: "compose",
    };
  }
  return {
    badge: "AI 正在处理",
    headline: _headline(text, STAGE_COPY._default.headline),
    subline: STAGE_COPY._default.subline,
    tone: "analyze",
  };
}

function normalizeWorkflowStatus(payload) {
  var source = typeof payload === "string" ? { message: payload } : payload || {};
  var statusText = source.message || source.text || source.data || source.content || "";
  var stage = _safeString(source.stage);
  var metadata = source.metadata || {};
  var toolName =
    source.toolName || metadata.tool_name || metadata.tool || _extractToolName(statusText);

  if (source.data === "slow_response") {
    return {
      badge: "稍等片刻",
      headline: "内容较多，正在深度处理",
      subline: "复杂问题需要更多推理时间，马上就好。",
      tone: "retry",
    };
  }
  if (source.eventType === "tool_call") {
    return TOOL_COPY[toolName] || TOOL_COPY._default;
  }
  if (source.eventType === "tool_result") {
    var copy = TOOL_COPY[toolName] || TOOL_COPY._default;
    return {
      badge: copy.badge,
      headline: _displayToolLabel(toolName) + " 已完成",
      subline: "结果已经拿到，正在吸收进最终回答。",
      tone: copy.tone,
    };
  }
  if (stage === "tool") {
    return TOOL_COPY[toolName] || TOOL_COPY._default;
  }
  if (stage && STAGE_COPY[stage]) {
    if (stage === "retry" || stage === "fallback") {
      return {
        badge: STAGE_COPY[stage].badge,
        headline: _headline(statusText, STAGE_COPY[stage].headline),
        subline: STAGE_COPY[stage].subline,
        tone: STAGE_COPY[stage].tone,
      };
    }
    return STAGE_COPY[stage];
  }
  return _normalizeUnknownHeader(statusText);
}

function buildWorkflowEntry(payload) {
  var source = typeof payload === "string" ? { data: payload } : payload || {};
  var metadata = source.metadata || {};
  var args = metadata.args && typeof metadata.args === "object" ? metadata.args : {};
  var eventType = _safeString(source.eventType || source.type || "status");
  var seq = Number(source.seq || 0);
  var statusText = _safeString(source.content || source.message || source.text || source.data);
  var toolName =
    source.toolName ||
    metadata.tool_name ||
    metadata.tool ||
    _extractToolName(statusText);
  var normalized = normalizeWorkflowStatus(source);
  var preview = _pickArgPreview(args);
  var toolLabel = toolName ? _safeToolLabel(toolName) : "";
  var displayToolLabel = toolName ? _displayToolLabel(toolName) : "";
  var title = normalized.headline;
  var detail = normalized.subline;

  if (source.data === "slow_response") {
    detail = "复杂问题需要更多推理时间，马上就好。";
  } else if (eventType === "tool_call") {
    title = "正在进行" + (displayToolLabel || "资料整理");
    detail = preview
      ? "本轮关注点：" + preview
      : "正在补这一环所需的证据、推导或外部信息。";
  } else if (eventType === "tool_result") {
    title = (displayToolLabel || "资料整理") + " 已完成";
    detail = "这一环的结果已经进入答案整理阶段。";
  }

  return {
    id: "wf_" + (seq || Date.now()) + "_" + eventType + "_" + (toolLabel || source.stage || "step"),
    seq: seq,
    eventType: eventType,
    badge: normalized.badge,
    title: title,
    detail: detail,
    tone: normalized.tone,
    toolLabel: toolLabel,
  };
}

function appendWorkflowEntry(existingEntries, payload) {
  var entries = Array.isArray(existingEntries) ? existingEntries.slice() : [];
  var nextEntry = buildWorkflowEntry(payload);
  var nextSeq = Number(nextEntry.seq || 0);

  if (nextSeq) {
    for (var i = 0; i < entries.length; i++) {
      if (Number(entries[i].seq || 0) === nextSeq) {
        entries[i] = nextEntry;
        return entries;
      }
    }
  }

  if (
    entries.length &&
    !nextSeq &&
    entries[entries.length - 1].title === nextEntry.title &&
    entries[entries.length - 1].detail === nextEntry.detail
  ) {
    entries[entries.length - 1] = nextEntry;
    return entries;
  }

  entries.push(nextEntry);
  return entries;
}

function summarizeWorkflow(entries, active) {
  var list = Array.isArray(entries) ? entries : [];
  var latest = list.length ? list[list.length - 1] : null;
  var toolLabels = _dedupe(
    list.map(function (item) {
      return item.toolLabel;
    }),
  );
  var count = list.length;

  if (!latest) {
    return {
      badge: STAGE_COPY._default.badge,
      headline: STAGE_COPY._default.headline,
      subline: STAGE_COPY._default.subline,
      tone: STAGE_COPY._default.tone,
      meta: "",
      countText: "",
      toggleText: "查看处理摘要",
      active: !!active,
    };
  }

  var summaryHeadline = active ? latest.title : "本轮处理已完成";
  var summarySubline = active
    ? latest.detail
    : toolLabels.length
      ? "已完成证据检索、推导校验和答案组织，可查看简要摘要。"
      : "处理已经完成，可查看简要摘要。";
  return {
    badge: active ? latest.badge : "处理摘要",
    headline: summaryHeadline,
    subline: summarySubline,
    tone: active ? latest.tone : latest.tone || "compose",
    meta: "",
    countText: "",
    toggleText: "查看处理摘要",
    active: !!active,
  };
}

module.exports = {
  appendWorkflowEntry: appendWorkflowEntry,
  buildWorkflowEntry: buildWorkflowEntry,
  normalizeWorkflowStatus: normalizeWorkflowStatus,
  summarizeWorkflow: summarizeWorkflow,
};
