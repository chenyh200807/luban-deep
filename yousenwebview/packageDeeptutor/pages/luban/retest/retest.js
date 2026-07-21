// 鲁班学习双轮 · 变体复测（spike 形态）
// 拉 /retest-items（服务端确定性投影 + selection identity）→ 客户端只回传选择；
// 全题完成后 POST /retest-complete，由服务端按 canonical 内容源重判并提交唯一 terminal。
// 页面不写 learner state、不发 station_completed；保存失败不展示收据。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 每题作答 = retest_item_answered（module=practice, action=complete,
//   object_type=variant, object_id=variant_id, result=correct|incorrect）
// - 全部答完 = learning_action_completed（object_type=retest,
//   object_id=pack_id, result="<correct>/<total>"）
const api = require("../../../utils/api");
const telemetry = require("../../../utils/surface-telemetry");
const helpers = require("../../../utils/helpers");
const route = require("../../../utils/route");
const auth = require("../../../utils/auth");
const { validateCompletionReceipt } = require("../../../utils/retest-receipt");

var RETEST_LIMIT = 5;

// 桥接 query 解码兜底(QA 死证):compiled practice HTML 注入器把 answers/projection_receipt
// 用 encodeURIComponent 编码进跳转 URL(practice_html.py __dtRedirectEvidence);DevTools 实测
// wx 导航路径把 query 原样保持 percent-encoded(`answers` 以 %5B%7B%22 开头) → 裸 JSON.parse 抛错
// → 用户看到"题目内容已更新，请返回重新完成五题"。真机 web-view JSSDK 可能自动解码一次(未知),
// 故两种行为都必须安全。策略:先直接用,失败且仍含 '%' 才 decodeURIComponent 一层再试;有界循环
// 兼容双重编码(%25...)。幂等:已解码输入直接成功即返回,不会二次解码;裸 % 不会出现在合法 JSON/
// base64url token 里(variant/option id 为连字符字母数字,receipt 为 base64url),故安全。
var BRIDGE_DECODE_MAX_HOPS = 4;

// 逐层 decodeURIComponent,直到不再含 '%'、无变化、或解码抛错为止。对无 '%' 的输入是恒等。
function decodeBridgeToken(raw) {
  var candidate = String(raw == null ? "" : raw);
  for (var hop = 0; hop < BRIDGE_DECODE_MAX_HOPS && candidate.indexOf("%") !== -1; hop += 1) {
    var decoded;
    try {
      decoded = decodeURIComponent(candidate);
    } catch (_error) {
      break;
    }
    if (decoded === candidate) break;
    candidate = decoded;
  }
  return candidate;
}

// 先直接 JSON.parse(真机可能已解码一次);失败且含 '%' 才逐层解码重试。返回 {ok, value}。
function parseBridgeJson(raw) {
  var candidate = String(raw == null ? "" : raw);
  for (var hop = 0; hop <= BRIDGE_DECODE_MAX_HOPS; hop += 1) {
    try {
      return { ok: true, value: JSON.parse(candidate) };
    } catch (_error) {
      if (candidate.indexOf("%") === -1) break;
      var decoded;
      try {
        decoded = decodeURIComponent(candidate);
      } catch (_decodeError) {
        break;
      }
      if (decoded === candidate) break;
      candidate = decoded;
    }
  }
  return { ok: false, value: null };
}

function parseBridgeReceipt(query, mode) {
  if (mode !== "forward" || String((query && query.presentation) || "") !== "receipt") {
    return { requested: false, projectionReceipt: "", answers: [] };
  }
  var projectionReceipt = decodeBridgeToken((query && query.projection_receipt) || "").trim();
  var parsed = parseBridgeJson(String((query && query.answers) || "").trim());
  if (!parsed.ok) return null;
  var answers = parsed.value;
  var variantIds = {};
  if (
    !projectionReceipt ||
    !Array.isArray(answers) ||
    answers.length !== RETEST_LIMIT ||
    answers.some(function (answer) {
      var variantId = String((answer && answer.variant_id) || "").trim();
      var optionId = String((answer && answer.selected_option_id) || "").trim();
      if (!variantId || !optionId || variantIds[variantId]) return true;
      variantIds[variantId] = true;
      return false;
    })
  ) return null;
  return { requested: true, projectionReceipt: projectionReceipt, answers: answers };
}

// 两种取题模式共用本页（复用同一 retest 页/内核，不建第二答题页）：
// - review（默认，复习轮换皮复测）；
// - forward（学习轮五题轻练；有 finished 供给的题面/答案来自 compiled HTML）。
// review 旧判断题保留即时呈现；forward 单选不下发答案，服务端 completion 是唯一判分/写回入口。
var COPY = {
  review: {
    navTitle: "换皮复测",
    heroKicker: "昨天的考点，换了一身皮",
    heroTitle: "看看你能不能一眼认出它",
    loadingText: "正在取今天的题…",
    emptyText: "今天这一站暂时没有复测题，明天再来。",
    doneTitlePrefix: "今天的回炉完成",
    doneDesc: "本轮结果已保存，系统会按你的复习节奏再次安排。",
  },
  forward: {
    navTitle: "课后轻练 · 5 题",
    heroKicker: "刚学完，用五题把它钉牢",
    heroTitle: "条件、工序、纠错、检查、诊断各来一题",
    loadingText: "正在给你抽题…",
    emptyText: "这一站的轻练题即将开通，先去把它讲懂。",
    doneTitlePrefix: "这 5 题已记下",
    doneDesc: "这次先记为已练过；是否稳定，等下一次换皮复测。",
  },
  // 错后当场确认(变体判断题消费点1): 拿刚做错的考点，换个皮当场再确认一遍。
  confirm: {
    navTitle: "当场确认",
    heroKicker: "刚才那个点，换身皮再看一眼",
    heroTitle: "判断这句话妥不妥当",
    loadingText: "正在给你抽题…",
    emptyText: "这个考点的确认题即将开通，先去把它看清。",
    doneTitlePrefix: "这几道确认题已记下",
    doneDesc: "刚才的薄弱点已当场再练一遍；是否稳定，等下一次换皮复测。",
  },
};

// ── 题给面板呈现层 ──
// 服务端签发 figure = 编译期从成品页绘制代码求值出的元素列表(334px 坐标系)。
// 这里只做纯几何缩放(px→rpx)与样式拼装, 零造词零改数; 无 figure 的题不渲。
// 画板可用宽 = 750 - 页内边距48 - 题卡内边距60 - 面板内边距40 - 边框≈8 = 594rpx
var FIG_BOARD_RPX = 594;

function _figureViewModel(figure) {
  if (!figure || !Array.isArray(figure.els) || !figure.els.length) return null;
  var w = Number(figure.w) > 0 ? Number(figure.w) : 334;
  var k = FIG_BOARD_RPX / w;
  var scale = function (value) { return Math.round((Number(value) || 0) * k * 10) / 10; };
  var els = [];
  for (var i = 0; i < figure.els.length; i += 1) {
    var el = figure.els[i] || {};
    var style =
      "left:" + scale(el.x) + "rpx;top:" + scale(el.top) + "rpx;" +
      "width:" + scale(el.w) + "rpx;height:" + scale(el.h) + "rpx;";
    if (el.bg && el.bg !== "transparent") style += "background:" + el.bg + ";";
    if (el.bd && el.bd !== "none") style += "border:" + el.bd + ";";
    if (el.r) style += "border-radius:" + scale(el.r) + "rpx;";
    if (el.fg) style += "color:" + el.fg + ";";
    if (el.fs) style += "font-size:" + scale(el.fs) + "rpx;";
    if (el.fw) style += "font-weight:" + el.fw + ";";
    if (el.ta) style += "text-align:" + el.ta + ";";
    if (el.jc) style += "justify-content:" + el.jc + ";";
    if (el.ai) style += "align-items:" + el.ai + ";";
    if (el.p && el.p !== "0") style += "padding:" + el.p + ";";
    els.push({ style: style, lab: String(el.lab || "") });
  }
  return {
    label: String(figure.label || ""),
    caption: String(figure.caption || ""),
    bg: String(figure.bg || "#ffffff"),
    height: Math.round((Number(figure.h) || 100) * k),
    els: els,
  };
}

// 错后当场确认会话的 facts 解析。有界解码兜底(≤4 跳,同 parseBridgeReceipt
// 的桥接教训):wx 各端对 navigateTo query 的解码行为不一致,DevTools 活体隔离
// 实验证实整串 encodeURIComponent 后送达仍是 %2C,split(",") 拆不开 → 0 题断链。
// 先把整串解码到不动点再拆,兼容已解码/单次编码/双重编码三形态。
function parseConfirmFacts(query) {
  var raw = String((query && query.confirm_facts) || "");
  for (var i = 0; i < 4 && raw.indexOf("%") !== -1; i += 1) {
    try {
      var decoded = decodeURIComponent(raw);
      if (decoded === raw) break;
      raw = decoded;
    } catch (e) {
      break;
    }
  }
  return raw
    .split(",")
    .map(function (fact) { return fact.trim(); })
    .filter(function (fact) { return fact; })
    .slice(0, 5);
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    packId: "",
    practiceSurface: "",
    mode: "review",
    probeId: "",
    trainingIntentId: "",
    dayIndex: 0,
    selectionId: "",
    completionId: "",
    syncStatus: "idle",
    syncError: "",
    terminalEventId: "",
    receiptSyncText: "",
    receiptStateText: "",
    receiptNextText: "",
    navTitle: COPY.review.navTitle,
    heroKicker: COPY.review.heroKicker,
    heroTitle: COPY.review.heroTitle,
    loadingText: COPY.review.loadingText,
    emptyText: COPY.review.emptyText,
    doneTitlePrefix: COPY.review.doneTitlePrefix,
    doneDesc: COPY.review.doneDesc,
    loading: true,
    errorText: "",
    items: [],
    total: 0,
    pool: null,          // 题池元信息 {core_total, rule_groups_total}(呈现层规模感)
    practiceSource: "signed_variant",
    bridgeMode: false,
    bridgeProjectionReceipt: "",
    bridgeAnswers: [],
    projectionReceipt: "",
    projectionDigest: "",
    seenCount: 0,        // 本地已见变体数(收集感, storage 呈现层)
    answeredCount: 0,
    correctCount: 0,
    done: false,
    // 单题聚焦流(纸墨版): 当前题指针 + 完场收据
    currentIndex: 0,
    showReceipt: false,
    wrongItems: [],      // 收据"再看一眼"清单(签发 correct_statement 逐字)
    rightItems: [],      // 收据"答对"清单(同源签发门道, 呈现层)
    ruleGroupCount: 0,   // 考法覆盖(去重 rule_group 数, 呈现层统计)
    textbookCount: 0,    // 翻出的教材原文句数(join 命中数, 呈现层统计)
    // 错后当场确认(变体判断题消费点1)——纯导航态, 零第二权威
    isConfirmSession: false,   // 本次已是 confirm 会话(禁再套娃)
    confirmFacts: [],          // confirm 会话传入的错题 facts(URL query)
    confirmAnchor: "",         // 服务端 canonical forward terminal；只作签发输入，服务端复核
    confirmFactsReady: [],     // 服务端 confirm_facts_ready(有 immediate_confirm 供给的 fact)
    confirmEntryFacts: [],     // 收据里可当场确认的错题 facts(与 ready 交集)
    showConfirmEntry: false,   // 收据是否亮「错题当场确认」入口
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    var packId = String((query && query.pack_id) || "").trim();
    var mode = String((query && query.mode) || "review") === "forward" ? "forward" : "review";
    var practiceSurface = String((query && query.practice_surface) || "").trim();
    var bridgeReceipt = parseBridgeReceipt(query, mode);
    var bridgeRequested = String((query && query.presentation) || "") === "receipt";
    var probeId = String((query && query.probe_id) || "").trim();
    var trainingIntentId = String((query && query.training_intent_id) || "").trim();
    // 错后当场确认会话: mode=forward&confirm_facts=f1,f2(客户端传的错题 facts, ≤5)。
    var confirmFacts = parseConfirmFacts(query);
    var isConfirmSession = mode === "forward" && confirmFacts.length > 0;
    var confirmAnchor = String((query && query.confirm_anchor) || "").trim();
    var completionId =
      "retest_" +
      String(packId || "unknown") +
      "_" +
      mode +
      "_" +
      Date.now() +
      "_" +
      Math.random().toString(16).slice(2, 10);
    var copy = COPY[isConfirmSession ? "confirm" : mode];
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDarkOr("light"),
      packId: packId,
      practiceSurface: practiceSurface,
      mode: mode,
      isConfirmSession: isConfirmSession,
      confirmFacts: confirmFacts,
      confirmAnchor: confirmAnchor,
      bridgeMode: bridgeRequested,
      bridgeProjectionReceipt: bridgeReceipt ? bridgeReceipt.projectionReceipt : "",
      bridgeAnswers: bridgeReceipt ? bridgeReceipt.answers : [],
      probeId: probeId,
      trainingIntentId: trainingIntentId,
      completionId: completionId,
      navTitle: copy.navTitle,
      heroKicker: copy.heroKicker,
      heroTitle: copy.heroTitle,
      loadingText: copy.loadingText,
      emptyText: copy.emptyText,
      doneTitlePrefix: copy.doneTitlePrefix,
      doneDesc: copy.doneDesc,
    });
    if (!packId) {
      this.setData({ loading: false, errorText: "缺少站点参数，请从提分路线进入" });
      return;
    }
    if (bridgeRequested && bridgeReceipt === null) {
      this.setData({ loading: false, errorText: "题目内容已更新，请返回重新完成五题" });
      return;
    }
    this._loadItems();
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._loadItems();
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: route.lubanTeachingPoints(),
      });
    }
  },

  // 「这样做妥当」/「不妥当」——本地确定性判分：选择 == expected_ok
  onChoiceTap(event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var choiceOk = dataset.choice === "ok";
    var items = this.data.items;
    if (!Number.isFinite(index) || index < 0 || index >= items.length) return;
    var item = items[index];
    if (!item || item.answered) return;

    var correct = choiceOk === Boolean(item.expected_ok);
    // 每题作答（任务稿 luban_retest_answer 的登记名）
    // practice_mode 判别位（spike 命门）：forward=学习轮当天轻练 / review=复习轮次日复测,
    // 埋点里必须可分,否则 D1 留存(GO 门)读不出。register-before-use catalog 已登记允许值。
    telemetry.trackProductBehavior("retest_item_answered", {
      module: "practice",
      action: "complete",
      objectType: "variant",
      objectId: item.variant_id,
      result: correct ? "correct" : "incorrect",
      practiceMode: this.data.mode,
    });

    var answeredCount = this.data.answeredCount + 1;
    var correctCount = this.data.correctCount + (correct ? 1 : 0);
    var allAnswered = answeredCount >= this.data.total && this.data.total > 0;
    var patch = {
      answeredCount: answeredCount,
      correctCount: correctCount,
      done: false,
    };
    patch["items[" + index + "].answered"] = true;
    patch["items[" + index + "].correct"] = correct;
    patch["items[" + index + "].chosenOk"] = choiceOk;
    this.setData(patch);
    var draftItems = items.slice();
    draftItems[index] = Object.assign({}, item, {
      answered: true,
      correct: correct,
      chosenOk: choiceOk,
    });
    this._persistDraft(draftItems);

    if (allAnswered) {
      // 收据数据(呈现层统计, 全部来自签发字段)
      var all = items.slice();
      all[index] = Object.assign({}, item, { answered: true, correct: correct });
      var groups = {};
      var textbookCount = 0;
      var wrong = [];
      var right = [];
      all.forEach(function (it) {
        if (it.rule_group) groups[it.rule_group] = true;
        if (it.textbook) textbookCount += 1;
        if (it.answered && it.correct === false) wrong.push(it);
        if (it.answered && it.correct === true) right.push(it);
      });
      this.setData({
        wrongItems: wrong,
        rightItems: right,
        ruleGroupCount: Object.keys(groups).length,
        textbookCount: textbookCount,
      });
      this._submitCompletion(all);
    }
  },

  // 编译 HTML 单选题：客户端只记录 option identity（可变草稿），不持有正确答案。
  // 收权纪律：tap 只写 selectedOptionId，是"已选未定稿"的可变草稿——用户离开本题
  // 前可反复改选（再点别的选项覆盖），高亮天然跟随 selectedOptionId。定稿（answered）、
  // 计数、提交全部收敛到 nextQuestion（离开本题的唯一动作），此处一概不写。
  // 未定稿选择不落盘：draft 只承载已定稿项（_persistDraft filter by answered，restore 据
  // selected_option_id 标 answered），避免给 draft/restore 引入"未定稿"第二子态。
  onOptionTap(event) {
    var dataset = (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var optionId = String(dataset.optionId || "").trim();
    var items = this.data.items;
    if (!Number.isFinite(index) || index < 0 || index >= items.length || !optionId) return;
    var item = items[index];
    // 已定稿（answered）的单选题锁定不可改（离开即锁,防离开后作弊/漂移）;
    // 未定稿的当前题允许反复改选。
    if (!item || item.answered || item.answer_type !== "single_choice") return;
    if (!(item.options || []).some(function (option) { return option.option_id === optionId; })) return;

    var patch = {};
    patch["items[" + index + "].selectedOptionId"] = optionId;
    this.setData(patch);
  },

  // 单选题定稿唯一权威：离开当前题时才把该题 answered=true、answeredCount 累加、持久化草稿。
  // 幂等：已定稿或非单选题一律 no-op（answered 幂等标记防重复计数）；未选择不能定稿。
  // 判断题（onChoiceTap）在点击当场即已定稿,此处不再处理。
  _finalizeCurrent() {
    var index = this.data.currentIndex;
    var items = this.data.items;
    var item = items[index];
    if (!item) return { items: items, finalized: false };
    if (item.answered || item.answer_type !== "single_choice") return { items: items, finalized: false };
    if (!item.selectedOptionId) return { items: items, finalized: false };

    var answeredCount = this.data.answeredCount + 1;
    var patch = { answeredCount: answeredCount, done: false };
    patch["items[" + index + "].answered"] = true;
    this.setData(patch);
    var finalizedItems = items.slice();
    finalizedItems[index] = Object.assign({}, item, { answered: true });
    this._persistDraft(finalizedItems);
    return { items: finalizedItems, finalized: true };
  },

  _draftKey() {
    return "luban_retest_draft:" + String(this.data.packId || "") + ":" + String(this.data.mode || "review");
  },

  _readDraft() {
    try {
      return auth.readOwnerStorage ? auth.readOwnerStorage(this._draftKey()) : null;
    } catch (_error) {
      return null;
    }
  },

  _persistDraft(items) {
    if (!this.data.selectionId || !auth.writeOwnerStorage) return;
    var answers = (items || this.data.items || [])
      .filter(function (item) { return item && item.answered; })
      .map(function (item) {
        return {
          variant_id: String(item.variant_id || ""),
          selected_option_id: String(item.selectedOptionId || ""),
          choice_ok: item.chosenOk === true,
          answer_type: String(item.answer_type || ""),
        };
      });
    try {
      auth.writeOwnerStorage(this._draftKey(), {
        projection_receipt: this.data.projectionReceipt,
        projection_digest: this.data.projectionDigest,
        selection_id: this.data.selectionId,
        completion_id: this.data.completionId,
        answers: answers,
        updated_at: Date.now(),
      });
    } catch (_error) {}
  },

  _clearDraft() {
    try {
      if (auth.removeOwnerStorage) auth.removeOwnerStorage(this._draftKey());
    } catch (_error) {}
  },

  _restoreDraft(items, selectionId, projectionReceipt, projectionDigest) {
    var draft = this._readDraft();
    if (
      !draft ||
      !selectionId ||
      String(draft.selection_id || "") !== String(selectionId || "") ||
      (
        this.data.bridgeMode &&
        (
          !projectionReceipt ||
          draft.projection_receipt !== projectionReceipt ||
          String(draft.projection_digest || "") !== String(projectionDigest || "")
        )
      ) ||
      !Array.isArray(draft.answers)
    ) {
      if (draft) this._clearDraft();
      return { items: items, completionId: "" };
    }
    var byVariant = {};
    draft.answers.forEach(function (answer) {
      byVariant[String((answer && answer.variant_id) || "")] = answer;
    });
    var restored = items.map(function (item) {
      var answer = byVariant[String(item.variant_id || "")];
      if (!answer) return item;
      if (item.answer_type === "single_choice") {
        var optionId = String(answer.selected_option_id || "");
        if (!(item.options || []).some(function (option) { return option.option_id === optionId; })) return item;
        return Object.assign({}, item, { answered: true, selectedOptionId: optionId });
      }
      return Object.assign({}, item, { answered: true, chosenOk: answer.choice_ok === true });
    });
    return { items: restored, completionId: String(draft.completion_id || "") };
  },

  // 本地"已见变体"集合(收集感, 呈现层非学情): 读旧集合并入本场
  _seenCount(items) {
    var key = "luban_retest_seen:" + (this.data.packId || "");
    var ownerId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    var seen = [];
    try {
      var raw = auth.readOwnerStorage ? auth.readOwnerStorage(key) : null;
      if (raw && Array.isArray(raw.ids)) seen = raw.ids;
    } catch (_e) {}
    var set = {};
    seen.forEach(function (id) { set[id] = true; });
    (items || []).forEach(function (it) { set[it.variant_id] = true; });
    var ids = Object.keys(set);
    try {
      if (ownerId && auth.writeOwnerStorage)
        auth.writeOwnerStorage(key, { ids: ids, at: Date.now() });
    } catch (_e) {}
    return ids.length;
  },

  // 单题流推进（MCQ 定稿唯一入口）: 离开当前题时先定稿该题,再翻页 / 末题统一提交。
  // "下一题/查看结果"的动作 = 离开该题的动作 = 定稿时机（业务事实 root-cause 第 2 点）。
  nextQuestion() {
    var finalized = this._finalizeCurrent();
    var items = finalized.items;
    var next = this.data.currentIndex + 1;
    if (next < this.data.total) {
      this.setData({ currentIndex: next });
      return;
    }
    // 末题：离开本题 = 统一提交（服务端重判唯一入口,架构不变）。
    if (this.data.syncStatus === "synced") { this.setData({ showReceipt: true }); return; }
    if (this.data.syncStatus === "syncing") return;
    if (this.data.syncStatus === "error") { this.retryCompletion(); return; }
    if (!items.length || items.some(function (item) { return !item.answered; })) return;
    this._submitCompletion(items.slice());
  },

  retryCompletion() {
    var all = (this.data.items || []).slice();
    if (!all.length || all.some(function (item) { return !item.answered; })) return;
    this._submitCompletion(all);
  },

  goConceptCards: function () {
    var packId = this.data.packId || "";
    if (!packId) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: route.lubanConceptCards({ pack_id: packId }),
      });
    }
  },

  // 错后当场确认(消费点1): 同页新会话 mode=forward&confirm_facts=错题facts;
  // boolean 渲染/completion 全复用, 不建第二答题页。纯导航零第二权威。
  goConfirmFacts: function () {
    var packId = this.data.packId || "";
    var facts = (this.data.confirmEntryFacts || []).slice(0, 5);
    var parentTerminal = String(this.data.terminalEventId || "").trim();
    if (!packId || !facts.length || !parentTerminal) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          encodeURIComponent(String(packId)) +
          // 逐 fact 编码后用字面逗号连接——整串 encodeURIComponent 会把分隔逗号
          // 变成 %2C,接收端 split(",") 拆不开(DevTools 活体隔离实验证实断链)。
          "&mode=forward&confirm_facts=" +
          facts.map(function (f) { return encodeURIComponent(String(f)); }).join(",") +
          "&confirm_anchor=" +
          encodeURIComponent(parentTerminal),
      });
    }
  },

  continueAfterReceipt() {
    // Canonical receipt is already rendered on this page.  Do not hand a
    // terminal truth to another page through forgeable query parameters.
    this.goBack();
  },

  // 收据错项呈现层：按 selectedOptionId 从签发 options 里取所选选项文本。
  // 纯查找零造词；查不到（如判断题无 options）返回空串 → 对应层整行隐藏。
  _selectedOptionText(item) {
    var selectedId = String((item && item.selectedOptionId) || "").trim();
    if (!selectedId) return "";
    var options = (item && item.options) || [];
    for (var i = 0; i < options.length; i++) {
      if (String(options[i].option_id || "") === selectedId) {
        return String(options[i].text || "");
      }
    }
    return "";
  },

  _submitCompletion(items) {
    if (this.data.syncStatus === "syncing" || this.data.syncStatus === "synced") return;
    var that = this;
    this.setData({ syncStatus: "syncing", syncError: "" });
    return api
      .completeLubanRetest(this.data.packId, {
        completion_id: this.data.completionId,
        selection_id: this.data.selectionId,
        mode: this.data.mode,
        day_index: this.data.dayIndex,
        training_intent_id: this.data.trainingIntentId,
        probe_id: this.data.probeId,
        answers: items.map(function (item) {
          if (item.answer_type === "single_choice") {
            return {
              variant_id: item.variant_id,
              selected_option_id: item.selectedOptionId,
            };
          }
          return { variant_id: item.variant_id, choice_ok: item.chosenOk === true };
        }),
      })
      .then(function (response) {
        var body = api.unwrapResponse(response) || response || {};
        var terminalEventId = String(body.terminal_event_id || "").trim();
        if (!terminalEventId) throw new Error("canonical terminal receipt missing");
        var changeStatus = String((body.learning_change || {}).status || "").trim();
        var expectedChange = that.data.mode === "forward"
          ? changeStatus === "practice_recorded"
          : changeStatus === "verification_passed" || changeStatus === "verification_failed";
        if (!expectedChange) throw new Error("canonical learning change missing");
        // terminal id/change 状态不足以证明逐题回执完整。exact validator 要求
        // 本次提交的每个 variant 恰有一个 boolean 结果，且聚合分数完全一致；
        // 缺项/重复/陌生题/类型漂移一律留在 error，可重试且不清 draft。
        var receipt = validateCompletionReceipt(items, body);
        var serverResults = receipt.resultsById;
        var scoredItems = items.map(function (item) {
          var result = serverResults[item.variant_id];
          var next = Object.assign({}, item, {
            correct: result.is_correct === true,
            correct_statement: String(result.correct_statement || item.correct_statement || ""),
            feedback: result.feedback || null,
          });
          if (item.answer_type === "single_choice") {
            telemetry.trackProductBehavior("retest_item_answered", {
              module: "practice",
              action: "complete",
              objectType: "variant",
              objectId: item.variant_id,
              result: next.correct ? "correct" : "incorrect",
              practiceMode: that.data.mode,
            });
          }
          return next;
        });
        var serverCorrectCount = receipt.correctCount;
        var groups = {};
        var textbookCount = 0;
        var wrong = [];
        var right = [];
        scoredItems.forEach(function (item) {
          if (item.rule_group) groups[item.rule_group] = true;
          if (item.textbook) textbookCount += 1;
          if (item.correct === false) {
            wrong.push(Object.assign({}, item, {
              selectedOptionText: that._selectedOptionText(item),
            }));
          } else if (item.correct === true) {
            right.push(item);
          }
        });
        // 错后当场确认入口(消费点1): 错题 fact_id ∩ 服务端 confirm_facts_ready。
        // 仅 forward 且非 confirm 会话本身(禁套娃); 供给闸不过时 ready 恒空 → 不亮。
        var confirmEntryFacts = [];
        if (that.data.mode === "forward" && !that.data.isConfirmSession) {
          var readySet = {};
          (that.data.confirmFactsReady || []).forEach(function (fact) {
            if (fact) readySet[String(fact)] = true;
          });
          var seenFact = {};
          wrong.forEach(function (item) {
            var fact = String(item.fact_id || "");
            if (fact && readySet[fact] && !seenFact[fact]) {
              seenFact[fact] = true;
              confirmEntryFacts.push(fact);
            }
          });
        }
        telemetry.trackProductBehavior("learning_action_completed", {
          module: "practice",
          action: "complete",
          objectType: "retest",
          objectId: that.data.packId,
          result: serverCorrectCount + "/" + that.data.total,
          practiceMode: that.data.mode,
        });
        that._clearDraft();
        var reviewPassed = changeStatus === "verification_passed";
        that.setData({
          syncStatus: "synced",
          syncError: "",
          terminalEventId: terminalEventId,
          receiptSyncText: "服务器已复核 · 已更新学习记录",
          receiptStateText: that.data.mode === "forward"
            ? "已练过 · 待验证"
            : (reviewPassed ? "复测通过 · 已更新" : "还需巩固 · 已更新"),
          receiptNextText: that.data.mode === "forward"
            ? "本次课后轻练不等于已经掌握；学习页会按记录安排下一次验证。"
            : (reviewPassed ? "这次换皮复测通过，学习页会按记录安排后续验证。" : "本次薄弱点已记录，学习页会继续安排验证。"),
          items: scoredItems,
          correctCount: serverCorrectCount,
          wrongItems: wrong,
          rightItems: right,
          confirmEntryFacts: confirmEntryFacts,
          showConfirmEntry: confirmEntryFacts.length > 0,
          ruleGroupCount: Object.keys(groups).length,
          textbookCount: textbookCount,
          done: true,
          showReceipt: true,
        });
      })
      .catch(function (err) {
        that._persistDraft(items);
        that.setData({
          syncStatus: "error",
          syncError: api.describeRequestError(err, "保存失败，请重试后再查看收据"),
        });
      });
  },

  _loadItems() {
    var that = this;
    return api
      .getLubanRetestItems(this.data.packId, RETEST_LIMIT, this.data.mode, {
        practiceSurface: this.data.practiceSurface,
        projectionReceipt: this.data.bridgeProjectionReceipt,
        probeId: this.data.probeId,
        confirmFacts: this.data.confirmFacts,
        confirmAnchor: this.data.confirmAnchor,
      })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var raw = Array.isArray(body.items) ? body.items : [];
        var declaredPracticeSource = String(body.practice_source || "");
        var practiceSource = declaredPracticeSource || "signed_variant";
        var variantProbeRole = String(body.variant_probe_role || "");
        if (
          that.data.isConfirmSession &&
          (
            declaredPracticeSource !== "signed_variant" ||
            variantProbeRole !== "immediate_confirm" ||
            !raw.length ||
            raw.some(function (item) {
              return String((item && item.probe_role) || "") !== "immediate_confirm";
            })
          )
        ) {
          throw new Error("retest_confirm_authority_invalid");
        }
        var confirmFactsReady = Array.isArray(body.confirm_facts_ready)
          ? body.confirm_facts_ready.map(function (fact) { return String(fact || ""); })
          : [];
        var projectionReceipt = String(body.projection_receipt || "").trim();
        var projectionDigest = String(body.projection_digest || "").trim();
        var pool = body.pool && body.pool.core_total ? body.pool : null;
        var items = raw.map(function (item, idx) {
          return {
            key: String(item.variant_id || "v_" + idx),
            variant_id: item.variant_id,
            rule_group: item.rule_group,
            answer_type: item.answer_type || "boolean",
            surface: item.surface,
            stem: item.stem || item.surface,
            // letter 是纯呈现层座位号(A/B/C/D), option_id 才是回传身份
            options: (Array.isArray(item.options) ? item.options : []).map(function (option, optionIdx) {
              return Object.assign({ letter: String.fromCharCode(65 + optionIdx) }, option);
            }),
            expected_ok: item.answer_type === "single_choice" ? null : Boolean(item.expected_ok),
            correct_statement: item.correct_statement,
            anchor: item.anchor,
            fact_id: String(item.fact_id || ""),     // 错题→考点映射(错后当场确认入口据此判交集)
            probe_role: String(item.probe_role || ""),
            textbook: item.textbook || null, // 教材原文并排卡(join 命中才有, 前端零造词)
            figure: _figureViewModel(item.figure), // 题给面板(签发才渲, 纯几何缩放)
            answered: false,
            correct: null,
            chosenOk: null,
            selectedOptionId: "",
            feedback: null,
          };
        });
        var selectionId = String(body.selection_id || "");
        var restored = that._restoreDraft(
          items, selectionId, projectionReceipt, projectionDigest
        );
        items = restored.items;
        var restoredCount = items.filter(function (item) { return item.answered; }).length;
        var bridgedItems = null;
        if (that.data.bridgeMode) {
          if (
            practiceSource !== "compiled_html" ||
            !projectionReceipt ||
            projectionReceipt !== that.data.bridgeProjectionReceipt ||
            that.data.bridgeAnswers.length !== items.length
          ) {
            throw new Error("content_updated_retake");
          }
          bridgedItems = items.map(function (item, index) {
            var answer = that.data.bridgeAnswers[index] || {};
            var optionId = String(answer.selected_option_id || "");
            if (
              String(answer.variant_id || "") !== String(item.variant_id || "") ||
              !(item.options || []).some(function (option) { return option.option_id === optionId; })
            ) throw new Error("content_updated_retake");
            return Object.assign({}, item, {
              answered: true,
              selectedOptionId: optionId,
            });
          });
          items = bridgedItems;
        }
        that.setData({
          pool: pool,
          practiceSource: practiceSource,
          confirmFactsReady: confirmFactsReady,
          showConfirmEntry: false,
          confirmEntryFacts: [],
          dayIndex: Number(body.day_index || 0),
          selectionId: selectionId,
          completionId: restored.completionId || that.data.completionId,
          projectionReceipt: projectionReceipt,
          projectionDigest: projectionDigest,
          seenCount: that._seenCount(items),
          items: items,
          total: items.length,
          answeredCount: bridgedItems ? bridgedItems.length : restoredCount,
          correctCount: 0,
          done: false,
          currentIndex: Math.max(0, (bridgedItems ? bridgedItems.length : restoredCount || 1) - 1),
          showReceipt: false,
          wrongItems: [],
          rightItems: [],
          ruleGroupCount: 0,
          textbookCount: 0,
          loading: false,
          errorText: "",
          syncStatus: "idle",
          syncError: "",
          receiptSyncText: "",
          receiptStateText: "",
          receiptNextText: "",
        });
        that._persistDraft(items);
        if (bridgedItems) that._submitCompletion(bridgedItems);
        else if (restoredCount === items.length && items.length > 0) that._submitCompletion(items);
      })
      .catch(function (err) {
        var errorCode = api.errorCodeOf ? api.errorCodeOf(err) : String((err && err.message) || "");
        var contentUpdated = errorCode === "content_updated_retake" || String((err && err.message) || "") === "content_updated_retake";
        // 练习供给尚未签发发布 != 收据漂移: 前者给暖文案"先看讲解打底", 不清草稿,
        // 也不催用户"重做已更新的题"(那是把教研节奏问题误伤成用户侧数据问题).
        var notReleased = errorCode === "practice_not_released";
        if (contentUpdated) that._clearDraft();
        that.setData({
          loading: false,
          errorText: contentUpdated
            ? "题目内容已更新，请返回重新完成五题"
            : notReleased
            ? "这一站的练习还在教研签发中，先看讲解打底"
            : api.describeRequestError(err, "复测题加载失败，请稍后重试"),
        });
      });
  },
});
