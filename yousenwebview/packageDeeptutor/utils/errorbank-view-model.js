// errorbank-view-model.js — 错因银行(复习二期二级页)纯函数视图模型
//
// 数据边界(零第二学情权威):
// - 错因记账真值 = 云端错题集 read model(/api/v1/mobile/mistake-book)。
//   error_label 由判分内核写入(diagnosis 或原始错因码), 本 vm 只做呈现层
//   人话化(镜像 deeptutor/contracts/error_codes.py 的 ERROR_CODE_REGISTRY
//   标签), 禁第二套错因归因。
// - 已标记 = 只呈现服务端 mastered_at(用户手动标记)。复测完成只推进
//   canonical review cadence, 不在本地把整包结果摊到某一笔错题上。
// - R8 解药 fail-closed: runtime 尚无解药 bank 供给(pack MD 不进 runtime)。
//   detail vm 留 (pack_id, error_code) 数据位, 供给 bank 上线后把响应喂进
//   buildErrorbankDetail 的 antidote 参数即亮; 无供给时卡片降级为
//   「解药整理中 · 先回到当时的解析」(深链既有解析, 不造讲解内容)。
//   ── 解药 bank 接口位形状(给后续内容管线) ──
//   请求键: { pack_id: "F16", error_code: "E03" }
//   响应形状: { mental_model: "<人话心智模型正文>",
//               textbook_ref: "<教材出处标签>" }
// - 换皮复测 CTA fail-closed: 只有 packId 可诚实归属且 canonical review-due
//   给出可用 probe 才渲染; 否则降级为回解析。
// - 文案铁律: 只用「帮你变强」基调, 禁审视揭短词(测试钉死禁词表)。

function _obj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _arr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v).trim();
}
function _time(v) {
  var ms = Date.parse(_str(v));
  return Number.isFinite(ms) ? ms : 0;
}
function _shortDate(v) {
  var ms = _time(v);
  if (!ms) return "";
  var d = new Date(ms);
  var mm = d.getMonth() + 1;
  var dd = d.getDate();
  return (mm < 10 ? "0" + mm : mm) + "-" + (dd < 10 ? "0" + dd : dd);
}

// ── 错因码 → 人话标签(呈现层镜像, 权威=deeptutor/contracts/error_codes.py) ──
// 报告页对 M 系列已有同源镜像(learning-report-view-model.cleanLearningText);
// 此处补齐 E 系列 + fallback, 只做展示替换, 不做第二套归因。
var ERROR_CODE_LABELS = {
  E01: "知识点缺失",
  E02: "采分点遗漏",
  E03: "关键词缺失",
  E04: "口号化表达",
  E05: "审题错误",
  E06: "程序顺序错误",
  E07: "概念混淆",
  E08: "背景信息提取失败",
  E09: "计算错误",
  E10: "规范适用错误",
  E11: "迁移失败",
  E12: "表达冗余",
  M01: "知识点不熟",
  M02: "关键词误读",
  M03: "概念混淆",
  M04: "选项陷阱",
  M05: "审题方向错误",
  M06: "多选漏选",
  M07: "多选错选",
  M08: "规范数字混淆",
  M09: "题干条件提取不完整",
  M10: "用常识替代规范判断",
  unknown_error: "未归因错误",
};

// ── 错因码 → 暖处方一句(呈现层文案, 与 ERROR_CODE_LABELS 同源同边界) ──
// 语气纪律: 只"帮你变强", 禁审视词; 缺码/未收录走 default(即原全站通用句)。
var WARM_LINES = {
  E02: "点都在你脑子里——差的是落笔时把每个采分点各给一句。这笔分能拿回来。",
  E03: "意思你懂了,差的只是阅卷认的那几个词。把给分词背上,这笔分就是你的。",
  E04: "方向对了,再把口号落成'条款+做法'的具体话,分就实了。",
  E05: "不是不会——是题眼看快了。下次先圈问法再动笔,这笔分能拿回来。",
  E06: "步骤你都有,差的是顺序。把流程按'先后'串一遍,这笔分能拿回来。",
  E07: "两个概念只差一层窗户纸。对照解药里的分界句,捅破就稳了。",
  E09: "思路对,数错了——列式再算一遍,过程分一分不丢。",
  E10: "你套的规范没错在懂不懂,错在'哪一本管这事'。记住适用边界,分就回来了。",
  E11: "老场景你会,新皮没认出来——多看一个换皮例子,下次一眼穿。",
  default: "不是不会做——差的只是把给分词落到纸上。这笔分能拿回来。",
};

// 按错因码取暖处方(呈现层, 不做第二套归因)
function warmLineFor(errorCode) {
  return WARM_LINES[_str(errorCode)] || WARM_LINES.default;
}

/**
 * error_label 人话化。判分内核写入的 error_label 可能是:
 * ① 人话 diagnosis(直接用) ② 原始错因码如 "E03"(镜像人话) ③ 空(兜底)。
 * @returns {{label: string, code: string}} code 仅在源头是注册表错因码时非空
 */
// 人话标签 → 注册码 逆映射(同一注册表的双向镜像; E 系先注册,与解药池键位一致)
var LABEL_TO_CODE = (function () {
  var map = {};
  Object.keys(ERROR_CODE_LABELS).forEach(function (code) {
    var label = ERROR_CODE_LABELS[code];
    if (!map[label]) map[label] = code;
  });
  return map;
})();

function humanizeErrorLabel(raw) {
  var text = _str(raw);
  if (!text) return { label: "待归因错因", code: "" };
  // "错因 E03" / "E03" 两种原始形态
  var match = text.match(/^(?:错因\s*)?([EM]\d{2}|unknown_error)$/);
  if (match && ERROR_CODE_LABELS[match[1]]) {
    return { label: ERROR_CODE_LABELS[match[1]], code: match[1] };
  }
  if (ERROR_CODE_LABELS[text]) {
    return { label: ERROR_CODE_LABELS[text], code: text };
  }
  // 判分内核写的人话 diagnosis: 整句=注册标签, 或 "标签：细节" 前缀 → 逆映射回码
  // (镜像同一注册表, 不产生第二套归因; 解锁解药/复测的 (pack, code) 查询键)
  if (LABEL_TO_CODE[text]) {
    return { label: text, code: LABEL_TO_CODE[text] };
  }
  var head = text.split(/[：:，,——]/)[0].trim();
  if (head && LABEL_TO_CODE[head]) {
    return { label: text, code: LABEL_TO_CODE[head] };
  }
  return { label: text, code: "" };
}

/**
 * 诚实归属 pack: 只有错题能明确对上鲁班站(lessons read model)时才给 packId。
 * 匹配口径(fail-closed, 对不上=空串, 不猜):
 * ① concept_label 与站 title 全等; ② question_id / tags 含站 pack_id 词元。
 */
function deriveRetestPackId(item, lessons) {
  var o = _obj(item);
  var rows = _arr(_obj(lessons).lessons);
  var concept = _str(o.concept_label || o.conceptLabel);
  var haystack = (
    _str(o.question_id || o.questionId) +
    " " +
    _arr(o.tags).join(" ")
  ).toUpperCase();
  for (var i = 0; i < rows.length; i++) {
    var row = _obj(rows[i]);
    var packId = _str(row.pack_id).toUpperCase();
    if (!packId) continue;
    if (concept && concept === _str(row.title)) return packId;
    if (haystack.indexOf(packId) >= 0) return packId;
  }
  return "";
}

var DAY_MS = 24 * 60 * 60 * 1000;

function _dueChip(dueAtMs, nowMs) {
  if (!dueAtMs) return null;
  var endOfToday = new Date(nowMs);
  endOfToday.setHours(23, 59, 59, 999);
  if (dueAtMs <= endOfToday.getTime()) {
    return { text: "今天到期", tone: "och" };
  }
  if (dueAtMs <= endOfToday.getTime() + DAY_MS) {
    return { text: "明天到期", tone: "ink" };
  }
  return null;
}

function _normalizeEntry(raw, index, lessons, nowMs) {
  var o = _obj(raw);
  var humanized = humanizeErrorLabel(o.error_label || o.errorLabel);
  var dueAtMs = _time(o.review_due_at || o.reviewDueAt);
  return {
    key: _str(o.event_id || o.key || o.attempt_ref) || "entry-" + index,
    attemptRef: _str(o.attempt_ref || o.attemptRef),
    title: _str(o.title) || "一笔错因",
    conceptLabel: _str(o.concept_label || o.conceptLabel) || "未归类知识点",
    errorLabel: humanized.label,
    errorCode: humanized.code,
    note: _str(o.note),
    savedLabel: _shortDate(o.saved_at || o.savedAt),
    masteredAt: _str(o.mastered_at || o.masteredAt),
    masteredLabel: _shortDate(o.mastered_at || o.masteredAt),
    dueAtMs: dueAtMs,
    dueChip: _dueChip(dueAtMs, nowMs),
    packId: deriveRetestPackId(o, lessons),
    repeatCount: 1, // 同点(考点×错因)累计, 下方聚合后回填
  };
}

/**
 * 组装错因银行列表页 data。
 * @param {object} args
 *   mistakeBook  = GET /api/v1/mobile/mistake-book 响应 body(include_mastered=true)
 *   lessons      = GET /api/v1/luban/lessons 响应 body(pack 归属唯一对照源)
 *   nowMs        = 注入时钟(测试用), 缺省 Date.now()
 */
function buildErrorbankViewModel(args) {
  var a = _obj(args);
  var nowMs = Number(a.nowMs) > 0 ? Number(a.nowMs) : Date.now();
  var items = _arr(_obj(a.mistakeBook).items).map(function (raw, index) {
    return _normalizeEntry(raw, index, a.lessons, nowMs);
  });

  // 同点已错次数 = 相同(考点 × 错因)的记账笔数(纯呈现聚合, 非归因)
  var repeat = {};
  items.forEach(function (entry) {
    var k = entry.conceptLabel + "::" + entry.errorLabel;
    repeat[k] = (repeat[k] || 0) + 1;
  });
  items.forEach(function (entry) {
    entry.repeatCount = repeat[entry.conceptLabel + "::" + entry.errorLabel] || 1;
    entry.repeatLine =
      entry.repeatCount >= 2
        ? "同一个点已错 " + entry.repeatCount + " 次 · 已帮你重点盯着"
        : "";
  });

  var pending = [];
  var settled = [];
  items.forEach(function (entry) {
    if (entry.masteredAt) {
      settled.push(
        Object.assign({}, entry, {
          // 服务端 mastered_at = 用户手动标记的呈现层旗标, 不冒充复测或掌握推断。
          settledAtMs: _time(entry.masteredAt),
          settledLine: (entry.masteredLabel ? entry.masteredLabel + " " : "") + "服务端已标记",
          settledVia: "manual",
        }),
      );
      return;
    }
    pending.push(entry);
  });

  // 排序: 到期在前(早到期优先), 其余按记账新→旧。
  // (设计稿「到期×分值」的分值维度 runtime 记账无供给, 诚实降级为到期先后)
  pending.sort(function (x, y) {
    var dx = x.dueAtMs || Infinity;
    var dy = y.dueAtMs || Infinity;
    if (dx !== dy) return dx - dy;
    return 0;
  });
  settled.sort(function (x, y) {
    return (y.settledAtMs || 0) - (x.settledAtMs || 0);
  });

  var totalCount = pending.length + settled.length;
  return {
    pendingEntries: pending,
    settledEntries: settled,
    pendingCount: pending.length,
    settledCount: settled.length,
    // 账本环 = 服务端已标记占比(竹青), 全空时 0
    settledPercent: totalCount ? Math.round((settled.length / totalCount) * 100) : 0,
    heroTitle: pending.length
      ? "待处理 " + pending.length + " 笔 · 已标记 " + settled.length + " 笔"
      : "当前没有待处理错因",
    // 空态(待处理 0) = D1 铁律深链, 服务端已标记记录仍保留。
    allClear: pending.length === 0,
    isEmpty: totalCount === 0,
  };
}

// ── 详情态(四段瀑布) ──────────────────────────────────────
var ANTIDOTE_PENDING_TITLE = "解药整理中";
var ANTIDOTE_PENDING_DESC =
  "这个误区的心智模型正在整理——先回到当时的解析，给分词都在里面。";

/**
 * 组装一笔错因的详情 data。
 * @param {object} entry buildErrorbankViewModel 输出的条目
 * @param {object} opts
 *   antidote    = 解药 bank 响应({mental_model, textbook_ref}), 无供给传 null
 *   retestProbe = {available: boolean, probeId: string} review-due 结论
 *   position    = {index, total} 「第 x / n 笔」
 */
function buildErrorbankDetail(entry, opts) {
  var e = _obj(entry);
  var o = _obj(opts);
  var antidote = o.antidote && typeof o.antidote === "object" ? o.antidote : null;
  var probe = _obj(o.retestProbe);
  var position = _obj(o.position);
  var retestReady = !!e.packId && probe.available === true && !!_str(probe.probeId);
  return {
    key: _str(e.key),
    attemptRef: _str(e.attemptRef),
    positionLabel:
      Number(position.index) > 0 && Number(position.total) > 0
        ? "错因银行 · 第 " + position.index + " / " + position.total + " 笔"
        : "错因银行",
    // ① 错因头卡: 错因码只呈现不二次归因
    errorLabel: _str(e.errorLabel) || "待归因错因",
    // 源头是注册表错因码时才亮码 chip(「判分内核直出」), 人话 diagnosis 不硬造码
    errorCodeChip: e.errorCode ? "错因码 " + e.errorCode + " · 判分内核直出" : "",
    title: _str(e.title) || "一笔错因",
    chips: [
      e.savedLabel ? { key: "saved", text: "记账 " + e.savedLabel, tone: "ink" } : null,
      e.repeatCount >= 2
        ? { key: "repeat", text: "同点已错 " + e.repeatCount + " 次", tone: "ink" }
        : null,
      e.dueChip ? { key: "due", text: e.dueChip.text, tone: e.dueChip.tone } : null,
    ].filter(Boolean),
    // 暖处方按错因码分文案(WARM_LINES 呈现层镜像); 缺码走 default 通用句
    warmLine: warmLineFor(e.errorCode),
    // ② 原题背景切片(记账现场), 完整作答对照走「回到当时的解析」深链
    slice: {
      quote: _str(e.title),
      noteKicker: _str(e.note) ? "当时的解析摘要" : "",
      note: _str(e.note),
    },
    // 早期记账没带错因码(判分内核后来才开始写码)——诚实说明,不留悬念
    thinNote: !e.errorCode
      ? "这笔是早期记账，没带错因码——新的判分会自动归因，这页会随之长厚。"
      : "",
    // ③ R8 解药: 有供给=签发全字段(现象→旧地图→新地图, 同码多条); 无=fail-closed
    antidote: antidote
      ? {
          state: "ready",
          // 向后兼容旧形状({mental_model,textbook_ref})
          items: (_arr(antidote.items).length
            ? _arr(antidote.items)
            : [antidote]
          )
            .map(function (r) {
              var o = _obj(r);
              return {
                text: _str(o.mental_model),
                phenomenon: _str(o.phenomenon),
                wrongModel: _str(o.wrong_model || o.wrongModel),
                textbookRef: _str(o.textbook_ref || o.textbookRef),
              };
            })
            .filter(function (r) {
              return !!r.text;
            })
            .slice(0, 2),
          text: _str(antidote.mental_model),
          textbookRef: _str(antidote.textbook_ref),
        }
      : {
          state: "pending",
          title: ANTIDOTE_PENDING_TITLE,
          desc: ANTIDOTE_PENDING_DESC,
        },
    // 解药 bank 查询键(数据位): 供给上线后按此形状取
    antidoteQuery: { pack_id: _str(e.packId), error_code: _str(e.errorCode) },
    // ④ 复习动线: canonical 到期 probe 齐全才允许进入换皮复测(fail-closed)
    retest: {
      ready: retestReady,
      packId: _str(e.packId),
      probeId: _str(probe.probeId),
      ctaText: retestReady ? "换个皮再试一次 · 约 3 分钟" : "",
      fallbackText: "回到当时的解析",
    },
  };
}

module.exports = {
  humanizeErrorLabel: humanizeErrorLabel,
  deriveRetestPackId: deriveRetestPackId,
  buildErrorbankViewModel: buildErrorbankViewModel,
  buildErrorbankDetail: buildErrorbankDetail,
};
