// 实务闯关(复习二期二级页 · 回忆→半写→核对三步)
// 设计权威: review-phase2-design/practice-gauntlet.html(第10轮宣纸补稿)
// 供给边界详见 gauntlet-view-model.js 头注:
// - 题面 = signed 变体池 read model(retest-items, 与 retest 页同一读源);
// - ②半写 = R6 挖空 bank 无供给 → 自由默写降级(接口位已留);
// - ③核对 = retest 同款本地确定性判分(choice === expected_ok), 零学情写入;
//   完成时只发既有非 promoting 信号(station_completed)+ 已登记埋点。
// - 草稿 = 本地 storage; 退出挽留 sheet 主按钮给退出(不做暗黑挽留)。
var api = require("../../../utils/api");
var telemetry = require("../../../utils/surface-telemetry");
var helpers = require("../../../utils/helpers");
var gauntletViewModel = require("../../../utils/gauntlet-view-model");

var GAUNTLET_LIMIT = 5;

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
    packId: "",
    title: "",
    loading: true,
    errorText: "",
    step: 1, // 1 回忆 | 2 半写 | 3 核对
    items: [],
    total: 0,
    pointCountLine: "",
    answeredCount: 0,
    verdict: null,
    draftText: "",
    draftSaved: false,
    showExitSheet: false,
    // ②半写 · R6 精确挖空(signed cloze bank 投影; null=无供给→自由默写降级)
    cloze: null,
    // 档位③全量作答(自由文本→判分内核 seam)。前端零判分, verdict 全由后端给。
    fullAnswer: null,
    fullAnswerLoading: false,
    fullAnswerNote: "", // 旗标关/未签发/失败时的诚实占位, 绝不本地伪造判分
  },

  onLoad: function (query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var sbh = info.statusBarHeight || 0;
    var packId = String((query && query.pack_id) || "").trim().toUpperCase();
    var title = String((query && query.title) || "").trim();
    this.setData({
      statusBarHeight: sbh,
      navHeight: sbh + 48,
      isDark: helpers.isDark(),
      packId: packId,
      title: title,
    });
    if (!packId) {
      this.setData({ loading: false, errorText: "缺少站点参数，请从复习页进入" });
      return;
    }
    // 退出留草稿的兑现: 有草稿则文字与步骤接着上次
    var draft = _readStorage(gauntletViewModel.draftStorageKey(packId));
    if (draft && typeof draft === "object" && draft.text) {
      this.setData({
        draftText: String(draft.text),
        draftSaved: true,
        step: Number(draft.step) === 2 ? 2 : 1,
      });
    }
    this._loadItems();
  },

  retry: function () {
    this.setData({ loading: true, errorText: "" });
    this._loadItems();
  },

  goBack: function () {
    // 半写有内容或已进行中 → 底部挽留 sheet(主按钮给退出, 草稿一字不丢)
    var inProgress =
      !this.data.loading &&
      !this.data.errorText &&
      this.data.total > 0 &&
      !(this.data.verdict && this.data.verdict.done) &&
      (this.data.step >= 2 || this.data.draftText);
    if (inProgress) {
      this.setData({ showExitSheet: true });
      return;
    }
    this._navigateBack();
  },

  // sheet 主按钮: 保留草稿 · 先退出
  exitWithDraft: function () {
    this._saveDraft();
    this.setData({ showExitSheet: false });
    this._navigateBack();
  },

  // sheet ghost: 继续作答
  dismissExitSheet: function () {
    this.setData({ showExitSheet: false });
  },

  // sheet 面板 catchtap 占位: 只挡冒泡到遮罩, 不做事
  noop: function () {},

  // ① → ②
  startHalfWrite: function () {
    this.setData({ step: 2 });
    this._saveDraft();
  },

  // ①兜底: 完全想不起来 → 回炉这一站(不惩罚想不起来的人)
  goStation: function () {
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/station/station?pack_id=" +
        encodeURIComponent(this.data.packId),
    });
  },

  onDraftInput: function (event) {
    var value = (event && event.detail && event.detail.value) || "";
    // 改了答案 → 旧的全量作答 verdict 作废(不留陈旧判分误导)
    this.setData({
      draftText: value,
      draftSaved: false,
      fullAnswer: null,
      fullAnswerNote: "",
    });
  },

  onDraftBlur: function () {
    this._saveDraft();
  },

  // ② → ③
  startVerify: function () {
    this._saveDraft();
    this.setData({ step: 3 });
  },

  // ②档位③全量作答: 自由默写文本 → 既有判分内核 seam(前端零判分、零改分)。
  // 唯一投递 { variant_id, answer_text }; 逐采分点 verdict 全由后端内核给回。
  submitFullAnswer: function () {
    var answer = String(this.data.draftText || "").trim();
    if (!answer) {
      this.setData({ fullAnswerNote: "先把你的判断理由写下来，再交给判分内核批" });
      return;
    }
    var items = this.data.items || [];
    var primary = items[0] || {};
    var variantId = String(primary.variant_id || "").trim();
    if (!variantId) {
      this.setData({ fullAnswerNote: "这一站暂无可判分的变体，先用逐条核对打底" });
      return;
    }
    this._saveDraft();
    // 等待态行内(判分要时间), 不做全屏遮罩
    this.setData({ fullAnswerLoading: true, fullAnswerNote: "", fullAnswer: null });
    var that = this;
    api
      .postLubanFullAnswer(this.data.packId, variantId, answer)
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var verdict = gauntletViewModel.buildFullAnswerVerdict(body);
        that.setData({ fullAnswer: verdict, fullAnswerLoading: false });
        // 已登记完成埋点(register-before-use): 全量作答是一次学习动作完成
        telemetry.trackProductBehavior("learning_action_completed", {
          module: "practice",
          action: "complete",
          objectType: "full_answer",
          objectId: that.data.packId,
          result: verdict.scoreLine || verdict.evidenceLevel,
        });
      })
      .catch(function (err) {
        // fail-closed: 旗标关/未签发 → 404 同形, 如实标「即将开通」, 绝不本地伪造判分
        var note =
          err && err.statusCode === 404
            ? "全量作答判分即将开通——先用下面逐条核对打底，一样扎实"
            : api.describeRequestError(err, "判分内核忙不过来，稍后再交一次");
        that.setData({ fullAnswerLoading: false, fullAnswerNote: note });
      });
  },

  // ③ 逐条核对: retest 同款本地确定性判分(唯一判分机制, 零学情写入)
  onChoiceTap: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var choiceOk = dataset.choice === "ok";
    var items = this.data.items;
    if (!Number.isFinite(index) || index < 0 || index >= items.length) return;
    var item = items[index];
    if (!item || item.answered) return;

    var correct = gauntletViewModel.gradeChoice(item, choiceOk);
    // 已登记事件名(register-before-use): 变体作答与 retest 同一动作语义
    telemetry.trackProductBehavior("retest_item_answered", {
      module: "practice",
      action: "complete",
      objectType: "variant",
      objectId: item.variant_id,
      result: correct ? "correct" : "incorrect",
    });

    var patch = {};
    patch["items[" + index + "].answered"] = true;
    patch["items[" + index + "].correct"] = correct;
    patch["items[" + index + "].chosenOk"] = choiceOk;
    var answeredCount = this.data.answeredCount + 1;
    patch.answeredCount = answeredCount;
    this.setData(patch);

    if (answeredCount >= this.data.total && this.data.total > 0) {
      this._finish();
    }
  },

  goReview: function () {
    this._navigateBack();
  },

  // 换个皮再练一遍 → 正向轻练；即时再练不冒充到期复测/销账。
  openRetest: function () {
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
        encodeURIComponent(this.data.packId) +
        "&mode=forward",
    });
  },

  _finish: function () {
    var verdict = gauntletViewModel.buildVerdict(this.data.items);
    this.setData({ verdict: verdict });
    // 闯关走完 → 清草稿(这一轮的半成品已兑现)
    _writeStorage(gauntletViewModel.draftStorageKey(this.data.packId), "");
    // 站完成信号(非 promoting, 只重排下一跳到期; 旗标关=服务端拒收, 静默)
    api.postStationCompleted(
      this.data.packId,
      this.data.title,
      "gauntlet_" + this.data.packId + "_" + Date.now(),
    ).catch(function () {});
    // 已登记完成埋点(与 retest 完成同一动作语义)
    telemetry.trackProductBehavior("learning_action_completed", {
      module: "practice",
      action: "complete",
      objectType: "retest",
      objectId: this.data.packId,
      result: verdict.hitCount + "/" + verdict.total,
    });
  },

  _saveDraft: function () {
    if (!this.data.packId) return;
    _writeStorage(
      gauntletViewModel.draftStorageKey(this.data.packId),
      gauntletViewModel.buildDraft(this.data.draftText, this.data.step),
    );
    this.setData({ draftSaved: !!this.data.draftText });
  },

  _navigateBack: function () {
    if (typeof wx === "undefined") return;
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (wx.redirectTo) {
      wx.redirectTo({
        url: "/packageDeeptutor/pages/luban/review/review",
        fail: function () {
          if (wx.reLaunch) {
            wx.reLaunch({ url: "/packageDeeptutor/pages/luban/review/review" });
          }
        },
      });
    }
  },

  // ②半写供给探测: signed R6 挖空 bank 有货则精确挖空, 404/失败保持自由默写降级
  _loadCloze: function () {
    var that = this;
    return api
      .getLubanCloze(this.data.packId, { silent: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var vm = gauntletViewModel.buildClozeViewModel(body);
        that.setData({ cloze: vm.available ? vm : null });
      })
      .catch(function () {
        that.setData({ cloze: null }); // fail-closed: 无供给不伪装挖空
      });
  },

  // 挖空逐句输入(改输入即作废该句旧自查结果, 不留陈旧对照)
  onClozeInput: function (event) {
    var dataset = (event && event.currentTarget && event.currentTarget.dataset) || {};
    var index = Number(dataset.index);
    var sentences = (this.data.cloze && this.data.cloze.sentences) || [];
    if (!(index >= 0 && index < sentences.length)) return;
    var value = (event && event.detail && event.detail.value) || "";
    var patch = {};
    patch["cloze.sentences[" + index + "].input"] = value;
    patch["cloze.sentences[" + index + "].checked"] = false;
    patch["cloze.sentences[" + index + "].hit"] = null;
    this.setData(patch);
  },

  // 「对照提示核对」: 呈现层确定性自查(gradeClozeBlank), 零学情/掌握写入
  checkCloze: function () {
    var cloze = this.data.cloze;
    if (!cloze || !cloze.sentences || !cloze.sentences.length) return;
    var sentences = cloze.sentences.map(function (s) {
      return Object.assign({}, s, {
        checked: true,
        hit: gauntletViewModel.gradeClozeBlank(s.hint, s.input),
      });
    });
    this.setData({ "cloze.sentences": sentences });
  },

  _loadItems: function () {
    var that = this;
    this._loadCloze();
    return api
      .getLubanRetestItems(this.data.packId, GAUNTLET_LIMIT)
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var vm = gauntletViewModel.buildGauntletViewModel(body);
        that.setData({
          items: vm.items,
          total: vm.total,
          pointCountLine: vm.pointCountLine,
          answeredCount: 0,
          verdict: null,
          fullAnswer: null,
          fullAnswerLoading: false,
          fullAnswerNote: "",
          loading: false,
          errorText: "",
        });
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(err, "闯关题面加载失败，请稍后重试"),
        });
      });
  },
});
