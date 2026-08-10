// 过线体检(S5)· 屏 2 测评页(纯点选,连续作答不打断;中场检查点已按 owner 2026-08-07 拍板下线)
// - create_assessment(assessment_type="pass_readiness");
// - 可见进度 + 案例微进度(「案例 2/3」);
// - 本地草稿 + 服务端 resume, 冲突服务端赢;
// - 提交走既有 submit_assessment(dict[str,str] 字母 wire)。
var api = require("../../../../utils/api");
var auth = require("../../../../utils/auth");
var helpers = require("../../../../utils/helpers");
var route = require("../../../../utils/route");
var surfaceTelemetry = require("../../../../utils/surface-telemetry");
var passVm = require("../../../../utils/pass-readiness-view-model");

var DEVICE_ID_KEY = "deeptutor.assessment.deviceId";

function trackBehavior(eventName, payload) {
  if (surfaceTelemetry && typeof surfaceTelemetry.trackProductBehavior === "function") {
    surfaceTelemetry.trackProductBehavior(eventName, payload);
  }
}

function getDeviceId() {
  var fallback =
    "wx_assessment_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
  try {
    var stored = String(wx.getStorageSync(DEVICE_ID_KEY) || "").trim();
    if (stored) return stored.slice(0, 128);
    wx.setStorageSync(DEVICE_ID_KEY, fallback);
  } catch (err) {
    return fallback;
  }
  return fallback;
}

function readDraft() {
  var draft = auth.readOwnerStorage ? auth.readOwnerStorage(passVm.DRAFT_STORAGE_KEY) : null;
  return draft && typeof draft === "object" ? draft : null;
}

function writeDraft(draft) {
  if (auth.writeOwnerStorage) auth.writeOwnerStorage(passVm.DRAFT_STORAGE_KEY, draft);
}

function clearDraft() {
  if (auth.writeOwnerStorage) auth.writeOwnerStorage(passVm.DRAFT_STORAGE_KEY, null);
}

Page({
  data: {
    isDark: false,
    statusBarHeight: 44,
    navHeight: 96,
    stage: "loading", // loading | quiz | submitting | error
    errorText: "",
    questions: [],
    currentIndex: 0,
    currentQ: null,
    selMap: {},
    selectedKeys: {},
    answerSheet: [],
    answeredCount: 0,
    unansweredCount: 0,
    totalCount: 0,
    scoredCount: 0,
    profileCount: 0,
  },

  _session: null,
  _quizId: "",
  _startTime: 0,
  _submitted: false,

  onLoad: function (options) {
    var info = helpers.getWindowInfo();
    this.setData({
      isDark: helpers.isDarkOr("light"),
      statusBarHeight: info.statusBarHeight || 44,
      navHeight: (info.statusBarHeight || 44) + 44,
    });
    this._entrySource = String((options && options.entry_source) || "").trim();
    this._deviceId = getDeviceId();
    this._bootstrap();
  },

  onShow: function () {
    surfaceTelemetry.trackModuleView(this, { module: "pass_readiness", section: "exam" });
    this.setData({ isDark: helpers.isDarkOr("light") });
  },

  onHide: function () {
    this._persistDraft();
    surfaceTelemetry.trackModuleExit(
      this,
      this.data.stage === "quiz" && !this._submitted
        ? { objectType: "pass_readiness_diagnostic", objectId: this._quizId || "", result: "incomplete" }
        : null,
    );
  },

  onUnload: function () {
    this._persistDraft();
    surfaceTelemetry.trackModuleExit(this);
  },

  // ── 启动: 先尝试服务端 resume(冲突服务端赢), 再新建 ─────────
  _bootstrap: function () {
    var self = this;
    var draft = readDraft();
    if (draft && draft.quizId) {
      api
        .getAssessmentSession(draft.quizId, self._deviceId)
        .then(function (resp) {
          var session = passVm.normalizeSession(resp);
          if (!session.questions.length || !session.quizId) {
            throw new Error("resume_empty");
          }
          self._applySession(session, draft);
        })
        .catch(function () {
          clearDraft();
          self._createSession();
        });
      return;
    }
    this._createSession();
  },

  _createSession: function () {
    var self = this;
    self.setData({ stage: "loading", errorText: "" });
    api
      .createAssessment({
        assessment_type: "pass_readiness",
        device_id: self._deviceId,
      })
      .then(function (resp) {
        var session = passVm.normalizeSession(resp);
        if (!session.questions.length || !session.quizId) {
          self.setData({ stage: "error", errorText: "暂无可用题目，请稍后重试" });
          return;
        }
        // 专名漏斗: 新会话真正开卷才算 started(resume 不重复计)
        trackBehavior("pass_readiness_started", {
          module: "pass_readiness",
          section: "exam",
          action: "start",
          objectType: "pass_readiness_diagnostic",
          objectId: session.quizId,
        });
        self._applySession(session, null);
      })
      .catch(function (err) {
        trackBehavior("event_error", {
          module: "pass_readiness",
          action: "error",
          objectType: "pass_readiness_diagnostic",
          result: "fail",
          errorCode: String((err && err.message) || "create_failed").slice(0, 60),
        });
        var msg = api.describeRequestError
          ? api.describeRequestError(err, "加载题目失败，请稍后重试", { context: "assessment_create" })
          : "加载题目失败，请稍后重试";
        self.setData({ stage: "error", errorText: msg });
      });
  },

  _applySession: function (session, draft) {
    // 冲突服务端赢: 本地草稿先铺底, 服务端草稿快照逐题覆盖
    var selectedKeys = passVm.mergeResumeAnswers(
      session.serverAnswers,
      draft ? draft.selectedKeys : null,
    );
    var currentIndex = draft
      ? Math.min(Math.max(0, draft.currentIndex || 0), session.questions.length - 1)
      : 0;
    this._session = session;
    this._quizId = session.quizId;
    this._startTime = Date.now();
    var selMap = {};
    Object.keys(selectedKeys).forEach(function (qId) {
      String(selectedKeys[qId]).split("").forEach(function (key) {
        selMap[qId + "_" + key] = true;
      });
    });
    var answerState = passVm.buildAnswerState(session.questions, selectedKeys, currentIndex);
    this.setData({
      stage: "quiz",
      questions: session.questions,
      currentIndex: currentIndex,
      currentQ: session.questions[currentIndex],
      selMap: selMap,
      selectedKeys: selectedKeys,
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
      totalCount: session.questions.length,
      scoredCount: session.scoredCount,
      profileCount: session.profileCount,
    });
  },

  _persistDraft: function () {
    if (!this._quizId || this._submitted) return;
    writeDraft(
      passVm.buildDraft(
        this._quizId,
        this.data.selectedKeys,
        this.data.currentIndex,
      ),
    );
  },

  // ── 作答(纯点选) ────────────────────────────────────────────
  onSelectOption: function (e) {
    helpers.vibrate("light");
    var key = e.currentTarget.dataset.key;
    var q = this.data.currentQ;
    if (!q) return;
    var qId = q.id;
    var isMulti = q.question_type === "multi_choice";
    var opts = q.options || [];
    var nextMap = Object.assign({}, this.data.selMap);
    if (isMulti) {
      nextMap[qId + "_" + key] = !nextMap[qId + "_" + key];
    } else {
      for (var i = 0; i < opts.length; i++) nextMap[qId + "_" + opts[i].key] = false;
      nextMap[qId + "_" + key] = true;
    }
    var answerStr = "";
    for (var j = 0; j < opts.length; j++) {
      if (nextMap[qId + "_" + opts[j].key]) answerStr += opts[j].key;
    }
    var newKeys = Object.assign({}, this.data.selectedKeys);
    newKeys[qId] = answerStr;
    var answerState = passVm.buildAnswerState(this.data.questions, newKeys, this.data.currentIndex);
    this.setData({
      selMap: nextMap,
      selectedKeys: newKeys,
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
    });
    this._persistDraft();

    var self = this;
    // 单选自动跳下一题(与既有测评页一致)
    if (!isMulti && this.data.currentIndex < this.data.questions.length - 1) {
      setTimeout(function () {
        self.onNext();
      }, 300);
    }
  },

  // ── 导航 ────────────────────────────────────────────────────
  _jumpTo: function (idx) {
    if (idx < 0 || idx >= this.data.questions.length) return;
    var answerState = passVm.buildAnswerState(this.data.questions, this.data.selectedKeys, idx);
    this.setData({
      currentIndex: idx,
      currentQ: this.data.questions[idx],
      answerSheet: answerState.answerSheet,
      answeredCount: answerState.answeredCount,
      unansweredCount: answerState.unansweredCount,
    });
    this._persistDraft();
  },

  onPrev: function () {
    this._jumpTo(this.data.currentIndex - 1);
  },

  onNext: function () {
    this._jumpTo(this.data.currentIndex + 1);
  },

  onJumpQuestion: function (e) {
    var idx = Number(e.currentTarget.dataset.index);
    if (!isNaN(idx)) this._jumpTo(idx);
  },

  onRetry: function () {
    this._createSession();
  },

  // ── 提交 ────────────────────────────────────────────────────
  onSubmit: function () {
    if (this.data.stage === "submitting") return;
    var self = this;
    var total = self.data.questions.length;
    var answered = self.data.answeredCount;
    if (answered < total) {
      wx.showModal({
        title: "还有未答题目",
        content:
          "还有 " + (total - answered) + " 题未答，已完成 " + answered + "/" + total + " 题，确定提交吗？",
        confirmText: "提交",
        success: function (res) {
          if (res.confirm) self._doSubmit();
        },
      });
      return;
    }
    self._doSubmit();
  },

  _doSubmit: function () {
    var self = this;
    helpers.vibrate("medium");
    self.setData({ stage: "submitting" });
    var timeSpent = Math.round((Date.now() - self._startTime) / 1000);
    var answers = passVm.buildSubmitAnswers(self.data.selectedKeys);
    api
      .submitAssessment(self._quizId, answers, timeSpent, self._deviceId)
      .then(function (resp) {
        var report = (resp && (resp.data || resp)) || {};
        self._submitted = true;
        clearDraft();
        trackBehavior("pass_readiness_completed", {
          module: "pass_readiness",
          section: "exam",
          action: "complete",
          objectType: "pass_readiness_diagnostic",
          objectId: self._quizId || "",
          durationMs: timeSpent * 1000,
          result: "success",
        });
        if (auth.writeOwnerStorage) {
          auth.writeOwnerStorage(passVm.REPORT_STORAGE_KEY, {
            quizId: self._quizId,
            report: report,
            savedAt: Date.now(),
          });
        }
        wx.redirectTo({
          url: route.lubanPassReadinessReport({ quiz_id: self._quizId }),
        });
      })
      .catch(function (err) {
        trackBehavior("event_error", {
          module: "pass_readiness",
          action: "error",
          objectType: "pass_readiness_diagnostic",
          objectId: self._quizId || "",
          result: "fail",
          errorCode: String((err && err.message) || "submit_failed").slice(0, 60),
        });
        wx.showToast({ title: "提交失败，请重试", icon: "none" });
        self.setData({ stage: "quiz" });
      });
  },

  goBack: function () {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.lubanPassReadiness() });
      },
    });
  },
});
