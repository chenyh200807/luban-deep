// pages/photo-answer/capture.js — 拍照作答：连拍多页 → 上传 → 触发 OCR
// 入口参数：question_id（必填）、stem（encodeURIComponent 后的题干，可选，用于题干折叠）
// 计划：docs/plan/鲁班移动端提分闭环/2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md

var api = require("../../utils/api");

var MAX_PAGES = 6;

Page({
  data: {
    questionId: "",
    questionStem: "",
    pages: [], // { tempPath, status: "ready"|"uploading"|"done"|"failed", qualityIssues: [] }
    submitting: false,
    errorText: "",
  },

  onLoad: function (options) {
    var stem = "";
    try {
      stem = decodeURIComponent(options.stem || "");
    } catch (e) {
      stem = String(options.stem || "");
    }
    this.setData({
      questionId: String(options.question_id || "").trim(),
      questionStem: stem,
    });
    if (!this.data.questionId) {
      this.setData({ errorText: "缺少题号，请从题目页进入拍照作答" });
    }
  },

  addPhotos: function () {
    var that = this;
    var remaining = MAX_PAGES - this.data.pages.length;
    if (remaining <= 0) {
      wx.showToast({ title: "最多 " + MAX_PAGES + " 页", icon: "none" });
      return;
    }
    wx.chooseMedia({
      count: remaining,
      mediaType: ["image"],
      sourceType: ["camera", "album"],
      sizeType: ["compressed"],
      camera: "back",
      success: function (res) {
        var added = (res.tempFiles || []).map(function (f) {
          return { tempPath: f.tempFilePath, status: "ready", qualityIssues: [] };
        });
        that.setData({ pages: that.data.pages.concat(added), errorText: "" });
      },
    });
  },

  removePage: function (e) {
    if (this.data.submitting) {
      return;
    }
    var index = Number(e.currentTarget.dataset.index);
    var pages = this.data.pages.slice();
    pages.splice(index, 1);
    this.setData({ pages: pages });
  },

  // 顺序上传 + 提交。失败页保留状态，可整体重试（同图重传由后端 content_hash 标重复）。
  submitAll: function () {
    var that = this;
    if (this.data.submitting || !this.data.questionId) {
      return;
    }
    if (!this.data.pages.length) {
      wx.showToast({ title: "请先拍摄答案", icon: "none" });
      return;
    }
    this.setData({ submitting: true, errorText: "" });

    var ensureSession = this.sessionId
      ? Promise.resolve({ session: { id: this.sessionId } })
      : api.createPhotoAnswerSession(this.data.questionId, this.data.questionStem);

    ensureSession
      .then(function (res) {
        that.sessionId = (res.session && res.session.id) || that.sessionId;
        if (!that.sessionId) {
          throw new Error("SESSION_CREATE_FAILED");
        }
        var chain = Promise.resolve();
        that.data.pages.forEach(function (page, index) {
          chain = chain.then(function () {
            if (page.status === "done") {
              return null;
            }
            that.setData({ ["pages[" + index + "].status"]: "uploading" });
            return api.uploadPhotoAnswerPage(that.sessionId, index, page.tempPath).then(
              function (uploaded) {
                var issues = (uploaded.quality && uploaded.quality.issues) || [];
                that.setData({
                  ["pages[" + index + "].status"]: "done",
                  ["pages[" + index + "].qualityIssues"]: issues,
                });
                if (issues.length) {
                  wx.showToast({
                    title: "第" + (index + 1) + "页" + that._qualityHint(issues) + "，建议重拍",
                    icon: "none",
                    duration: 2500,
                  });
                }
              },
              function (err) {
                that.setData({ ["pages[" + index + "].status"]: "failed" });
                throw err;
              }
            );
          });
        });
        return chain;
      })
      .then(function () {
        return api.submitPhotoAnswerSession(that.sessionId);
      })
      .then(function () {
        that.setData({ submitting: false });
        wx.navigateTo({
          url: "/pages/photo-answer/confirm?session_id=" + that.sessionId,
        });
      })
      .catch(function (err) {
        that.setData({
          submitting: false,
          errorText: (err && err.message) || "上传失败，请重试",
        });
      });
  },

  _qualityHint: function (issues) {
    if (issues.indexOf("too_dark") >= 0) return "偏暗";
    if (issues.indexOf("blurry") >= 0) return "可能模糊";
    if (issues.indexOf("low_resolution") >= 0) return "分辨率偏低";
    return "质量欠佳";
  },
});
