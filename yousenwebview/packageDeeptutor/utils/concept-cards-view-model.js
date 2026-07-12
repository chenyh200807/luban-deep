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
        tier: _str(o.tier), // "standard"=全考纲标准梯队(明示分层)
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


var knowledgeShape = require("./knowledge-shape");
var buildCardStructure = knowledgeShape.buildCardStructure;
var cardShapeOf = knowledgeShape.cardShapeOf;

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
        // v32 采分点富化: [{statement, required_terms[]}] 签发透传(无=空数组)
        scoringTerms: _safeArr(o.scoring_terms)
          .map(function (r) {
            var t = _safeObj(r);
            return {
              statement: _str(t.statement),
              terms: _safeArr(t.required_terms).map(_str).filter(Boolean),
            };
          })
          .filter(function (r) {
            return r.terms.length > 0;
          }),
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
