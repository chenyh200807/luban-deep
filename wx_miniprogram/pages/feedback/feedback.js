// pages/feedback/feedback.js — structured product feedback intake

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");

var PROBLEM_TYPES = [
  {
    key: "chat",
    mark: "对话",
    label: "对话答疑",
    desc: "回复、追问、流式输出",
    tag: "对话答疑",
  },
  {
    key: "learning_report",
    mark: "学情",
    label: "学情模块",
    desc: "今日处方、掌握趋势、证据",
    tag: "学情模块",
  },
  {
    key: "assessment",
    mark: "摸底",
    label: "摸底测试",
    desc: "出题、提交、结果生成",
    tag: "摸底测试",
  },
  {
    key: "diagnostic_report",
    mark: "报告",
    label: "摸底报告",
    desc: "诊断结论、错因、建议",
    tag: "摸底报告",
  },
  {
    key: "history",
    mark: "历史",
    label: "历史记录",
    desc: "记录丢失、打不开、同步",
    tag: "历史记录",
  },
  {
    key: "billing",
    mark: "会员",
    label: "权益充值",
    desc: "余额、充值、权益、订单",
    tag: "权益充值",
  },
  {
    key: "profile",
    mark: "我的",
    label: "我的/登录",
    desc: "登录、资料、设置、反馈",
    tag: "我的登录",
  },
  {
    key: "content",
    mark: "题目",
    label: "题目/答案",
    desc: "题干、解析、依据、答案",
    tag: "题目答案",
  },
];

var ISSUE_OPTIONS = {
  chat: [
    { key: "no_response", label: "没有回复" },
    { key: "stream_stuck", label: "回复卡住" },
    { key: "answer_quality", label: "答非所问" },
    { key: "format_broken", label: "排版错乱" },
    { key: "copy_failed", label: "复制失败" },
  ],
  learning_report: [
    { key: "data_wrong", label: "数据不对" },
    { key: "missing_evidence", label: "证据缺失" },
    { key: "prescription_wrong", label: "今日处方不准" },
    { key: "trend_wrong", label: "掌握趋势异常" },
    { key: "card_tap_failed", label: "卡片点不开" },
  ],
  assessment: [
    { key: "question_wrong", label: "题目不合适" },
    { key: "submit_failed", label: "提交失败" },
    { key: "result_missing", label: "结果没生成" },
    { key: "timer_problem", label: "计时异常" },
    { key: "page_stuck", label: "页面卡住" },
  ],
  diagnostic_report: [
    { key: "conclusion_wrong", label: "结论不准" },
    { key: "weakness_wrong", label: "薄弱点不准" },
    { key: "reason_unclear", label: "依据不清" },
    { key: "report_missing", label: "报告丢失" },
    { key: "layout_broken", label: "展示错乱" },
  ],
  history: [
    { key: "record_missing", label: "记录丢失" },
    { key: "record_open_failed", label: "打不开" },
    { key: "sync_delay", label: "同步延迟" },
    { key: "wrong_order", label: "顺序不对" },
    { key: "delete_failed", label: "删除失败" },
  ],
  billing: [
    { key: "balance_wrong", label: "余额不对" },
    { key: "pay_failed", label: "支付失败" },
    { key: "benefit_missing", label: "权益没到账" },
    { key: "order_missing", label: "订单缺失" },
    { key: "quota_wrong", label: "扣费异常" },
  ],
  profile: [
    { key: "login_failed", label: "登录异常" },
    { key: "profile_save_failed", label: "资料保存失败" },
    { key: "feedback_failed", label: "反馈提交失败" },
    { key: "navigation_wrong", label: "入口跳错" },
    { key: "avatar_failed", label: "头像失败" },
  ],
  content: [
    { key: "answer_wrong", label: "答案错误" },
    { key: "explanation_wrong", label: "解析错误" },
    { key: "source_unclear", label: "依据不清" },
    { key: "stem_wrong", label: "题干错误" },
    { key: "image_missing", label: "图片缺失" },
  ],
};

function findByKey(items, key) {
  return (items || []).find(function (item) {
    return item.key === key;
  });
}

function syncIssueOptions(moduleKey, selectedKeys) {
  var selectedMap = {};
  (selectedKeys || []).forEach(function (key) {
    selectedMap[key] = true;
  });
  return (ISSUE_OPTIONS[moduleKey] || ISSUE_OPTIONS.chat).map(function (item) {
    return Object.assign({}, item, { selected: !!selectedMap[item.key] });
  });
}

function getCurrentRoute() {
  try {
    var pages = getCurrentPages();
    var previous =
      pages && pages.length > 1 ? pages[pages.length - 2] : pages && pages[0];
    return (previous && previous.route) || "pages/feedback/feedback";
  } catch (_) {
    return "pages/feedback/feedback";
  }
}

function getDeviceInfo() {
  try {
    return wx.getSystemInfoSync ? wx.getSystemInfoSync() || {} : {};
  } catch (_) {
    return {};
  }
}

function normalizeAttachment(file, index) {
  return {
    id: "local-" + index,
    kind: file.fileType || file.type || "image",
    size: Number(file.size || 0),
    temp_path: file.tempFilePath || "",
  };
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    source: "profile",
    problemTypes: PROBLEM_TYPES,
    issueOptions: syncIssueOptions("chat", []),
    selectedProblemType: "chat",
    currentProblemLabel: "对话答疑",
    selectedIssueCount: 0,
    selectedSymptoms: [],
    comment: "",
    attachments: [],
    contextSnapshot: {
      route: "pages/feedback/feedback",
      network_type: "",
      device_model: "",
      platform: "",
      system: "",
    },
    submitting: false,
  },

  onLoad: function (query) {
    var win = helpers.getWindowInfo ? helpers.getWindowInfo() : {};
    var device = getDeviceInfo();
    var source =
      String((query && query.source) || "profile").trim() || "profile";
    var snapshot = {
      route: getCurrentRoute(),
      network_type: "",
      device_model: device.model || "",
      platform: device.platform || "",
      system: device.system || "",
      wechat_version: device.version || "",
    };
    this.setData({
      source: source,
      statusBarHeight: win.statusBarHeight || 0,
      navHeight: (win.statusBarHeight || 0) + 48,
      isDark: true,
      contextSnapshot: snapshot,
    });
    this._loadNetworkType();
  },

  _loadNetworkType: function () {
    var self = this;
    if (!wx.getNetworkType) return;
    wx.getNetworkType({
      success: function (res) {
        self.setData({
          contextSnapshot: Object.assign({}, self.data.contextSnapshot, {
            network_type: res.networkType || "",
          }),
        });
      },
    });
  },

  goBack: function () {
    wx.navigateBack();
  },

  onProblemTypeTap: function (e) {
    if (this.data.submitting) return;
    var key = e.currentTarget.dataset.key;
    var problem = findByKey(PROBLEM_TYPES, key);
    if (!problem) return;
    this.setData({
      selectedProblemType: key,
      currentProblemLabel: problem.label,
      selectedSymptoms: [],
      selectedIssueCount: 0,
      issueOptions: syncIssueOptions(key, []),
    });
  },

  onSymptomTap: function (e) {
    if (this.data.submitting) return;
    var key = e.currentTarget.dataset.key;
    if (!findByKey(this.data.issueOptions, key)) return;
    var selected = this.data.selectedSymptoms.slice();
    var idx = selected.indexOf(key);
    if (idx >= 0) {
      selected.splice(idx, 1);
    } else {
      selected.push(key);
    }
    this.setData({
      selectedSymptoms: selected,
      selectedIssueCount: selected.length,
      issueOptions: syncIssueOptions(this.data.selectedProblemType, selected),
    });
  },

  onFeedbackInput: function (e) {
    if (this.data.submitting) return;
    this.setData({ comment: e.detail.value || "" });
  },

  onChooseMedia: function () {
    if (this.data.submitting) return;
    var self = this;
    wx.chooseMedia({
      count: Math.max(1, 3 - this.data.attachments.length),
      mediaType: ["image", "video"],
      sourceType: ["album", "camera"],
      maxDuration: 30,
      success: function (res) {
        var offset = self.data.attachments.length;
        var incoming = (res.tempFiles || []).map(function (file, index) {
          return normalizeAttachment(file, offset + index);
        });
        var merged = self.data.attachments.concat(incoming).slice(0, 3);
        self.setData({ attachments: merged });
      },
      fail: function () {
        wx.showToast({ title: "未选择附件", icon: "none" });
      },
    });
  },

  onRemoveAttachment: function (e) {
    if (this.data.submitting) return;
    var idx = Number(e.currentTarget.dataset.index);
    var next = this.data.attachments.slice();
    if (idx >= 0) {
      next.splice(idx, 1);
      this.setData({ attachments: next });
    }
  },

  _buildPayload: function () {
    var problem =
      findByKey(PROBLEM_TYPES, this.data.selectedProblemType) ||
      PROBLEM_TYPES[0];
    var issueOptions = this.data.issueOptions || [];
    var symptomLabels = this.data.selectedSymptoms
      .map(function (key) {
        return findByKey(issueOptions, key);
      })
      .filter(Boolean)
      .map(function (item) {
        return item.label;
      });
    var source =
      this.data.source === "profile"
        ? "wx_miniprogram_profile_feedback"
        : "wx_miniprogram_feedback";
    return {
      rating: -1,
      reason_tags: [problem.tag].concat(symptomLabels),
      comment: String(this.data.comment || "").trim(),
      answer_mode: "AUTO",
      feedback_source: source,
      problem_type: problem.key,
      symptom_tags: this.data.selectedSymptoms.slice(),
      attachments: this.data.attachments.slice(),
      context_snapshot: Object.assign({}, this.data.contextSnapshot),
    };
  },

  _uploadAttachments: function (items) {
    var attachments = items || [];
    if (!attachments.length) return Promise.resolve([]);
    if (!api.uploadFeedbackAttachment) return Promise.resolve(attachments);
    var uploads = attachments.map(function (item) {
      return api.uploadFeedbackAttachment(item).then(function (stored) {
        return Object.assign({}, item, stored || {});
      });
    });
    return Promise.all(uploads);
  },

  onSubmitFeedback: function () {
    if (this.data.submitting) return;
    var payload = this._buildPayload();
    if (
      !payload.comment &&
      !payload.symptom_tags.length &&
      !payload.attachments.length
    ) {
      wx.showToast({ title: "请选择问题或补充说明", icon: "none" });
      return;
    }
    helpers.vibrate && helpers.vibrate("light");
    var self = this;
    this.setData({ submitting: true });
    this._uploadAttachments(payload.attachments)
      .then(function (attachments) {
        return api.submitFeedback(
          Object.assign({}, payload, { attachments: attachments }),
        );
      })
      .then(function () {
        wx.showToast({ title: "反馈已提交", icon: "success" });
        self.setData({ submitting: false });
        setTimeout(function () {
          wx.navigateBack({ delta: 1, fail: function () {} });
        }, 1500);
      })
      .catch(function () {
        wx.showToast({ title: "附件或反馈提交失败", icon: "none" });
        self.setData({ submitting: false });
      });
  },
});
