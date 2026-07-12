// 考点卡翻卡页（复习 §6.2 · 30 秒再认 · 纸墨朱竹）
// 只读投影，前端不算分不造数：
// - 站点条/卡内容 = /api/v1/luban/concept-cards[*]（signed 卡池投影逐字透传，
//   正面问法=固定模板包裹签发 pack §1 知识点短名，禁前端造句）；
// - 翻面 = 教材原文并排（quote 逐字 + point_id/页码角注）+ 助记颗粒；
// - 「记住了/再看一眼」= 纯本地牌序（concept-cards-view-model.stepDeck），
//   绝不写掌握态——掌握语义唯一权威仍是判分链路 + revalidation_queue；
// - 未签发/旗标关 = 后端 404/空投影，本页走诚实空态深链回复习页。
var api = require("../../../utils/api");
var auth = require("../../../utils/auth");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var ccvm = require("../../../utils/concept-cards-view-model");
var ebvm = require("../../../utils/errorbank-view-model");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false, // 第10版主色=宣纸亮(与 review 同口径)
    loading: true,
    errorText: "",
    library: null, // buildLibraryViewModel 输出(站点条)
    deck: null, // buildDeckViewModel 输出(当前站卡组)
    deckState: null, // initDeckState/stepDeck 纯本地牌序
    activePackId: "",
    currentCard: null, // 当前展示卡(由 deckState 派生)
    flipped: false, // 正面/翻面(纯呈现态)
    quoteOpen: false, // 教材原文全文展开(记忆面默认收拢,尊重爱看全文的用户)
    packPendingCount: 0, // 本站待还错因笔数(错因银行只读回路; 0/未开通=不显)
    pendingMap: {}, // 各站待还笔数(选站抽屉红点; 同一归属口径)
    packSheetOpen: false, // 选站抽屉
    finished: false,
  },

  onLoad: function (query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: false });
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanConceptCards());
      return;
    }
    this._requestedPackId = String((query && query.pack_id) || "")
      .trim()
      .toUpperCase();
    this._loadLibrary();
  },

  goBack: function () {
    if (typeof wx === "undefined") return;
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (wx.redirectTo) {
      wx.redirectTo({ url: route.lubanReview() });
    }
  },

  retry: function () {
    this._loadLibrary();
  },

  switchPack: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var packId = String(dataset.packId || "").trim();
    if (!packId || packId === this.data.activePackId) return;
    this._loadDeck(packId);
  },

  flipCard: function () {
    if (!this.data.currentCard || this.data.finished) return;
    this.setData({ flipped: !this.data.flipped, quoteOpen: false });
  },

  toggleQuote: function () {
    this.setData({ quoteOpen: !this.data.quoteOpen });
  },

  // 「记住了」/「再看一眼」——纯本地牌序，零上报零掌握写入
  markGotIt: function () {
    this._step("got_it");
  },

  markAgain: function () {
    this._step("again");
  },

  restartDeck: function () {
    var deck = this.data.deck;
    if (!deck) return;
    this._applyDeckState(ccvm.initDeckState(deck.cards.length));
  },

  _step: function (action) {
    if (!this.data.flipped) return; // 未翻面不许判断自己(先看原文)
    var next = ccvm.stepDeck(this.data.deckState, action);
    this._applyDeckState(next);
  },

  _applyDeckState: function (state) {
    var deck = this.data.deck;
    var idx = ccvm.currentCardIndex(state);
    this.setData({
      deckState: state,
      currentCard: idx >= 0 && deck ? deck.cards[idx] : null,
      flipped: false,
      quoteOpen: false,
      finished: idx < 0,
    });
  },

  // 错因银行只读回路: 全站待还笔数一次算清(deriveRetestPackId 同一归属口径,
  // 零第二权威; 未开通/失败=空map——纯导航增强, 不是新学情)。
  _probePackPending: function (packId) {
    var that = this;
    if (this._pendingMapLoaded) {
      this.setData({ packPendingCount: this.data.pendingMap[packId] || 0 });
      return;
    }
    Promise.all([
      api.getMistakeBook({ include_mastered: false }, { silent: true }),
      api.getLubanLessons({ silent: true }),
    ])
      .then(function (results) {
        var book = api.unwrapResponse(results[0]) || {};
        var lessons = results[1] ? api.unwrapResponse(results[1]) || {} : {};
        var items = Array.isArray(book.items) ? book.items : [];
        var map = {};
        items.forEach(function (item) {
          if (item && item.mastered_at) return;
          var pid = ebvm.deriveRetestPackId(item, lessons);
          if (pid) map[pid] = (map[pid] || 0) + 1;
        });
        that._pendingMapLoaded = true;
        that.setData({
          pendingMap: map,
          packPendingCount: map[that.data.activePackId] || 0,
        });
      })
      .catch(function () {
        that.setData({ packPendingCount: 0 });
      });
  },

  openPackSheet: function () {
    this.setData({ packSheetOpen: true });
  },

  closePackSheet: function () {
    this.setData({ packSheetOpen: false });
  },

  pickPack: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var packId = String(dataset.packId || "").trim();
    this.setData({ packSheetOpen: false });
    if (!packId || packId === this.data.activePackId) return;
    this._loadDeck(packId);
  },

  // 下一站: 按库序循环(完场/站牌一键连翻)
  nextPack: function () {
    var lib = this.data.library;
    if (!lib || !lib.packs || !lib.packs.length) return;
    var idx = -1;
    for (var i = 0; i < lib.packs.length; i++) {
      if (lib.packs[i].packId === this.data.activePackId) idx = i;
    }
    var next = lib.packs[(idx + 1) % lib.packs.length];
    if (next && next.packId !== this.data.activePackId) {
      this._loadDeck(next.packId);
    }
  },

  goErrorbank: function () {
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.lubanErrorbank() });
    }
  },

  _loadLibrary: function () {
    var that = this;
    this.setData({ loading: true, errorText: "" });
    return api
      .getLubanConceptCardLibrary()
      .then(function (resp) {
        var library = ccvm.buildLibraryViewModel(api.unwrapResponse(resp) || {});
        that.setData({ library: library });
        if (!library.available) {
          that.setData({ loading: false });
          return null;
        }
        var requested = that._requestedPackId;
        var hit = null;
        for (var i = 0; i < library.packs.length; i++) {
          if (library.packs[i].packId === requested) hit = library.packs[i];
        }
        return that._loadDeck((hit || library.packs[0]).packId);
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "考点卡加载失败，请稍后重试"),
        });
      });
  },

  _loadDeck: function (packId) {
    var that = this;
    this.setData({ loading: true, errorText: "", activePackId: packId });
    this._probePackPending(packId);
    return api
      .getLubanConceptCards(packId)
      .then(function (resp) {
        var deck = ccvm.buildDeckViewModel(api.unwrapResponse(resp) || {});
        that.setData({ deck: deck, loading: false });
        that._applyDeckState(ccvm.initDeckState(deck.cards.length));
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "考点卡加载失败，请稍后重试"),
        });
      });
  },
});
