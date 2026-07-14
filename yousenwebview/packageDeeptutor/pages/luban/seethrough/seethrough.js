// 鲁班 · F16 防水「5天留存闭环」原生体验(spike 雏形)
// 只投影已签发看穿内容(GET /api/v1/luban/seethrough/F16),前端一字不新造。
// 每天 7 步同构:今日一刀 → 表皮试探(4选1本地判) → 这题的门道(透视揭底4段) →
//   给你的一句话(暖纠正) → 明日换皮约定 → 证据入账(light signal, 非 promoting)。
// Day4 = 半写 + 对照已签发 P10/P11 采分点文本自我核对(诚实标注非官方,不走内核实判)。
// Day5 = 三处换皮综合复测 + 进步收据 + 安全网。
//
// 红线:掌握前端不自算(仅本地判对错+呈现,不写掌握);错因只投影签发 error_code(E系);
//   薄 program-progress(第几天/已完成天,本地呈现层非学情真值);学员端文案禁审视硬词。
const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const telemetry = require("../../../utils/surface-telemetry");

var PACK_ID = "F16";
var PROGRESS_KEY = "luban_seethrough_progress:" + PACK_ID; // 本地呈现层进度(非掌握真值)

// 步骤机(MCQ 天与半写天分支);学员端标签守暖基调,避开审视硬词
var STEP = {
  CUT: "cut",           // 今日一刀
  PROBE: "probe",       // 表皮试探(4选1)
  WRITE: "write",       // Day4 半写输入
  SELFCHECK: "selfcheck", // Day4 对照采分点自我核对
  INSIGHT: "insight",   // 透视揭底(呈现名:这题的门道)
  WARM: "warm",         // 暖纠正(呈现名:给你的一句话)
  PROMISE: "promise",   // 明日换皮约定
};

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    loading: true,
    errorText: "",
    title: "",
    days: [],            // 签发投影的 5 天
    dayIndex: 0,
    step: STEP.CUT,
    completedDays: [],   // 已完成天(本地呈现层)
    // 当前天答题态
    picked: "",          // 选中的 option_id
    answered: false,
    correct: false,
    pickedDistractor: null, // 选错时命中的诊断干扰项(误解+error_code)
    // Day4 半写
    draft: "",
    selfCheck: null,     // {points:[{label,hit,required_terms,error_code}], hitCount, total}
    isLast: false,
  },

  onLoad(query) {
    var info = typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48 });
    telemetry.trackProductBehavior("module_viewed", {
      module: "learning", action: "view", objectType: "station", objectId: PACK_ID,
    });
    this._restoreProgress();
    this._load();
  },

  _restoreProgress() {
    var done = [];
    var raw = auth.readOwnerStorage ? auth.readOwnerStorage(PROGRESS_KEY) : null;
    if (raw && Array.isArray(raw.completedDays)) done = raw.completedDays;
    this.setData({ completedDays: done });
  },

  _persistProgress(completedDays) {
    // 本地呈现层进度(第几天/已完成天),非掌握真值——掌握等复测读回,前端不自算。
    if (auth.writeOwnerStorage) {
      auth.writeOwnerStorage(PROGRESS_KEY, {
        completedDays: completedDays,
        at: Date.now(),
      });
    }
  },

  _load() {
    var that = this;
    return api.getLubanSeethrough(PACK_ID, { silent: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var days = Array.isArray(body.days) ? body.days : [];
        if (!days.length) {
          that.setData({ loading: false, errorText: "内容即将开通" });
          return;
        }
        // 选项呈现序确定性洗牌(红队修复: bank 原序 correct_option_id 全在 A 位,
        // "闭眼点第一个"=100%)。只动呈现序, 判定仍按 option_id 零语义改动;
        // 同 day 幂等。根治(bank 生产随机化位置+判分收服务端)归内容/架构工单。
        days = days.map(function (d) {
          var opts = Array.isArray(d.options) ? d.options.slice() : null;
          if (!opts || opts.length < 2) return d;
          var scoreOf = function (o) {
            var k = "st:" + d.day + ":" + String(o.option_id);
            var s = 0;
            for (var j = 0; j < k.length; j++) {
              s = (s * 131 + k.charCodeAt(j)) >>> 0;
              // xor-shift 雪崩: 线性散列对"仅末字符不同"单调(A<B<C<D 排完不动),
              // 每步混洗破坏单调性
              s ^= s >>> 13;
              s = (s * 2654435761) >>> 0;
            }
            return (s ^ (s >>> 16)) >>> 0;
          };
          opts.sort(function (a, b) { return scoreOf(a) - scoreOf(b); });
          return Object.assign({}, d, { options: opts });
        });
        // 起始关 = 首个未完成关(呈现层); 关卡递进解锁见 _isUnlocked
        var firstIncomplete = 0;
        for (var i = 0; i < days.length; i++) {
          if (that.data.completedDays.indexOf(days[i].day) < 0) { firstIncomplete = i; break; }
        }
        that.setData({
          title: String(body.title || "防水 · 5天留存"),
          days: days,
          dayIndex: firstIncomplete,
          loading: false,
          errorText: "",
        });
        that._enterDay(firstIncomplete);
      })
      .catch(function (err) {
        that.setData({ loading: false, errorText: api.describeRequestError(err, "加载失败,请稍后重试") });
      });
  },

  _curDay() { return this.data.days[this.data.dayIndex] || {}; },

  _enterDay(idx) {
    var day = this.data.days[idx] || {};
    var isWrite = String(day.answer_mode || "mcq") === "semi_write";
    this.setData({
      dayIndex: idx,
      step: STEP.CUT,
      picked: "", answered: false, correct: false, pickedDistractor: null,
      draft: "", selfCheck: null,
      isLast: idx >= this.data.days.length - 1,
    });
    telemetry.trackProductBehavior("learning_action_started", {
      module: "learning", action: "start_training",
      objectType: "station", objectId: PACK_ID + ":D" + (day.day || idx + 1),
    });
  },

  // 今日一刀「开始」→ 表皮试探(或 Day4 半写)
  goProbe() {
    var day = this._curDay();
    this.setData({ step: String(day.answer_mode || "mcq") === "semi_write" ? STEP.WRITE : STEP.PROBE });
  },

  // 4选1 本地判(选择==correct_option_id);选错时取该干扰项的诊断映射(误解+error_code)
  onOptionTap(e) {
    if (this.data.answered) return;
    var ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
    var oid = String(ds.oid || "");
    var day = this._curDay();
    var correct = oid === String(day.correct_option_id || "");
    var pickedDistractor = null;
    if (!correct) {
      var list = day.distractors || [];
      for (var i = 0; i < list.length; i++) {
        if (String(list[i].option_id) === oid) { pickedDistractor = list[i]; break; }
      }
    }
    this.setData({ picked: oid, answered: true, correct: correct, pickedDistractor: pickedDistractor });
    telemetry.trackProductBehavior("retest_item_answered", {
      module: "practice", action: "complete", objectType: "variant",
      objectId: String(day.variant_id || (PACK_ID + "-D" + day.day)),
      result: correct ? "correct" : "incorrect", practiceMode: "forward",
    });
  },

  // 答后 → 这题的门道(透视揭底 4 段)
  goInsight() { this.setData({ step: STEP.INSIGHT }); },
  // → 给你的一句话(暖纠正)
  goWarm() { this.setData({ step: STEP.WARM }); },
  // → 明日换皮约定 + 证据入账
  goPromise() {
    this.setData({ step: STEP.PROMISE });
    this._recordDayEvidence();
  },

  // Day4 半写输入
  onDraftInput(e) { this.setData({ draft: (e && e.detail && e.detail.value) || "" }); },

  // Day4 对照已签发 P10/P11 采分点文本自我核对(确定性命中/漏点;非内核实判,诚实标注)
  goSelfCheck() {
    var day = this._curDay();
    var answer = String(this.data.draft || "");
    var points = (day.scoring_points || []).map(function (sp) {
      var terms = sp.required_terms || [];
      // 命中 = 作答文本包含该采分点全部关键词(确定性,非评分)
      var hit = terms.length > 0 && terms.every(function (t) { return answer.indexOf(String(t)) >= 0; });
      return { point_id: sp.point_id, label: sp.label, error_code: sp.error_code, hit: hit, required_terms: terms };
    });
    var hitCount = points.filter(function (p) { return p.hit; }).length;
    this.setData({ step: STEP.SELFCHECK, selfCheck: { points: points, hitCount: hitCount, total: points.length } });
    telemetry.trackProductBehavior("learning_action_completed", {
      module: "practice", action: "complete", objectType: "full_answer",
      objectId: PACK_ID + ":D" + day.day, result: hitCount + "/" + points.length, practiceMode: "forward",
    });
  },

  // 每天证据入账:light signal(非 promoting)+ 完成天推进(本地呈现层);
  // Day5(末天)额外发 station_completed → 复测读回(既有单一 sink,非 promoting)。
  _recordDayEvidence() {
    var day = this._curDay();
    var completed = this.data.completedDays.slice();
    if (completed.indexOf(day.day) < 0) completed.push(day.day);
    this.setData({ completedDays: completed });
    this._persistProgress(completed);
    telemetry.trackProductBehavior("learning_action_completed", {
      module: "learning", action: "complete", objectType: "seethrough_day",
      objectId: PACK_ID + ":D" + day.day, result: "done", practiceMode: "forward",
    });
    if (this.data.isLast) {
      // 复测读回:F16 站完成信号(非 promoting;旗标关=服务端拒收静默,不阻断)
      try {
        api.postStationCompleted(
          PACK_ID,
          this.data.title || "",
          "seethrough_" + PACK_ID + "_" + Date.now(),
        ).catch(function () {});
      } catch (_e) {}
    }
  },

  // 明日换皮约定「进入明天」→ 下一天(或末天完成)
  goNextDay() {
    var next = this.data.dayIndex + 1;
    if (next >= this.data.days.length) {
      // 末天:回到起点总览(雏形可重走)
      this.setData({ step: STEP.PROMISE });
      if (typeof wx !== "undefined" && wx.showToast) wx.showToast({ title: "5关全通!", icon: "success" });
      return;
    }
    this._enterDay(next);
  },

  // 关卡导航(owner 2026-07-11 拍板: 弃日隐喻改 5 关连闯, binge 友好)。
  // 递进解锁: 已完成的关 + 第一个未完成关可进, 之后的锁定——
  // 审阅期"自由跳"脚手架就此移除(它曾泄漏成产品体验, 账本有案)。
  onDayTap(e) {
    var ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
    var idx = Number(ds.idx);
    if (!Number.isFinite(idx) || idx < 0 || idx >= this.data.days.length) return;
    if (!this._isUnlocked(idx)) {
      if (typeof wx !== "undefined" && wx.showToast) {
        wx.showToast({ title: "先闯完上一关", icon: "none" });
      }
      return;
    }
    this._enterDay(idx);
  },

  // 解锁判定: 该关已完成, 或它之前的所有关都已完成(=下一待闯关)
  _isUnlocked(idx) {
    var days = this.data.days || [];
    var done = this.data.completedDays || [];
    if (done.indexOf((days[idx] || {}).day) >= 0) return true;
    for (var i = 0; i < idx; i++) {
      if (done.indexOf((days[i] || {}).day) < 0) return false;
    }
    return true;
  },

  goBack() {
    if (typeof wx !== "undefined" && wx.navigateBack) wx.navigateBack();
  },
});
