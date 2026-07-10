// 首跑剧本页（首次体验产品化）。
// 设计权威：docs/plan/鲁班移动端提分闭环/2026-07-10-luban-first-run-script-light-practice-plan.md §3。
// 红线：全静态供给零 LLM；逃生舱每幕可退直达 chat；聊天入口唯一 /api/v1/ws（本页零聊天请求）。
var data = require("./script-data");
var route = require("../../utils/route");
var telemetry = require("../../utils/surface-telemetry");
var subscribeMessage = require("../../utils/subscribe-message");

var DONE_KEY = require("../../utils/first-run-entry").DONE_KEY;

function behavior(action, extra) {
  var payload = { module: "first_run", action: action };
  if (extra && typeof extra === "object") {
    Object.keys(extra).forEach(function (k) {
      payload[k] = extra[k];
    });
  }
  return payload;
}

Page({
  data: {
    act: "war", // war | mode | question | feedback | interlude | reveal | report | finale
    progressSeg: 1, // 1..6
    warOpts: [],
    modeOpts: [],
    // question/feedback
    qIndex: 0,
    qTotal: data.QUESTIONS.length,
    q: null,
    fb: null,
    // interlude
    inter: null,
    interTitle: "",
    // reveal
    reveal: null,
    // report
    report: null,
    finale: { title: "开始对话吧", lead: "有任何题、任何概念，直接问。" },
  },

  war: null,
  mode: null,
  profile: {},
  results: [],
  qShownAt: 0,

  onLoad: function () {
    // 重置页级可变态：微信不为非 data 自定义属性做每实例克隆，
    // 从学情页再入本页时 this.results/profile 会残留上轮记录 → 报告分数翻倍。
    this.profile = {};
    this.results = [];
    this.setData({
      warOpts: this._optList(data.WAR_OPTS),
      modeOpts: this._optList(data.MODE_OPTS),
      materialOpts: this._optList(data.MATERIAL_OPTS),
    });
    telemetry.trackProductBehavior(
      "first_run_started",
      behavior("view", { section: "act_war" })
    );
  },

  _optList: function (obj) {
    return Object.keys(obj).map(function (k) {
      return { key: k, text: obj[k] };
    });
  },

  _go: function (act, seg) {
    this.setData({ act: act, progressSeg: seg });
    if (typeof wx !== "undefined" && wx.pageScrollTo) {
      wx.pageScrollTo({ scrollTop: 0, duration: 0 });
    }
    telemetry.trackProductBehavior(
      "module_viewed",
      behavior("view", { section: "act_" + act })
    );
  },

  /* ---------- 逃生舱 ---------- */
  onSkip: function () {
    var self = this;
    wx.showModal({
      title: "直接开始对话？",
      content: "剧本随时可以从「学情」页再进。",
      confirmText: "去对话",
      cancelText: "继续",
      success: function (res) {
        if (!res.confirm) return;
        telemetry.trackProductBehavior(
          "module_exited",
          behavior("dismiss", { section: "act_" + self.data.act })
        );
        self._finish("escape");
      },
    });
  },

  /* ---------- 摸底两问 ---------- */
  onWarPick: function (e) {
    this.war = e.currentTarget.dataset.key;
    this._go("mode", 1);
  },
  onModePick: function (e) {
    this.mode = e.currentTarget.dataset.key;
    this._go("material", 1);
  },

  /* ---------- 摸底第 3 问：资料年份 → 2026 改版时刻 ---------- */
  onMaterialPick: function (e) {
    var key = e.currentTarget.dataset.key;
    this.profile.material = key;
    var reveal = data.MATERIAL_REVEAL[key] || data.MATERIAL_REVEAL.unknown;
    this.setData({ materialReveal: reveal });
    this._go("materialReveal", 1);
  },
  onMaterialGo: function () {
    this._showQuestion(0);
  },

  /* ---------- 题集 ---------- */
  _showQuestion: function (i) {
    var q = data.QUESTIONS[i];
    this.qShownAt = Date.now();
    this.setData({
      qIndex: i,
      q: {
        slug: q.slug,
        name: q.name,
        family: q.family,
        src: q.src,
        cas: q.cas,
        stem: q.stem,
        hint: q.hint,
        opts: this._optList(q.opts),
      },
    });
    this._go("question", 2 + i);
  },

  onAnswer: function (e) {
    var picked = e.currentTarget.dataset.key;
    var i = this.data.qIndex;
    var q = data.QUESTIONS[i];
    var ok = picked === q.right;
    var secs = Math.max(1, Math.round((Date.now() - this.qShownAt) / 1000));
    this.results.push({ name: q.name, familyShort: q.familyShort, ok: ok, mn: q.mn.big, secs: secs });
    telemetry.trackProductBehavior(
      "first_run_question_completed",
      behavior("complete", {
        objectType: "question",
        objectId: q.slug,
        result: ok ? "correct" : "incorrect",
        durationMs: secs * 1000,
      })
    );
    // 逐项拆解顺序：你的选择 + 正解优先
    var order = [];
    if (!ok) order.push(picked);
    order.push(q.right);
    ["A", "B", "C", "D"].forEach(function (o) {
      if (order.indexOf(o) < 0) order.push(o);
    });
    var items = order.map(function (o) {
      return {
        key: o,
        text: q.opts[o],
        expl: q.expl[o],
        isRight: o === q.right,
        isMine: o === picked,
        isTrap: o === q.trap,
      };
    });
    var terms = q.lib.terms.map(function (t) {
      var isHit = t === q.lib.hitTerm;
      return {
        text: (isHit ? (ok ? "✓ " : "✗ ") : "") + t,
        state: isHit ? (ok ? "hit" : "miss") : "",
      };
    });
    this.setData({
      fb: {
        ok: ok,
        ringPct: ok ? 100 : 55,
        ringTx: ok ? "命中" : "差半步",
        title: ok ? q.vt.ok : q.vt.no,
        sub: ok ? q.vs.ok : q.vs.no,
        items: items,
        point: q.point,
        srcNote: q.srcNote,
        terms: terms,
        scale:
          "判分卡按 " + q.lib.year + " 官方参考答案编译 · 全题 " + q.lib.total +
          " 分 · 切成 " + q.lib.nPoints +
          " 条判分点 · 鲁班编译库已收录 174 个真题小问 / 1221 条判分点",
        mnBig: q.mn.big,
        mnSub: q.mn.sub,
        nextTx:
          i < data.QUESTIONS.length - 1
            ? "下一题（" + (i + 2) + "/" + data.QUESTIONS.length + "）→"
            : "生成我的学习报告 →",
      },
    });
    this._go("feedback", 2 + i);
  },

  onFeedbackNext: function () {
    this._showInterlude(this.data.qIndex);
  },

  /* ---------- 侧写间奏 ---------- */
  _showInterlude: function (i) {
    var it = data.INTERLUDES[i];
    var secs = this.results[i] ? this.results[i].secs : 10;
    this.setData({
      inter: { key: it.key, chip: it.chip, opts: this._optList(it.opts) },
      interTitle: it.title.replace("{secs}", String(secs)),
    });
    this._go("interlude", 2 + i);
  },

  onInterPick: function (e) {
    this.profile[this.data.inter.key] = e.currentTarget.dataset.key;
    var i = this.data.qIndex;
    if (i < data.QUESTIONS.length - 1) {
      this._showQuestion(i + 1);
    } else {
      this._buildReveal();
    }
  },

  /* ---------- 画像揭晓 ---------- */
  _buildReveal: function () {
    var c = data.CHAN[this.profile.chan || "B"];
    var s = data.STYLE[this.profile.style || "B"];
    var typeName = c.n + " · " + s.n;
    this.profile.typeName = typeName;
    this.setData({
      reveal: {
        typeName: typeName,
        desc: "你" + c.tag + "，做题" + s.tag + "——这不是标签，是接下来系统给你排课、出题、做复测的依据。",
        tags: [c.tag, s.tag, data.SLOT_TAG[this.profile.slot] || data.SLOT_TAG.D],
        rows: [
          { ic: "🧠", t: "记忆方式", s: c.teach },
          { ic: "🎯", t: "复测方式", s: s.teach },
          { ic: "⏰", t: "排课节奏", s: data.SLOT[this.profile.slot] || data.SLOT.D },
          { ic: "🔥", t: "坚持的燃料", s: data.DRIVE[this.profile.drive] || data.DRIVE.A },
        ],
      },
    });
    this._go("reveal", 6);
  },

  onRevealGo: function () {
    this._buildReport();
  },

  /* ---------- 学习报告 ---------- */
  _buildReport: function () {
    var results = this.results;
    var okN = results.filter(function (r) {
      return r.ok;
    }).length;
    var missN = results.length - okN;
    var pct = Math.round((okN / results.length) * 100);
    var rx =
      missN >= 2
        ? "先补「屋面防水 · 维修工艺」"
        : missN === 1
          ? "先复测错的那 1 题，再进新站"
          : "直接进「细部构造」拔高";
    var modeTexts = data.MODE_REPORT[this.mode] || data.MODE_REPORT.nopoint;
    var modeText = (missN ? modeTexts.miss : modeTexts.clean).replace("{missN}", String(missN));
    this.setData({
      report: {
        pct: pct,
        rx: rx,
        rxSub: "约 20 分钟 · " + results.length + " 条作答证据 · 明天复测薄弱点",
        ansN: results.length,
        missN: missN,
        modeTitle:
          (this.profile.typeName ? this.profile.typeName + " —— " : "") +
          (data.WAR_TX[this.war] || ""),
        modeText: modeText,
        basis:
          results.length + " 条作答 · " + missN + " 个错因命中 · " +
          results.length + " 个采分点比对鲁班编译库（174 个真题小问 / 1221 条判分点）· 6 个画像信号",
        rows: results.map(function (r) {
          return { name: r.name, family: r.familyShort, ok: r.ok, tag: r.ok ? "已命中" : "明天复测" };
        }),
        mns: results.map(function (r) {
          return r.mn;
        }),
      },
    });
    this._go("report", 6);
  },

  onReportGo: function () {
    telemetry.trackProductBehavior(
      "learning_action_completed",
      behavior("complete", { objectType: "script", result: "go_report" })
    );
    // 正式版：直接落在学情页
    this._finish("completed", "pages/report/report");
  },

  onReportRemind: function () {
    var self = this;
    telemetry.trackProductBehavior(
      "learning_action_completed",
      behavior("complete", { objectType: "script", result: "remind" })
    );
    subscribeMessage.requestNextDayRetestAuthorization().then(function (res) {
      telemetry.trackProductBehavior(
        "subscribe_prompt_result",
        behavior("complete", { objectType: "retest", result: res.status })
      );
      self.setData({
        finale: {
          title: "记下了，明天见",
          lead: "明天的换皮复测题已排好。\n报告存在「学情」tab——底部第三个。",
        },
      });
      self._go("finale", 6);
    });
  },

  onFinale: function () {
    this._finish("completed");
  },

  _finish: function (how, url) {
    try {
      wx.setStorageSync(DONE_KEY, { at: Date.now(), how: how });
    } catch (e) {}
    // packageDeeptutor 无 tabBar，统一走 route reLaunch
    wx.reLaunch({ url: route.resolve(url || "pages/chat/chat") });
  },
});
