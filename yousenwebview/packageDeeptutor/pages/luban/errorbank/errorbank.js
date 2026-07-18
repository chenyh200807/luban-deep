// 错因银行(复习二期二级页 · 列表/详情/空态)
// 设计权威: review-phase2-design/errorbank-detail.html(第10轮宣纸补稿)
// 数据边界(零第二学情权威, 详见 errorbank-view-model.js 头注):
// - 记账真值 = 云端错题集 read model(只读); pack 归属对照 lessons read model;
// - R8 解药 runtime 无供给 → fail-closed 降级卡(深链既有解析), 数据位已留;
// - 已标记 = 只呈现服务端 mastered 旗标;复测只推进复习节奏,绝不在前端销单题;
// - 到期复测 = 只消费 review-due 的 pack + probe; 页面不探题池、不自算到期。
var api = require("../../../utils/api");
var auth = require("../../../utils/auth");
var helpers = require("../../../utils/helpers");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var errorbankViewModel = require("../../../utils/errorbank-view-model");

var SETTLED_PREVIEW_COUNT = 2;

function _writeStorage(key, value) {
  if (auth.writeOwnerStorage) auth.writeOwnerStorage(key, value);
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
      isDark: helpers.isDarkOr("light"),
    });
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanErrorbank());
      return;
    }
    this._probeCache = {}; // packId -> {available: bool, probeId: string}
    this._antidoteCache = {}; // "packId::errorCode" -> {mental_model, textbook_ref} | null
    this._loadAll();
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

  // ④ 复习动线 CTA: 只允许 canonical 到期 probe 进入 review 复测。
  openRetest: function () {
    var detail = this.data.detail;
    if (!detail || !detail.retest || !detail.retest.ready) return;
    var packId = detail.retest.packId;
    var probeId = detail.retest.probeId;
    if (!packId || !probeId) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          encodeURIComponent(packId) +
          "&mode=review&probe_id=" +
          encodeURIComponent(probeId),
      });
    }
  },

  // 解药查询键: 只有 packId 可诚实归属 ∧ errorCode 是注册表错因码才成立
  // (deriveRetestPackId / humanizeErrorLabel 对不上=空串)。任一空 = 不查, 保持
  // 「解药整理中」占位, 绝不拿半个键瞎猜。
  goConceptCards: function () {
    var detail = this.data.detail || {};
    var packId = detail.retest && detail.retest.packId;
    if (!packId) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.lubanConceptCards({ pack_id: packId }) });
    }
  },

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
    this.setData({ mode: "detail", detail: detail });
    if (entry.packId && !probe) this._resolveDueProbe(entry, index, total);
    if (
      antidoteKey &&
      !Object.prototype.hasOwnProperty.call(this._antidoteCache, antidoteKey)
    ) {
      this._probeAntidote(entry, index, total);
    }
  },

  // R8 解药单条探测: 详情页打开时按 {pack_id, error_code} 一次 GET(与错因银行
  // 同一只读投影, 非第二权威)。404/失败 = 负缓存 null → 保持「解药整理中」占位,
  // 绝不自造讲解(fail-closed, 与 _resolveDueProbe 同款异步回填结构)。
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
            ? {
                mental_model: body.mental_model,
                textbook_ref: body.textbook_ref || "",
                items: Array.isArray(body.items) ? body.items : [],
              }
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

  // 到期事实只读: 详情页消费 canonical review-due，匹配 pack + probe。
  // 未到期/无 probe/变体不可用/请求失败一律不亮销账 CTA，不降成 forward。
  _resolveDueProbe: function (entry, index, total) {
    var that = this;
    api
      .getLubanReviewDue({ silent: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var rows = Array.isArray(body.due) ? body.due : [];
        var matched = null;
        for (var i = 0; i < rows.length; i++) {
          var row = rows[i] || {};
          if (
            String(row.pack_id || "").toUpperCase() === String(entry.packId || "").toUpperCase() &&
            row.retest_available === true &&
            String(row.probe_id || "").trim()
          ) {
            matched = row;
            break;
          }
        }
        that._probeCache[entry.packId] = {
          available: !!matched,
          probeId: matched ? String(matched.probe_id).trim() : "",
        };
      })
      .catch(function () {
        that._probeCache[entry.packId] = { available: false, probeId: "" };
      })
      .then(function () {
        var detail = that.data.detail;
        if (that.data.mode !== "detail" || !detail || detail.key !== entry.key) return;
        that._openDetailAt(entry, index, total);
      });
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
