// 首跑剧本页（首次体验产品化）。
// 设计权威：docs/plan/鲁班移动端提分闭环/2026-07-10-luban-first-run-script-light-practice-plan.md §3。
// 红线：全静态供给零 LLM；正式判定/处方只来自服务端 signed manifest + Learner State。
var data = require("./script-data");
var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var telemetry = require("../../utils/surface-telemetry");
var subscribeMessage = require("../../utils/subscribe-message");
var firstRunEntry = require("../../utils/first-run-entry");

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
    statusBarHeight: 44,
    navHeight: 92,
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
    syncStatus: "idle", // idle | syncing | synced | pending | blocked
    syncMessage: "",
    finale: { title: "今天的起点已经记下", lead: "回到学习首页，继续今天的任务。" },
  },

  war: null,
  mode: null,
  profile: {},
  results: [],
  qShownAt: 0,
  completionId: "",
  userId: "",
  _syncInFlight: false,
  _answerLocked: false,

  onLoad: function () {
    // 重置页级可变态：微信不为非 data 自定义属性做每实例克隆，
    // 从学情页再入本页时 this.results/profile 会残留上轮记录 → 报告分数翻倍。
    this.profile = {};
    this.results = [];
    this.completionId = "";
    this._answerLocked = false;
    this.userId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    var windowInfo = {};
    try {
      windowInfo = helpers.getWindowInfo ? helpers.getWindowInfo() : {};
    } catch (_e) {}
    this.setData({
      statusBarHeight: Number(windowInfo.statusBarHeight || 44),
      navHeight: Number(windowInfo.statusBarHeight || 44) + 48,
      warOpts: this._optList(data.WAR_OPTS),
      modeOpts: this._optList(data.MODE_OPTS),
      materialOpts: this._optList(data.MATERIAL_OPTS),
    });
    this._restoreCheckpoint();
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

  _checkpointPayload: function () {
    return {
      scriptVersion: data.SCRIPT_VERSION,
      act: this.data.act,
      qIndex: this.data.qIndex,
      war: this.war,
      mode: this.mode,
      profile: this.profile,
      results: this.results,
      completionId: this.completionId,
    };
  },

  _saveCheckpoint: function () {
    if (!this.userId || this.data.syncStatus === "synced") return;
    firstRunEntry.writeCheckpoint(this.userId, this._checkpointPayload());
  },

  _restoreCheckpoint: function () {
    if (!this.userId) return;
    var saved = firstRunEntry.readCheckpoint(this.userId);
    if (!saved) return;
    if (saved.scriptVersion !== data.SCRIPT_VERSION) {
      firstRunEntry.clearCheckpoint(this.userId);
      return;
    }
    this.war = saved.war || null;
    this.mode = saved.mode || null;
    this.profile = saved.profile || {};
    this.results = Array.isArray(saved.results) ? saved.results.slice() : [];
    this.completionId = String(saved.completionId || "");
    var act = String(saved.act || "war");
    var qIndex = Math.max(0, Math.min(Number(saved.qIndex || 0), data.QUESTIONS.length - 1));
    if (act === "question") {
      this._showQuestion(qIndex, true);
      return;
    }
    if (act === "feedback" && this.results[qIndex]) {
      this.setData({ qIndex: qIndex });
      var previous = this.results.pop();
      this._answerQuestion(previous.picked, previous.durationMs, true);
      return;
    }
    if (act === "interlude") {
      this.setData({ qIndex: qIndex });
      this._showInterlude(qIndex, true);
      return;
    }
    if (act === "materialReveal" && this.profile.material) {
      this.setData({ materialReveal: data.MATERIAL_REVEAL[this.profile.material] || data.MATERIAL_REVEAL.unknown });
    }
    if (act === "report" && this.results.length === data.QUESTIONS.length) {
      this._buildReport();
      return;
    }
    if (act === "reveal" && this.results.length === data.QUESTIONS.length) {
      this._buildReveal();
      return;
    }
    this._go(act, act === "war" || act === "mode" || act === "material" || act === "materialReveal" ? 1 : 6);
  },

  /* ---------- 逃生舱 ---------- */
  onSkip: function () {
    var self = this;
    wx.showModal({
      title: "稍后继续？",
      content: "进度会保存在这台设备，回到「学习」首页可以接着做。",
      confirmText: "回学习",
      cancelText: "继续",
      success: function (res) {
        if (!res.confirm) return;
        telemetry.trackProductBehavior(
          "module_exited",
          behavior("dismiss", { section: "act_" + self.data.act })
        );
        self._saveCheckpoint();
        self._finish();
      },
    });
  },

  /* ---------- 摸底两问 ---------- */
  onWarPick: function (e) {
    this.war = e.currentTarget.dataset.key;
    this._go("mode", 1);
    this._saveCheckpoint();
  },
  onModePick: function (e) {
    this.mode = e.currentTarget.dataset.key;
    this._go("material", 1);
    this._saveCheckpoint();
  },

  /* ---------- 摸底第 3 问：资料年份 → 2026 改版时刻 ---------- */
  onMaterialPick: function (e) {
    var key = e.currentTarget.dataset.key;
    this.profile.material = key;
    var reveal = data.MATERIAL_REVEAL[key] || data.MATERIAL_REVEAL.unknown;
    this.setData({ materialReveal: reveal });
    this._go("materialReveal", 1);
    this._saveCheckpoint();
  },
  onMaterialGo: function () {
    this._showQuestion(0);
  },

  /* ---------- 题集 ---------- */
  _showQuestion: function (i, restoring) {
    var q = data.QUESTIONS[i];
    this.qShownAt = Date.now();
    this._answerLocked = false;
    this.setData({
      qIndex: i,
      q: {
        slug: q.slug,
        questionId: q.questionId,
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
    if (!restoring) this._saveCheckpoint();
  },

  onAnswer: function (e) {
    if (this._answerLocked) return;
    this._answerLocked = true;
    this._answerQuestion(e.currentTarget.dataset.key, 0, false);
  },

  _answerQuestion: function (picked, durationOverrideMs, restoring) {
    var i = this.data.qIndex;
    var q = data.QUESTIONS[i];
    var ok = picked === q.right;
    var durationMs = Number(durationOverrideMs) || Math.max(1000, Date.now() - this.qShownAt);
    var secs = Math.max(1, Math.round(durationMs / 1000));
    this.results.push({
      questionId: q.questionId,
      name: q.name,
      familyShort: q.familyShort,
      picked: picked,
      ok: ok,
      mn: q.mn.big,
      secs: secs,
      durationMs: durationMs,
    });
    if (!restoring) {
      telemetry.trackProductBehavior(
        "first_run_question_completed",
        behavior("complete", {
          objectType: "question",
          objectId: q.questionId,
          result: ok ? "correct" : "incorrect",
          durationMs: durationMs,
        })
      );
    }
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
    this._saveCheckpoint();
  },

  onFeedbackNext: function () {
    this._showInterlude(this.data.qIndex);
  },

  /* ---------- 侧写间奏 ---------- */
  _showInterlude: function (i, restoring) {
    var it = data.INTERLUDES[i];
    var secs = this.results[i] ? this.results[i].secs : 10;
    this.setData({
      inter: { key: it.key, chip: it.chip, opts: this._optList(it.opts) },
      interTitle: it.title.replace("{secs}", String(secs)),
    });
    this._go("interlude", 2 + i);
    if (!restoring) this._saveCheckpoint();
  },

  onInterPick: function (e) {
    this.profile[this.data.inter.key] = e.currentTarget.dataset.key;
    var i = this.data.qIndex;
    if (i < data.QUESTIONS.length - 1) {
      this._showQuestion(i + 1);
    } else {
      this._buildReveal();
    }
    this._saveCheckpoint();
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
        desc: "你" + c.tag + "，做题" + s.tag + "——这是今天的起点画像，之后每次真实作答都会继续修正它。",
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
    var modeTexts = data.MODE_REPORT[this.mode] || data.MODE_REPORT.nopoint;
    var modeText = (missN ? modeTexts.miss : modeTexts.clean).replace("{missN}", String(missN));
    this.setData({
      report: {
        pct: pct,
        rx: "正在根据作答生成今天任务",
        rxSub: results.length + " 条作答证据 · 保存后回到「学习」继续",
        ansN: results.length,
        missN: missN,
        modeTitle:
          (this.profile.typeName ? this.profile.typeName + " —— " : "") +
          (data.WAR_TX[this.war] || ""),
        modeText: modeText,
        basis:
          results.length + " 条作答 · " + missN + " 题暂未命中 · " +
          results.length + " 个采分点比对鲁班编译库（174 个真题小问 / 1221 条判分点）· 6 个画像信号",
        rows: results.map(function (r) {
          return { name: r.name, family: r.familyShort, ok: r.ok, tag: r.ok ? "已命中" : "明天复测" };
        }),
        mns: results.map(function (r) {
          return r.mn;
        }),
      },
      syncStatus: "syncing",
      syncMessage: "报告已生成，正在保存到你的学情",
    });
    this._go("report", 6);
    var payload = this._buildCompletionPayload();
    this._saveCheckpoint();
    this._syncCompletion(payload);
  },

  _ensureCompletionId: function () {
    if (!this.completionId) {
      this.completionId =
        "first-run-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
    }
    return this.completionId;
  },

  _declaredPreferences: function () {
    return {
      exam_stage: String(this.war || ""),
      answer_style: String(this.mode || ""),
      material_version: String(this.profile.material || ""),
      memory_channel: String(this.profile.chan || ""),
      study_slot: String(this.profile.slot || ""),
      motivation: String(this.profile.drive || ""),
    };
  },

  _buildCompletionPayload: function () {
    return {
      completion_id: this._ensureCompletionId(),
      script_version: data.SCRIPT_VERSION,
      completed_at: new Date().toISOString(),
      answers: this.results.map(function (item) {
        return {
          question_id: item.questionId,
          selected_key: item.picked,
          duration_ms: Number(item.durationMs || item.secs * 1000 || 0),
        };
      }),
      declared_preferences: this._declaredPreferences(),
    };
  },

  _syncCompletion: function (payload) {
    if (this._syncInFlight || !this.userId) return Promise.resolve(null);
    var self = this;
    this._syncInFlight = true;
    firstRunEntry.savePendingSync(this.userId, payload);
    this.setData({ syncStatus: "syncing", syncMessage: "报告已生成，正在保存到你的学情" });
    return api
      .completeFirstRun(payload, { silent: true })
      .then(function (result) {
        firstRunEntry.clearPendingSync(self.userId);
        firstRunEntry.clearCheckpoint(self.userId);
        firstRunEntry.markDone(self.userId, payload);
        var projection = (result && result.home_projection) || {};
        var focus = projection.today_focus || {};
        var report = Object.assign({}, self.data.report || {}, {
          rx: String(focus.title || "今天任务已生成"),
          rxSub: "学情已保存 · 回到「学习」继续今天的任务",
        });
        self.setData({
          report: report,
          syncStatus: "synced",
          syncMessage: "已保存到学情，第二天回来会接着这条路线",
        });
        return result;
      })
      .catch(function (error) {
        var errorCode = api.errorCodeOf(error);
        var blocked =
          errorCode === "first_run_content_not_signed" ||
          errorCode === "first_run_version_conflict";
        self.setData({
          syncStatus: blocked ? "blocked" : "pending",
          syncMessage: blocked
            ? "报告已生成，内容校验完成后会继续保存"
            : "报告已生成，网络恢复后会自动保存学情",
        });
        return null;
      })
      .then(function (result) {
        self._syncInFlight = false;
        return result;
      });
  },

  onReportGo: function () {
    telemetry.trackProductBehavior(
      "learning_action_completed",
      behavior("complete", { objectType: "script", result: "go_report" })
    );
    this._finish();
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
          lead: "明天的换皮复测题已排好。\n先回「学习」首页，今天的任务已经接上。",
        },
      });
      self._go("finale", 6);
    });
  },

  onFinale: function () {
    this._finish();
  },

  _finish: function () {
    wx.reLaunch({ url: route.resolve("pages/learn/learn") });
  },
});
