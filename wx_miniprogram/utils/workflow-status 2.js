function _stripDecorators(text) {
  return String(text || "")
    .replace(/^[^\u4e00-\u9fa5A-Za-z0-9]+/u, "")
    .replace(/\s*\[[^\]]+\]\s*$/, "")
    .replace(/\(Step\s*\d+\)/gi, "")
    .replace(/\(FAST[^\)]*\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function _extractToolName(text) {
  var match = String(text || "").match(/\[([^\]]+)\]\s*$/);
  return match ? match[1] : "";
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

var TOOL_COPY = {
  // ── 检索类 ──
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
  // ── 案例类 ──
  case_chain: {
    badge: "拆解案例",
    headline: "正在梳理案例时间线和责任关系",
    subline: "先把事件顺序理清，再判断责任主体和作答结构。",
    tone: "plan",
  },
  // ── 计算类 ──
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
  // ── 评分/出题类 ──
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
  // ── 辅助类 ──
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
  _default: {
    badge: "调用工具",
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
  plan: {
    badge: "拆解步骤",
    headline: "正在梳理解题顺序和关键判断点",
    subline: "会先搭好回答骨架，避免遗漏条件和边界。",
    tone: "plan",
  },
  retrieve: {
    badge: "检索依据",
    headline: "正在查找教材和规范依据",
    subline: "优先核对教材表述、规范条文和相关考点。",
    tone: "search",
  },
  tool: TOOL_COPY._default,
  generate: {
    badge: "深度推理",
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
  stream: {
    badge: "组织答案",
    headline: "正在整理最终回答",
    subline: "把结论、依据和记忆点压缩成更好吸收的表达。",
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

function _normalizeUnknownHeader(raw) {
  var text = String(raw || "");
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
  var source =
    typeof payload === "string" ? { message: payload } : payload || {};
  var rawText = source.message || source.text || source.data || "";
  var stage = source.stage || "";
  var toolName = source.toolName || _extractToolName(rawText);

  if (stage === "tool") {
    return TOOL_COPY[toolName] || TOOL_COPY._default;
  }
  if (stage && STAGE_COPY[stage]) {
    if (stage === "retry") {
      return {
        badge: STAGE_COPY.retry.badge,
        headline: _headline(rawText, STAGE_COPY.retry.headline),
        subline: STAGE_COPY.retry.subline,
        tone: STAGE_COPY.retry.tone,
      };
    }
    if (stage === "fallback") {
      return {
        badge: STAGE_COPY.fallback.badge,
        headline: _headline(rawText, STAGE_COPY.fallback.headline),
        subline: STAGE_COPY.fallback.subline,
        tone: STAGE_COPY.fallback.tone,
      };
    }
    return STAGE_COPY[stage];
  }
  return _normalizeUnknownHeader(rawText);
}

module.exports = {
  normalizeWorkflowStatus: normalizeWorkflowStatus,
};
