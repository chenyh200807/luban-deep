// knowledge-shape.js — 知识形状确定性解析器(共享组件)
//
// 2026-07-12 从 concept-cards-view-model 抽出:错因银行解药/轻练反馈/首跑判分卡
// 与考点卡共用同一套"逐字切分零改写"的图形化。单一权威边界:所有输出都是
// 输入文本的逐字子串,本模块零生成零改写,只做切分与归形。
function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _str(v) {
  return v == null ? "" : String(v);
}

/* ── 记忆面结构化（确定性解析，零改写零生成）──────────────────────
 * 单一权威边界不变：所有渲染文本都是 key_gist / quote 的逐字子串，
 * 前端只做"切分与排版"，不产生一个新字；教材原文全文永远一键可见。
 * 三种结构（有则展示，无则回落 keyGist 颗粒条）：
 * - chain  : key_gist 按 → 切成步骤石阶（≥3 段才算链）
 * - roster : quote 按 ①②… 枚举切行，行首主体（…单位/…方）提为签章
 * - numbers: gist+quote 里的 数字+单位 提为关键数瓷砖（≤4 枚）
 */
var _CHAIN_SPLIT_RE = /\s*(?:→|➝|➔|->)\s*/;
var _ENUM_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮";
var _PAREN_ENUM_RE = /[（(]\s*(\d{1,2})\s*[）)]/g;
var _BAN_RE = /(严禁|不得|禁止|不应|不准)/;
var _ACTOR_RE = /^([^，。；：、]{2,14}?)(?=应当|应|须|宜|不得|不应|禁止|负责(?!人)|组织)/;
var _NUM_RE = /(\d+(?:\.\d+)?)\s*(个月|小时|万元|天|日|人|层|次|年|h|mm|cm|km|m²|m³|m|米|%|‰|MPa|kN|℃|倍|级|元|d)/g;

function _parseChain(gist) {
  var g = _str(gist).trim();
  if (!g) return null;
  var parts = g.split(_CHAIN_SPLIT_RE).map(function (p) {
    return p.trim();
  }).filter(function (p) {
    return p.length > 0 && p.length <= 40;
  });
  return parts.length >= 3 && parts.length <= 9 ? parts : null;
}

function _parseRoster(quote) {
  var q = _str(quote);
  var idxs = [];
  var markLens = [];
  for (var i = 0; i < q.length; i++) {
    if (_ENUM_MARKS.indexOf(q[i]) >= 0) {
      idxs.push(i);
      markLens.push(1);
    }
  }
  if (idxs.length < 2) {
    // （1）(2) 式枚举(教材另一常用体例)
    idxs = [];
    markLens = [];
    _PAREN_ENUM_RE.lastIndex = 0;
    var pm;
    while ((pm = _PAREN_ENUM_RE.exec(q)) !== null) {
      idxs.push(pm.index);
      markLens.push(pm[0].length);
    }
  }
  if (idxs.length < 2) return null;
  var rows = [];
  for (var k = 0; k < idxs.length; k++) {
    var start = idxs[k] + markLens[k];
    var end = k + 1 < idxs.length ? idxs[k + 1] : q.length;
    var item = q.slice(start, end).replace(/[；;。\s]+$/, "").trim();
    if (!item) continue;
    var m = item.match(_ACTOR_RE);
    rows.push({
      mark: String(k + 1),
      actor: m ? m[1] : "",
      body: m ? item.slice(m[1].length) : item,
      banned: _BAN_RE.test(item),
    });
  }
  return rows.length >= 2 ? rows : null;
}

/** 条件→结果 规则牌: gist 恰好双段(→切一刀); 结果含禁止词=红线章。 */
function _parseRule(gist) {
  var g = _str(gist).trim();
  if (!g) return null;
  var parts = g.split(_CHAIN_SPLIT_RE).map(function (p) {
    return p.trim();
  }).filter(Boolean);
  if (parts.length !== 2) return null;
  if (parts[0].length > 60 || parts[1].length > 40) return null;
  return { cond: parts[0], result: parts[1], banned: _BAN_RE.test(parts[1]) };
}

/** 红线句捞取: 原文里含 严禁/不得/禁止 的整句(逐字, ≤2条)。 */
function _parseRedlines(quote) {
  var q = _str(quote);
  if (!q) return [];
  var out = [];
  var sentences = q.split(/(?<=[。；;])/);
  for (var i = 0; i < sentences.length && out.length < 2; i++) {
    var sent = sentences[i].trim();
    if (sent && _BAN_RE.test(sent) && sent.length <= 90) out.push(sent);
  }
  return out;
}

/** 句读要点: 无枚举时按 。；切 2-6 条短句(逐字), 长散文的最后兜底。 */
function _parseClauses(quote) {
  var q = _str(quote).trim();
  if (!q) return null;
  var parts = q.split(/[。；;]/).map(function (p) {
    return p.trim();
  }).filter(function (p) {
    return p.length >= 6 && p.length <= 70;
  });
  return parts.length >= 2 && parts.length <= 6 ? parts : null;
}

function _parseNumbers(gist, quote) {
  var seen = {};
  var out = [];
  var srcs = [_str(gist), _str(quote)];
  for (var i = 0; i < srcs.length && out.length < 4; i++) {
    var text = srcs[i];
    _NUM_RE.lastIndex = 0;
    var m;
    while ((m = _NUM_RE.exec(text)) !== null && out.length < 4) {
      var key = m[1] + m[2];
      if (seen[key]) continue;
      seen[key] = true;
      // 标签=命中处前面的逐字上下文（截到最近标点，≤10 字）
      var head = text.slice(Math.max(0, m.index - 10), m.index);
      var cut = Math.max(
        head.lastIndexOf("，"), head.lastIndexOf("。"), head.lastIndexOf("；"),
        head.lastIndexOf("："), head.lastIndexOf("、"), head.lastIndexOf(" ")
      );
      out.push({ num: m[1], unit: m[2], label: cut >= 0 ? head.slice(cut + 1) : head });
    }
  }
  return out;
}

/** 知识形状: 结构→类型徽标(正面预告"往哪个方向回忆", 翻面定视觉锚)。
 * 优先级=辨识度: 红线>规则>流程链>分工清单>关键数>要点>原文颗粒。 */
function cardShapeOf(structure) {
  var st = _safeObj(structure);
  if (st.rule && st.rule.banned) return { key: "redline", label: "一道红线", tone: "red" };
  if (st.rule) return { key: "rule", label: "一条规则", tone: "grn" };
  if (st.redlines && st.redlines.length) return { key: "redline", label: "一道红线", tone: "red" };
  if (st.chain) return { key: "chain", label: "一条流程链", tone: "grn" };
  if (st.roster) return { key: "roster", label: "一份分工清单", tone: "grn" };
  if (st.numbers && st.numbers.length) return { key: "numbers", label: "几个关键数", tone: "warn" };
  if (st.clauses) return { key: "clauses", label: "几句要点", tone: "ink" };
  return { key: "plain", label: "一句原文", tone: "ink" };
}

/** 记忆面结构（卡级派生，纯函数）。 */
function buildCardStructure(card) {
  var c = _safeObj(card);
  var chain = _parseChain(c.keyGist);
  var rule = chain ? null : _parseRule(c.keyGist);
  var roster = _parseRoster(c.quote);
  // 要点/红线只在没有枚举行时兜底(避免同一原文双重呈现)
  var clauses = roster ? null : _parseClauses(c.quote);
  var redlines = rule || roster ? [] : _parseRedlines(c.quote);
  // 兜底句里已含红线句时去重
  if (redlines.length && clauses) {
    clauses = clauses.filter(function (p) {
      return redlines.every(function (r) {
        return r.indexOf(p) < 0;
      });
    });
    if (clauses.length < 2) clauses = null;
  }
  var numbers = _parseNumbers(c.keyGist, c.quote);
  return {
    chain: chain,
    rule: rule,
    roster: roster,
    clauses: clauses,
    redlines: redlines,
    numbers: numbers,
    // 全形态都空才回落颗粒条(gist 原样)
    plain:
      !chain && !rule && !roster && !clauses &&
      redlines.length === 0 && numbers.length === 0,
  };
}


module.exports = {
  buildCardStructure: buildCardStructure,
  cardShapeOf: cardShapeOf,
  parseChain: _parseChain,
  parseRule: _parseRule,
  parseRoster: _parseRoster,
  parseRedlines: _parseRedlines,
  parseClauses: _parseClauses,
  parseNumbers: _parseNumbers,
};
