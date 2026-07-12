// concept-cards-view-model.js — 考点卡库/翻卡页纯函数视图模型
//
// 单一权威边界(双轮 §6.2 / §8):
// - 卡内容 = 后端 signed 卡池投影逐字透传, 前端零改写零生成——正面问法也只是
//   固定模板包裹 pack §1 的知识点短名(模板确定性渲染, 禁 LLM 组织文本);
// - 教材原文(quote)与 point_id/页码角注原样展示, 不截断不润色;
// - 「记住了/再看一眼」= 纯本地牌序操作(immutable), 绝不写掌握态——
//   掌握语义唯一权威仍是判分链路 + revalidation_queue;
// - 文案铁律: 帮你变强基调, 禁审视揭短词(测试钉死禁词表)。

// 正面问法固定模板(确定性渲染; 知识点短名来自签发 pack §1, 非前端造句)
var FRONT_PROMPT_SUFFIX = "教材原文怎么说？先自己回忆 30 秒";
// 翻面后的两枚按钮(呈现态文案, 不承诺掌握)
var GOT_IT_LABEL = "记住了";
var AGAIN_LABEL = "再看一眼";
var DONE_TITLE = "这一轮过完了";
var DONE_DESC = "教材原句多见一次就更稳一分，随时再来一轮";

function _safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _safeArr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v);
}

/** 库总览: GET /api/v1/luban/concept-cards 响应 → 复习页/翻卡页站点条。
 * 后端旗标关(enabled=false)或零签发池 → available=false(复习页保持占位)。 */
function buildLibraryViewModel(body) {
  var b = _safeObj(body);
  var packs = _safeArr(b.packs)
    .map(function (p) {
      var o = _safeObj(p);
      return {
        packId: _str(o.pack_id).toUpperCase(),
        title: _str(o.title),
        cardCount: Number(o.card_count) > 0 ? Math.round(Number(o.card_count)) : 0,
      };
    })
    .filter(function (p) {
      return p.packId && p.cardCount > 0;
    });
  var total = Number(b.total) > 0 ? Math.round(Number(b.total)) : 0;
  return {
    available: total > 0 && packs.length > 0,
    total: total,
    packs: packs,
  };
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
var _ACTOR_RE = /^([^，。；：、]{2,14}?)(?=应当|应|须|宜|不得|不应|禁止|负责|组织)/;
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

/** 单站卡组: GET /api/v1/luban/concept-cards/{pack_id} 响应 → 翻卡页数据。
 * 卡字段逐字透传; 无 quote/front 的脏卡就地剔除(fail-closed, 不补文案)。 */
function buildDeckViewModel(body) {
  var b = _safeObj(body);
  var cards = _safeArr(b.cards)
    .map(function (c) {
      var o = _safeObj(c);
      var ref = _safeObj(o.source_ref);
      var page = Number(ref.page_num);
      var base = {
        cardId: _str(o.card_id),
        front: _str(o.front),
        prompt: FRONT_PROMPT_SUFFIX,
        keyGist: _str(o.key_gist),
        quote: _str(o.quote),
        pointId: _str(o.point_id),
        // 角注: point_id 溯源 + 教材页码(有则并示)
        sourceNote:
          _str(o.point_id) +
          (Number.isFinite(page) && page > 0 ? " · 教材 P" + page : ""),
      };
      base.structure = buildCardStructure(base);
      base.shape = cardShapeOf(base.structure);
      return base;
    })
    .filter(function (c) {
      return !!(c.cardId && c.front && c.quote);
    });
  return {
    packId: _str(b.pack_id).toUpperCase(),
    title: _str(b.title),
    cards: cards,
    gotItLabel: GOT_IT_LABEL,
    againLabel: AGAIN_LABEL,
    doneTitle: DONE_TITLE,
    doneDesc: DONE_DESC,
  };
}

/** 牌序初态: 顺序过一遍(0..n-1)。 */
function initDeckState(cardCount) {
  var n = Number(cardCount) > 0 ? Math.round(Number(cardCount)) : 0;
  var order = [];
  for (var i = 0; i < n; i++) order.push(i);
  return { order: order, pos: 0, gotCount: 0, againCount: 0 };
}

/** 翻牌步进(纯函数, 返回新 state, 不改入参——绝不上报, 掌握态零写入):
 * - "got_it"  记住了 → 前进一张;
 * - "again"   再看一眼 → 当前牌挪到队尾, 稍后重来(pos 不动=直接看下一张)。 */
function stepDeck(state, action) {
  var s = _safeObj(state);
  var order = _safeArr(s.order).slice();
  var pos = Number(s.pos) >= 0 ? Math.round(Number(s.pos)) : 0;
  if (pos >= order.length) return state; // 已完场, 不动
  if (action === "again") {
    var current = order[pos];
    order.splice(pos, 1);
    order.push(current);
    return {
      order: order,
      pos: pos,
      gotCount: Number(s.gotCount) || 0,
      againCount: (Number(s.againCount) || 0) + 1,
    };
  }
  return {
    order: order,
    pos: pos + 1,
    gotCount: (Number(s.gotCount) || 0) + 1,
    againCount: Number(s.againCount) || 0,
  };
}

/** 当前牌下标(完场返回 -1)。 */
function currentCardIndex(state) {
  var s = _safeObj(state);
  var order = _safeArr(s.order);
  var pos = Number(s.pos) >= 0 ? Math.round(Number(s.pos)) : 0;
  return pos < order.length ? order[pos] : -1;
}

module.exports = {
  buildLibraryViewModel: buildLibraryViewModel,
  buildDeckViewModel: buildDeckViewModel,
  buildCardStructure: buildCardStructure,
  cardShapeOf: cardShapeOf,
  initDeckState: initDeckState,
  stepDeck: stepDeck,
  currentCardIndex: currentCardIndex,
  FRONT_PROMPT_SUFFIX: FRONT_PROMPT_SUFFIX,
};
