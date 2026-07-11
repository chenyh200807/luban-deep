// 错因银行(复习二期二级页 · 列表/详情/空态)
// 设计权威: review-phase2-design/errorbank-detail.html(第10轮宣纸补稿)
// 数据边界(零第二学情权威, 详见 errorbank-view-model.js 头注):
// - 记账真值 = 云端错题集 read model(只读); pack 归属对照 lessons read model;
// - R8 解药 runtime 无供给 → fail-closed 降级卡(深链既有解析), 数据位已留;
// - 销账 = 呈现层: 本地换皮复测通过记录 + 服务端 mastered 旗标, 绝不写掌握态;
// - 变体池探测 = 详情页单站一次 getLubanRetestItems(非列表 N+1), 有货才亮换皮 CTA。
var api = require("../../../utils/api");
var auth = require("../../../utils/auth");
var helpers = require("../../../utils/helpers");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var errorbankViewModel = require("../../../utils/errorbank-view-model");

var SETTLED_STORE_KEY = "luban_errorbank_settled_v1";
var RETEST_RESULT_PREFIX = "luban_retest_last:";
var SETTLED_PREVIEW_COUNT = 2;

function _readStorage(key) {
  if (typeof wx === "undefined" || !wx.getStorageSync) return null;
  try {
    return wx.getStorageSync(key) || null;
  } catch (_err) {
    return null;
  }
}

function _writeStorage(key, value) {
  if (typeof wx === "undefined" || !wx.setStorageSync) return;
  try {
    wx.setStorageSync(key, value);
  } catch (_err) {}
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    loading: true,
    errorText: "",
    mode: "list", // list | detail
    bookDisabled: false, // 记账功能未开通(mistake-book 404)——诚实空态, 非错误态
    vm: null,
    detail: null,
    settledExpanded: false,
    settledPreview: [],
    // 销账竹青章仪式: 复测通过返回本页时短暂高亮
    justSettledKey: "",
  },

  onLoad: function () {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({
      statusBarHeight: sbh,
      navHeight: sbh + 48,
      isDark: helpers.isDark(),
    });
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanErrorbank());
      return;
    }
    this._pendingRetest = null; // {packId, itemKey, leftAt}
    this._probeCache = {}; // packId -> {available: bool}
    this._antidoteCache = {}; // "packId::errorCode" -> {mental_model, textbook_ref} | null
    this._loadAll();
  },

  onShow: function () {
    this._settleFromRetestResult();
  },

  onPullDownRefresh: function () {
    this._loadAll().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) {
        wx.stopPullDownRefresh();
      }
    });
  },

  retry: function () {
    this._loadAll();
  },

  goBack: function () {
    if (this.data.mode === "detail") {
      this.setData({ mode: "list", detail: null });
      return;
    }
    if (typeof wx === "undefined") return;
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (wx.redirectTo) {
      wx.redirectTo({
        url: route.lubanReview(),
        fail: function () {
          if (wx.reLaunch) wx.reLaunch({ url: route.lubanReview() });
        },
      });
    }
  },

  // 空态深链(D1 铁律): 待还清零 → 去学习页点亮下一站
  goLearn: function () {
    if (typeof wx === "undefined" || !wx.redirectTo) return;
    wx.redirectTo({
      url: route.learn(),
      fail: function () {
        if (wx.reLaunch) wx.reLaunch({ url: route.learn() });
      },
    });
  },

  toggleSettled: function () {
    this.setData({ settledExpanded: !this.data.settledExpanded });
    this._syncSettledPreview();
  },

  openDetail: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var vm = this.data.vm;
    var entries = (vm && vm.pendingEntries) || [];
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].key === dataset.key) {
        this._openDetailAt(entries[i], i + 1, entries.length);
        return;
      }
    }
  },

  // ② 原题背景切片 →「回到当时的解析」: 复用既有 attempt-detail 深链
  // (与 mistake-book 页同一 cacheKey 约定, 单一解析入口)
  openAttemptDetail: function () {
    var detail = this.data.detail;
    if (!detail || !detail.attemptRef) return;
    var cacheKey =
      "mistake_book_attempt:" +
      String(detail.key || Date.now()).replace(/[^a-zA-Z0-9:_-]/g, "_");
    _writeStorage(cacheKey, {
      card: {
        key: detail.key,
        attemptRef: detail.attemptRef,
        title: detail.title,
        questionText: detail.title,
        concept: "",
        diagnosis: detail.errorLabel,
        diagnosisDetail: detail.slice ? detail.slice.note : "",
        answerLine: "",
        resultLabel: "错题",
        tone: "wrong",
      },
      savedAt: Date.now(),
    });
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/attempt-detail/attempt-detail?cacheKey=" +
          encodeURIComponent(cacheKey) +
          "&attemptRef=" +
          encodeURIComponent(detail.attemptRef),
      });
    }
  },

  // ④ 销账动线 CTA: 换个皮再试一次 → 既有变体复测链路(retest 页带 pack_id)
  openRetest: function () {
    var detail = this.data.detail;
    if (!detail || !detail.retest || !detail.retest.ready) return;
    var packId = detail.retest.packId;
    if (!packId) return;
    this._pendingRetest = {
      packId: packId,
      itemKey: detail.key,
      leftAt: Date.now(),
    };
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          encodeURIComponent(packId),
      });
    }
  },

  // 解药查询键: 只有 packId 可诚实归属 ∧ errorCode 是注册表错因码才成立
  // (deriveRetestPackId / humanizeErrorLabel 对不上=空串)。任一空 = 不查, 保持
  // 「解药整理中」占位, 绝不拿半个键瞎猜。
  _antidoteKey: function (entry) {
    var e = entry || {};
    if (!e.packId || !e.errorCode) return "";
    return e.packId + "::" + e.errorCode;
  },

  _openDetailAt: function (entry, index, total) {
    var probe = this._probeCache[entry.packId] || null;
    var antidoteKey = this._antidoteKey(entry);
    // 命中缓存(含已探为 null 的负缓存)即用; 未探过 = null → vm 走 pending 占位。
    var antidote =
      antidoteKey && Object.prototype.hasOwnProperty.call(this._antidoteCache, antidoteKey)
        ? this._antidoteCache[antidoteKey]
        : null;
    var detail = errorbankViewModel.buildErrorbankDetail(entry, {
      antidote: antidote, // R8 解药 bank 供给(签发后 GET /luban/antidotes); 无=fail-closed 占位
      retestProbe: probe,
      position: { index: index, total: total },
    });
    this.setData({ mode: "detail", detail: detail, justSettledKey: "" });
    if (entry.packId && !probe) this._probeRetestPool(entry, index, total);
    if (
      antidoteKey &&
      !Object.prototype.hasOwnProperty.call(this._antidoteCache, antidoteKey)
    ) {
      this._probeAntidote(entry, index, total);
    }
  },

  // R8 解药单条探测: 详情页打开时按 {pack_id, error_code} 一次 GET(与错因银行
  // 同一只读投影, 非第二权威)。404/失败 = 负缓存 null → 保持「解药整理中」占位,
  // 绝不自造讲解(fail-closed, 与 _probeRetestPool 同款异步回填结构)。
  _probeAntidote: function (entry, index, total) {
    var that = this;
    var key = this._antidoteKey(entry);
    if (!key) return;
    api
      .getLubanAntidote(entry.packId, entry.errorCode, { silent: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        // 供给形状: {mental_model, textbook_ref}; 缺正文 = 视同无供给(负缓存)。
        that._antidoteCache[key] =
          body && body.mental_model
            ? { mental_model: body.mental_model, textbook_ref: body.textbook_ref || "" }
            : null;
      })
      .catch(function () {
        that._antidoteCache[key] = null; // 未签发/无此码/旗标关一律 404 → 占位
      })
      .then(function () {
        var detail = that.data.detail;
        if (that.data.mode !== "detail" || !detail || detail.key !== entry.key) return;
        that._openDetailAt(entry, index, total);
      });
  },

  // 变体池单站探测: 详情页打开时一次 GET(与 retest 页同一 read model,
  // 非第二权威; 列表禁 N+1 的收权语义不受影响)。失败/空池 = 不承诺换皮。
  _probeRetestPool: function (entry, index, total) {
    var that = this;
    api
      .getLubanRetestItems(entry.packId, 1, { silent: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var available = Array.isArray(body.items) && body.items.length > 0;
        that._probeCache[entry.packId] = { available: available };
      })
      .catch(function () {
        that._probeCache[entry.packId] = { available: false };
      })
      .then(function () {
        var detail = that.data.detail;
        if (that.data.mode !== "detail" || !detail || detail.key !== entry.key) return;
        that._openDetailAt(entry, index, total);
      });
  },

  // 复测通过返回 → 本地销账(呈现层记录, 绝不写掌握态)+ 竹青销章仪式
  _settleFromRetestResult: function () {
    var pending = this._pendingRetest;
    if (!pending) return;
    this._pendingRetest = null;
    var result = _readStorage(RETEST_RESULT_PREFIX + pending.packId);
    if (
      !result ||
      !(Number(result.at) > pending.leftAt) ||
      !(Number(result.total) > 0) ||
      Number(result.correct) !== Number(result.total)
    ) {
      return; // 没做完/没全对: 不销账, 无声返回
    }
    var settled = this._readSettled();
    settled[pending.itemKey] = { at: Number(result.at), packId: pending.packId };
    _writeStorage(SETTLED_STORE_KEY, settled);
    this.setData({ mode: "list", detail: null, justSettledKey: pending.itemKey });
    this._rebuildVm();
  },

  _readSettled: function () {
    var stored = _readStorage(SETTLED_STORE_KEY);
    return stored && typeof stored === "object" ? stored : {};
  },

  _loadAll: function () {
    var that = this;
    this.setData({ loading: true, errorText: "" });
    return Promise.all([
      // mistake-book 404(=DEEPTUTOR_MISTAKE_BOOK_ENABLED 关/记账未开通)不是整页
      // 失败: lessons 仍可渲染, 降级为诚实"记账未开通"空态(bookDisabled), 不冒充
      // "都还清了"庆祝态; 网络类错误照旧走整页错误+重试。
      api
        .getMistakeBook({ include_mastered: true }, { suppressAuthRedirect: true })
        .catch(function (err) {
          if (err && Number(err.statusCode) === 404) return { __disabled: true };
          throw err;
        }),
      api.getLubanLessons().catch(function () {
        return null; // lessons 拿不到: pack 归属降级为空(换皮 CTA fail-closed)
      }),
    ])
      .then(function (results) {
        var disabled = !!(results[0] && results[0].__disabled);
        that._mistakeBody = disabled ? { items: [] } : api.unwrapResponse(results[0]) || {};
        that._lessonsBody = api.unwrapResponse(results[1]) || {};
        that.setData({ loading: false, bookDisabled: disabled });
        that._rebuildVm();
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "错因银行加载失败，请稍后重试"),
        });
      });
  },

  _rebuildVm: function () {
    var vm = errorbankViewModel.buildErrorbankViewModel({
      mistakeBook: this._mistakeBody || {},
      lessons: this._lessonsBody || {},
      settledLocal: this._readSettled(),
    });
    this.setData({ vm: vm });
    this._syncSettledPreview();
  },

  _syncSettledPreview: function () {
    var vm = this.data.vm;
    var entries = (vm && vm.settledEntries) || [];
    this.setData({
      settledPreview: this.data.settledExpanded
        ? entries
        : entries.slice(0, SETTLED_PREVIEW_COUNT),
    });
  },
});
