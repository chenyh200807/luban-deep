// pages/photo-answer/confirm.js — 识别确认页：疑点高亮 / 题干折叠 / 轻量修改 / 主动重识别
// 设计纪律（plan §5/§7）：系统只建议不替换；题干默认折叠不删除；关键疑点未解决
// 时后端 fail-closed 为 provisional 批改（不写学情）。

var api = require("../../utils/api");

var POLL_INTERVAL_MS = 1500;
var POLL_MAX_TRIES = 60; // 90 秒兜底

Page({
  data: {
    sessionId: "",
    status: "processing", // processing | awaiting_confirm | failed | confirmed
    jobVersion: 1,
    draftText: "",
    originalDraft: "",
    paragraphs: [], // { text, is_stem_suspect, included }
    suspicions: [], // { id, source, severity, suggestion, resolvedLocal }
    unresolvedCount: 0,
    criticalCount: 0,
    escalateUsed: false,
    confirming: false,
    failText: "",
  },

  onLoad: function (options) {
    this._destroyed = false;
    this.setData({ sessionId: String(options.session_id || "") });
    this._pollTries = 0;
    this._poll();
  },

  onUnload: function () {
    this._destroyed = true;
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
    }
  },

  _poll: function () {
    var that = this;
    if (that._destroyed || !this.data.sessionId) {
      return;
    }
    api.getPhotoAnswerSession(this.data.sessionId).then(
      function (res) {
        if (that._destroyed) return;
        var status = (res.session && res.session.status) || "processing";
        if (status === "awaiting_confirm" && res.view) {
          that._applyView(res);
          return;
        }
        if (status === "failed") {
          that.setData({
            status: "failed",
            failText: "识别失败，可重试或改用手动输入",
          });
          return;
        }
        that._pollTries += 1;
        if (that._pollTries >= POLL_MAX_TRIES) {
          that.setData({ status: "failed", failText: "识别超时，请重试" });
          return;
        }
        that._pollTimer = setTimeout(that._poll.bind(that), POLL_INTERVAL_MS);
      },
      function () {
        if (that._destroyed) return;
        that._pollTries += 1;
        that._pollTimer = setTimeout(
          that._poll.bind(that),
          POLL_INTERVAL_MS * 2,
        );
      },
    );
  },

  _applyView: function (res) {
    var view = res.view || {};
    var paragraphs = (view.paragraphs || []).map(function (p) {
      return {
        text: p.text,
        is_stem_suspect: !!p.is_stem_suspect,
        included: !p.is_stem_suspect, // 题干默认不计入但保留，可一键恢复
      };
    });
    var suspicions = (view.suspicions || []).map(function (s) {
      return {
        id: s.id,
        source: s.source,
        severity: s.severity,
        page_index: Number(s.page_index) || 0,
        suggestion: s.suggestion || "",
        spanText: this._spanText(s),
        resolvedLocal: !!s.resolved_by_user,
      };
    }, this);
    this.setData(
      {
        status: "awaiting_confirm",
        jobVersion: (res.job && res.job.job_version) || 1,
        paragraphs: paragraphs,
        suspicions: suspicions,
      },
      this._rebuildDraft.bind(this),
    );
  },

  _spanText: function (s) {
    try {
      var span =
        typeof s.span_json === "string"
          ? JSON.parse(s.span_json)
          : s.span_json || {};
      return span.char || span.text || "";
    } catch (e) {
      return "";
    }
  },

  _rebuildDraft: function () {
    var draft = this.data.paragraphs
      .filter(function (p) {
        return p.included;
      })
      .map(function (p) {
        return p.text;
      })
      .join("\n");
    var unresolved = this.data.suspicions.filter(function (s) {
      return !s.resolvedLocal;
    });
    this.setData({
      draftText: draft,
      originalDraft: draft,
      unresolvedCount: unresolved.length,
      criticalCount: unresolved.filter(function (s) {
        return s.severity === "critical";
      }).length,
    });
  },

  onDraftInput: function (e) {
    this.setData({ draftText: e.detail.value });
  },

  toggleParagraph: function (e) {
    var index = Number(e.currentTarget.dataset.index);
    var that = this;
    var apply = function () {
      that.setData(
        {
          ["paragraphs[" + index + "].included"]:
            !that.data.paragraphs[index].included,
        },
        that._rebuildDraft.bind(that),
      );
    };
    if (this.data.draftText !== this.data.originalDraft) {
      wx.showModal({
        title: "恢复段落会重建文本",
        content: "你已手动修改过文本，恢复/折叠段落将覆盖手动修改。继续？",
        success: function (res) {
          if (res.confirm) apply();
        },
      });
      return;
    }
    apply();
  },

  resolveSuspicion: function (e) {
    var index = Number(e.currentTarget.dataset.index);
    var item = this.data.suspicions[index];
    this.setData(
      { ["suspicions[" + index + "].resolvedLocal"]: !item.resolvedLocal },
      this._recountSuspicions.bind(this),
    );
  },

  _recountSuspicions: function () {
    var unresolved = this.data.suspicions.filter(function (s) {
      return !s.resolvedLocal;
    });
    this.setData({
      unresolvedCount: unresolved.length,
      criticalCount: unresolved.filter(function (s) {
        return s.severity === "critical";
      }).length,
    });
  },

  // 选择升级目标页：取"最高严重度未解决疑点"所在页。
  // 严重度只有 critical / normal 两档：优先 critical，否则取任一未解决 normal，
  // 都没有再回落第 0 页。这样多页 session 不会永远只升级第 0 页。
  _escalatePageIndex: function () {
    var unresolved = this.data.suspicions.filter(function (s) {
      return !s.resolvedLocal;
    });
    var critical = unresolved.filter(function (s) {
      return s.severity === "critical";
    });
    var pick = critical[0] || unresolved[0];
    return pick ? Number(pick.page_index) || 0 : 0;
  },

  // 主动升级重识别：每次拍题仅 1 次，花的是最贵引擎（plan §3.3 硬顶通道）
  escalate: function () {
    var that = this;
    if (this.data.escalateUsed) {
      return;
    }
    var pageIndex = this._escalatePageIndex();
    wx.showModal({
      title: "重新识别",
      content: "将使用更高精度引擎重新识别（每次拍题仅可用一次）。继续？",
      success: function (res) {
        if (!res.confirm) return;
        wx.showLoading({ title: "重新识别中" });
        api
          .retryPhotoAnswerSession(that.data.sessionId, {
            mode: "escalate",
            page_index: pageIndex,
          })
          .then(
            function () {
              wx.hideLoading();
              if (that._destroyed) return;
              that.setData({ escalateUsed: true });
              that._pollTries = 0;
              api
                .getPhotoAnswerSession(that.data.sessionId)
                .then(function (res2) {
                  if (that._destroyed) return;
                  if (res2.view) that._applyView(res2);
                });
            },
            function (err) {
              wx.hideLoading();
              if (that._destroyed) return;
              that.setData({ escalateUsed: true });
              wx.showToast({
                title: (err && err.message) || "重识别不可用",
                icon: "none",
              });
            },
          );
      },
    });
  },

  rerun: function () {
    var that = this;
    wx.showLoading({ title: "重新提交中" });
    api.retryPhotoAnswerSession(this.data.sessionId, { mode: "rerun" }).then(
      function () {
        wx.hideLoading();
        that.setData({ status: "processing", failText: "" });
        that._pollTries = 0;
        that._poll();
      },
      function (err) {
        wx.hideLoading();
        wx.showToast({
          title: (err && err.message) || "重试失败",
          icon: "none",
        });
      },
    );
  },

  confirm: function (e) {
    this._doConfirm(false);
  },

  _doConfirm: function (ack) {
    var that = this;
    if (this.data.confirming) {
      return;
    }
    var text = String(this.data.draftText || "").trim();
    if (!text) {
      wx.showToast({ title: "确认稿不能为空", icon: "none" });
      return;
    }
    this.setData({ confirming: true });
    var resolvedIds = this.data.suspicions
      .filter(function (s) {
        return s.resolvedLocal;
      })
      .map(function (s) {
        return s.id;
      });
    api
      .confirmPhotoAnswerSession(this.data.sessionId, {
        confirmed_text: text,
        job_version: this.data.jobVersion,
        ack_normal_suspicions: !!ack,
        resolved_span_ids: resolvedIds,
        edited_char_count: Math.abs(
          text.length - this.data.originalDraft.length,
        ),
      })
      .then(function (res) {
        that.setData({ confirming: false });
        if (res.status === "needs_review_ack") {
          wx.showModal({
            title: "还有疑点未确认",
            content:
              "有 " +
              res.unresolved_normal +
              " 处识别疑点未逐一确认。直接提交可能影响批改准确性，确定提交？",
            confirmText: "确定提交",
            success: function (modal) {
              if (modal.confirm) {
                that._doConfirm(true);
              }
            },
          });
          return;
        }
        that._onConfirmed(res);
      })
      .catch(function (err) {
        that.setData({ confirming: false });
        wx.showToast({
          title: (err && err.message) || "确认失败",
          icon: "none",
        });
      });
  },

  _onConfirmed: function (res) {
    var payload = res.grader_payload || {};
    var app = getApp();
    if (app && app.globalData) {
      app.globalData.photoAnswerPayload = payload; // 既有提交链路从这里取 confirmed_text
    }
    var channel = this.getOpenerEventChannel && this.getOpenerEventChannel();
    if (channel && channel.emit) {
      channel.emit("photoAnswerConfirmed", payload);
    }
    var provisional = payload.grading_tier === "provisional";
    var that = this;
    wx.showModal({
      title: provisional ? "已确认（临时批改）" : "已确认",
      content: provisional
        ? "存在未解决的关键疑点（数字/工期类）或页面质量不佳，本次批改结果将标记为临时，不计入学情。"
        : "确认稿已生成，将送入批改。",
      showCancel: false,
      success: function () {
        wx.navigateBack({ delta: 2 });
      },
    });
  },
});
