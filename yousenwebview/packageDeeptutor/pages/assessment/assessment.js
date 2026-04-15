// pages/assessment/assessment.js — 摸底测试

var api = require("../../utils/api");
var route = require("../../utils/route");

var LEVEL_NAMES = {
  beginner: "入门",
  intermediate: "中级",
  advanced: "进阶",
  expert: "精通",
};

var ARCHETYPE_ICONS = {
  strategist: "S",
  explorer: "E",
  sprinter: "F",
  builder: "B",
};
var ARCHETYPE_COLORS = {
  strategist: "#3b82f6",
  explorer: "#8b5cf6",
  sprinter: "#f59e0b",
  builder: "#22c55e",
};
var RESPONSE_LABELS = {
  fluent: "流畅型",
  deliberate: "审慎型",
  impulsive: "冲动型",
  struggling: "困难型",
};
var RESPONSE_DESCS = {
  fluent: "你答题速度快且准确率高，知识掌握扎实，能快速调取记忆。",
  deliberate:
    "你倾向深思熟虑后作答，虽然速度较慢但准确率很高，属于稳扎稳打型。",
  impulsive: "你答题速度较快但容易出错，建议放慢节奏，仔细审题后再选择。",
  struggling: "部分知识点掌握不够牢固，建议从基础章节开始系统复习。",
};
var CALIBRATION_LABELS = {
  overconfident: "偏乐观",
  accurate: "很准确",
  underconfident: "偏保守",
};

// 客户端 fallback 画像数据
var ARCHETYPE_NAMES = {
  strategist: "策略型学员",
  explorer: "探索型学员",
  sprinter: "冲刺型学员",
  builder: "基础型学员",
};
var ARCHETYPE_DESCS = {
  strategist:
    "你注重效率与结果，善于规划学习路径，习惯用数据驱动决策。面对考试，你会优先攻克高权重考点，用最少的时间获取最大的分数收益。",
  explorer:
    "你拥有强烈的求知欲，喜欢深入理解知识背后的逻辑和原理。你不满足于死记硬背，而是追求真正的融会贯通。",
  sprinter:
    "你目标明确、执行力强，擅长在压力下高效产出。你喜欢集中火力攻克重点，在冲刺阶段爆发力惊人。",
  builder:
    "你做事扎实稳健，喜欢循序渐进地构建知识体系。你相信万丈高楼平地起，基础打牢了后面的学习自然水到渠成。",
};
var ARCHETYPE_TRAITS = {
  strategist: ["目标导向", "高效执行", "数据驱动", "善于规划"],
  explorer: ["求知欲强", "深度学习", "融会贯通", "知识整合"],
  sprinter: ["执行力强", "重点突破", "抗压力好", "目标明确"],
  builder: ["扎实稳健", "循序渐进", "基础牢固", "持之以恒"],
};
var ARCHETYPE_TIPS = {
  strategist:
    "建议按考试权重分配精力，优先攻克高频考点。利用错题数据精准定位薄弱环节，避免低效重复。",
  explorer:
    "建议均衡覆盖各章节，重点关注知识点之间的联系。用思维导图串联知识体系，让零散知识形成网络。",
  sprinter:
    "建议聚焦高权重章节和历年高频考点，通过大量刷题建立题感。考前一个月进入模拟考试密集训练。",
  builder:
    "建议从基础章节开始，确保每个概念理解透彻后再进入下一个。用工地实际场景帮助记忆，让知识落地。",
};

var helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    stage: "welcome", // welcome | quiz | loading | result
    questions: [],
    currentIndex: 0,
    currentQ: null,
    selMap: {}, // { "qId_A": true, "qId_C": true } — WXML 渲染用
    selectedKeys: {}, // { qId: "A" or "AC" } — 提交用
    resultScore: 0,
    resultLevel: "beginner",
    resultLevelName: "入门",
    chapterList: [],
    // 学员画像
    archetype: "",
    archetypeName: "",
    archetypeDesc: "",
    archetypeTraits: [],
    archetypeTip: "",
    archetypeColor: "",
    archetypeIcon: "",
    // 认知画像
    responseLabel: "",
    responseDesc: "",
    calibrationLabel: "",
    // 错误模式
    errorPattern: "",
    errorPatternName: "",
    // 行动计划
    priorityChapters: [],
    planStrategy: "",
  },

  _quizId: null,
  _startTime: 0,

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
      isDark: helpers.isDark(),
      enableOrbs: helpers.getAnimConfig().enableBreathingOrbs,
    });
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
  },

  // ── 开始测试 ──────────────────────────────────
  onStart: function () {
    if (this.data.starting) return;
    var self = this;
    helpers.vibrate("medium");
    self.setData({ stage: "loading", starting: true });

    api
      .createAssessment("diagnostic", 20)
      .then(function (resp) {
        // 兼容两种返回格式: {questions, quiz_id} 或 {data: {questions, quiz_id}}
        var payload = resp.data || resp;
        var questions = payload.questions || [];
        if (!questions.length) {
          wx.showToast({ title: "暂无题目", icon: "none" });
          self.setData({ stage: "welcome", starting: false });
          return;
        }
        // 标准化字段名
        questions = questions.map(function (q) {
          var opts = q.options || [];
          // 数组格式 [{key, value}] → [{key, text}]
          if (Array.isArray(opts)) {
            opts = opts.map(function (o) {
              return { key: o.key, text: o.value || o.text || "" };
            });
          } else {
            // 对象格式 {A: "text"} → [{key, text}]
            opts = Object.keys(opts)
              .sort()
              .map(function (k) {
                return { key: k, text: opts[k] };
              });
          }
          return {
            id: q.question_id || q.id,
            question_stem:
              q.text || q.question_stem || q.stem || q.content || "",
            options: opts,
            question_type: q.question_type || "single_choice",
            difficulty: q.difficulty || "",
          };
        });
        self._quizId = payload.quiz_id;
        self._startTime = Date.now();
        self.setData({
          stage: "quiz",
          starting: false,
          questions: questions,
          currentIndex: 0,
          currentQ: questions[0],
          selMap: {},
          selectedKeys: {},
        });
      })
      .catch(function (e) {
        // 创建失败已通过 toast 展示
        wx.showToast({ title: "加载题目失败", icon: "none" });
        self.setData({ stage: "welcome", starting: false });
      });
  },

  // ── 选择选项 ──────────────────────────────────
  onSelectOption: function (e) {
    helpers.vibrate("light");
    var key = e.currentTarget.dataset.key;
    var q = this.data.currentQ;
    var qId = q.id;
    var isMulti = q.question_type === "multi_choice";
    var mapKey = qId + "_" + key;

    // 构建新的 selMap（WXML 渲染用）
    var newMap = {};
    var oldMap = this.data.selMap;
    var k;
    for (k in oldMap) {
      if (oldMap.hasOwnProperty(k)) newMap[k] = oldMap[k];
    }

    if (isMulti) {
      // 多选：toggle 当前 key
      newMap[mapKey] = !newMap[mapKey];
    } else {
      // 单选：先清除该题所有选项，再选中当前
      var opts = q.options || [];
      for (var i = 0; i < opts.length; i++) {
        newMap[qId + "_" + opts[i].key] = false;
      }
      newMap[mapKey] = true;
    }

    // 同步生成 selectedKeys（提交用）
    var opts2 = q.options || [];
    var answerStr = "";
    for (var j = 0; j < opts2.length; j++) {
      if (newMap[qId + "_" + opts2[j].key]) answerStr += opts2[j].key;
    }
    var newKeys = {};
    var oldKeys = this.data.selectedKeys;
    for (k in oldKeys) {
      if (oldKeys.hasOwnProperty(k)) newKeys[k] = oldKeys[k];
    }
    newKeys[qId] = answerStr;

    this.setData({ selMap: newMap, selectedKeys: newKeys });

    // 单选自动跳下一题 (300ms 延迟)
    if (
      q.question_type !== "multi_choice" &&
      this.data.currentIndex < this.data.questions.length - 1
    ) {
      var self = this;
      setTimeout(function () {
        self.onNext();
      }, 300);
    }
  },

  // ── 导航 ──────────────────────────────────────
  onPrev: function () {
    if (this.data.currentIndex <= 0) return;
    var idx = this.data.currentIndex - 1;
    this.setData({ currentIndex: idx, currentQ: this.data.questions[idx] });
  },

  onNext: function () {
    if (this.data.currentIndex >= this.data.questions.length - 1) return;
    var idx = this.data.currentIndex + 1;
    this.setData({ currentIndex: idx, currentQ: this.data.questions[idx] });
  },

  // ── 提交 ──────────────────────────────────────
  onSubmit: function () {
    if (this.data.submitting) return;
    var self = this;
    var answers = self.data.selectedKeys;
    var total = self.data.questions.length;
    var answered = Object.keys(answers).filter(function (k) {
      return answers[k];
    }).length;

    if (answered < total) {
      wx.showModal({
        title: "还有未答题目",
        content: "你已完成 " + answered + "/" + total + " 题，确定提交吗？",
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
    self.setData({ stage: "loading", submitting: true });

    var timeSpent = Math.round((Date.now() - self._startTime) / 1000);
    var answers = {};
    var keys = self.data.selectedKeys;
    Object.keys(keys).forEach(function (qId) {
      if (keys[qId]) answers[qId] = keys[qId];
    });

    api
      .submitAssessment(self._quizId, answers, timeSpent)
      .then(function (resp) {
        var data = resp.data || resp;
        // 响应已收到
        var fb = data.diagnostic_feedback || data.feedback || {};
        var ao = fb.ability_overview || {};
        var ci = fb.cognitive_insight || {};
        var lp = fb.learner_profile || {};
        var ap = fb.action_plan || {};
        var diag = data.diagnostic || data.diagnostic_profile || {};

        var score = ao.score_pct || data.score || 0;
        var level = data.suggested_level || data.level || "beginner";

        // 章节掌握度
        var mastery = ao.chapter_mastery || data.chapter_mastery || {};
        var chapterList = Object.keys(mastery)
          .map(function (ch) {
            var v = mastery[ch];
            var name = typeof v === "object" ? v.name || ch : ch;
            var pct =
              typeof v === "object"
                ? Math.round(v.mastery || v.pct || 0)
                : Math.round(v * 100);
            return { name: name, pct: pct };
          })
          .sort(function (a, b) {
            return b.pct - a.pct;
          });

        // ── 客户端 fallback 画像生成 ──────────────
        var archetype = lp.archetype || diag.learner_archetype || "";
        var archetypeName = lp.archetype_name || "";
        var archetypeDesc = lp.description || "";
        var archetypeTraits = lp.traits || [];
        var archetypeTip = lp.study_tip || "";
        var rp = ci.response_profile || diag.response_profile || "";
        var cal = ci.calibration_label || diag.calibration_label || "";
        var ep = ao.error_pattern || diag.error_pattern || "";

        // 如果后端没返回画像，根据分数和答题时间本地生成
        if (!archetype) {
          var avgTime = timeSpent / self.data.questions.length;
          if (score >= 70) {
            archetype = avgTime < 20 ? "strategist" : "explorer";
          } else if (score >= 40) {
            archetype = avgTime < 25 ? "sprinter" : "builder";
          } else {
            archetype = avgTime < 20 ? "sprinter" : "builder";
          }
        }
        if (!archetypeName)
          archetypeName = ARCHETYPE_NAMES[archetype] || archetype;
        if (!archetypeDesc) archetypeDesc = ARCHETYPE_DESCS[archetype] || "";
        if (!archetypeTraits.length)
          archetypeTraits = ARCHETYPE_TRAITS[archetype] || [];
        if (!archetypeTip) archetypeTip = ARCHETYPE_TIPS[archetype] || "";

        // 认知风格 fallback
        if (!rp) {
          var avgT = timeSpent / self.data.questions.length;
          var correct = Object.keys(answers).length > 0 ? score / 100 : 0;
          if (correct >= 0.6 && avgT < 25) rp = "fluent";
          else if (correct >= 0.6) rp = "deliberate";
          else if (avgT < 20) rp = "impulsive";
          else rp = "struggling";
        }

        // 错误模式 fallback
        if (!ep)
          ep =
            score >= 60
              ? "slip_dominant"
              : score >= 30
                ? "mixed"
                : "gap_dominant";
        var epNames = {
          slip_dominant: "粗心型",
          gap_dominant: "知识盲区型",
          confusion_dominant: "概念混淆型",
          mixed: "综合型",
        };

        // 优先攻克：掌握度最低的 5 个章节
        var priority = (ap.priority_chapters || []).map(function (c) {
          return typeof c === "object" ? c.name || c.code || "" : c;
        });
        if (!priority.length && chapterList.length) {
          priority = chapterList
            .slice()
            .sort(function (a, b) {
              return a.pct - b.pct;
            })
            .slice(0, 5)
            .map(function (c) {
              return c.name;
            });
        }

        self.setData({
          stage: "result",
          submitting: false,
          resultScore: score,
          resultLevel: level,
          resultLevelName: LEVEL_NAMES[level] || level,
          chapterList: chapterList,
          archetype: archetype,
          archetypeName: archetypeName,
          archetypeDesc: archetypeDesc,
          archetypeTraits: archetypeTraits,
          archetypeTip: archetypeTip,
          archetypeColor: ARCHETYPE_COLORS[archetype] || "#3b82f6",
          archetypeIcon: ARCHETYPE_ICONS[archetype] || "?",
          responseLabel: RESPONSE_LABELS[rp] || rp,
          responseDesc: RESPONSE_DESCS[rp] || "",
          calibrationLabel: CALIBRATION_LABELS[cal] || cal || "",
          errorPattern: ep,
          errorPatternName: epNames[ep] || ep,
          priorityChapters: priority.slice(0, 5),
          planStrategy: ap.plan_strategy || "",
        });

        wx.setStorageSync("diagnostic_completed", true);
        helpers.vibrate("heavy");
      })
      .catch(function (e) {
        // 提交失败已通过 toast 展示
        wx.showToast({ title: "提交失败，请重试", icon: "none" });
        self.setData({ stage: "quiz", submitting: false });
      });
  },

  // ── 操作 ──────────────────────────────────────
  onRetake: function () {
    this.setData({
      stage: "welcome",
      questions: [],
      selMap: {},
      selectedKeys: {},
      currentIndex: 0,
    });
  },

  goChat: function () {
    wx.reLaunch({ url: route.chat() });
  },

  goBack: function () {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.chat() });
      },
    });
  },
});
