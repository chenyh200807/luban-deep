function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function text(value, fallback) {
  var result = String(value || "").trim();
  return result || fallback || "";
}

function parseTime(value) {
  var raw = text(value);
  if (!raw) return 0;
  var ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : 0;
}

function shortDate(value) {
  var ms = parseTime(value);
  if (!ms) return "最近收藏";
  var date = new Date(ms);
  return date.getMonth() + 1 + "月" + date.getDate() + "日";
}

function countBy(items, key, fallback) {
  var map = {};
  items.forEach(function (item) {
    var label = text(item[key], fallback);
    map[label] = (map[label] || 0) + 1;
  });
  return Object.keys(map)
    .map(function (label) {
      return { label: label, count: map[label] };
    })
    .sort(function (a, b) {
      return b.count - a.count;
    });
}

function buildBars(rows, maxItems, keyPrefix) {
  var list = rows.slice(0, maxItems || 4);
  var max = list.reduce(function (current, item) {
    return Math.max(current, item.count || 0);
  }, 1);
  return list.map(function (item, index) {
    return {
      key: keyPrefix + "-" + index,
      label: item.label,
      count: item.count,
      percent: Math.max(12, Math.round((item.count / max) * 100)),
      tone: index === 0 ? "hot" : index === 1 ? "focus" : "calm",
    };
  });
}

function reviewState(item, nowMs) {
  if (item.masteredAt) return "mastered";
  var due = parseTime(item.reviewDueAt);
  if (due && due <= nowMs) return "due";
  return "active";
}

function buildInsight(items, conceptBars, errorBars, dueCount) {
  if (!items.length) {
    return {
      title: "完成练习后生成错题分析",
      summary: "收藏错题后，这里会把高频知识点、错因和复习压力整理成可执行的补弱建议。",
      bullets: [
        { key: "empty-1", text: "先从学情页最近做题复盘里收藏一道错题" },
        { key: "empty-2", text: "完成复习后再标记掌握，系统会保留复习轨迹" },
      ],
    };
  }
  var topConcept = conceptBars[0] && conceptBars[0].label;
  var topError = errorBars[0] && errorBars[0].label;
  return {
    title: topConcept ? "重点先补：" + topConcept : "先处理最近错题",
    summary: topError
      ? "AI分析显示，当前错题主要集中在“" + (topConcept || "综合题目") + "”，常见问题是“" + topError + "”。"
      : "AI分析显示，当前错题已经形成可复盘集合，建议先按知识点逐条回看解析。",
    bullets: [
      {
        key: "focus",
        text: topConcept ? "先连续复盘“" + topConcept + "”相关错题" : "先处理最近收藏的错题",
      },
      {
        key: "reason",
        text: topError ? "复盘时重点解释“为什么会" + topError + "”" : "每道题都补一句自己的错因",
      },
      {
        key: "review",
        text: dueCount > 0 ? "今天有 " + dueCount + " 道错题需要复习验证" : "复习后用“标记掌握”收口，避免错题堆积",
      },
    ],
  };
}

function normalizeItem(raw, index, nowMs) {
  var item = asObject(raw);
  var masteredAt = text(item.mastered_at || item.masteredAt);
  var normalized = {
    key: text(item.event_id || item.key || item.attempt_ref, "mistake-" + index),
    attemptRef: text(item.attempt_ref || item.attemptRef),
    title: text(item.title, "错题复盘"),
    conceptLabel: text(item.concept_label || item.conceptLabel, "未归类知识点"),
    errorLabel: text(item.error_label || item.errorLabel, "待归因错因"),
    note: text(item.note),
    savedAt: text(item.saved_at || item.savedAt),
    savedLabel: shortDate(item.saved_at || item.savedAt),
    masteredAt: masteredAt,
    lastReviewedAt: text(item.last_reviewed_at || item.lastReviewedAt),
    reviewDueAt: text(item.review_due_at || item.reviewDueAt),
    etag: text(item.etag),
    isMastered: Boolean(masteredAt),
  };
  normalized.state = reviewState(normalized, nowMs);
  normalized.stateLabel =
    normalized.state === "mastered"
      ? "已掌握"
      : normalized.state === "due"
        ? "待复习"
        : "未掌握";
  normalized.stateTone =
    normalized.state === "mastered"
      ? "mastered"
      : normalized.state === "due"
        ? "due"
        : "active";
  normalized.reviewLabel = normalized.lastReviewedAt
    ? "上次复习 " + shortDate(normalized.lastReviewedAt)
    : normalized.reviewDueAt
      ? "计划复习 " + shortDate(normalized.reviewDueAt)
      : "尚未复习";
  return normalized;
}

function buildMistakeBookViewModel(payload) {
  var body = asObject(payload);
  var nowMs = Date.now();
  var items = asList(body.items)
    .map(function (item, index) {
      return normalizeItem(item, index, nowMs);
    })
    .filter(function (item) {
      return item.attemptRef || item.title;
    });
  var activeItems = items.filter(function (item) {
    return item.state !== "mastered";
  });
  var dueItems = items.filter(function (item) {
    return item.state === "due";
  });
  var masteredItems = items.filter(function (item) {
    return item.state === "mastered";
  });
  var analysisItems = activeItems.length ? activeItems : items;
  var conceptBars = buildBars(
    countBy(analysisItems, "conceptLabel", "未归类知识点"),
    4,
    "concept",
  );
  var errorBars = buildBars(
    countBy(analysisItems, "errorLabel", "待归因错因"),
    4,
    "error",
  );
  return {
    ok: body.ok !== false,
    generatedAt: text(body.generated_at || body.generatedAt),
    etag: text(body.etag),
    count: items.length,
    activeCount: activeItems.length,
    dueCount: dueItems.length,
    masteredCount: masteredItems.length,
    topConceptLabel: conceptBars[0] ? conceptBars[0].label : "暂无错题",
    topErrorLabel: errorBars[0] ? errorBars[0].label : "暂无错因",
    items: items,
    visibleItems: items.slice(0, 60),
    conceptBars: conceptBars,
    errorBars: errorBars,
    aiInsight: buildInsight(items, conceptBars, errorBars, dueItems.length),
    empty: items.length === 0,
  };
}

module.exports = {
  buildMistakeBookViewModel: buildMistakeBookViewModel,
};
