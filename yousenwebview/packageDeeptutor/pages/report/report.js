// pages/report/report.js — 学情页：诊断 + AI作战方案 + 进步反馈

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");
const flags = require("../../utils/flags");

const RADAR_SELF_SUBJECT = "self";
const LEVEL_NAMES = {
  beginner: "入门",
  intermediate: "中级",
  advanced: "进阶",
  expert: "精通",
};
const CHAPTER_CODE_LABELS = {
  "1A411": "建筑设计与构造",
  "1A412": "结构设计与建筑材料",
  "1A413": "装配式建筑",
  "1A414": "建筑工程材料",
  "1A415": "建筑工程施工技术",
  "1A421": "项目组织管理",
  "1A422": "施工进度管理",
  "1A423": "施工质量管理",
  "1A424": "施工安全管理",
  "1A425": "合同与招投标管理",
  "1A426": "施工成本管理",
  "1A427": "资源与现场管理",
  "1A431": "建筑工程法规",
  "1A432": "建筑工程技术标准",
};

function _displayLevelName(value) {
  var key = String(value || "").trim();
  return LEVEL_NAMES[key] || key || "";
}

function _displayChapterName(value) {
  var text = String(value || "").trim();
  if (/^1A\d{6}$/i.test(text)) {
    return CHAPTER_CODE_LABELS[text.slice(0, 5).toUpperCase()] || "综合能力";
  }
  return text || "综合能力";
}

function _buildRadarSignature(dims) {
  return (dims || [])
    .map(function (d) {
      var name = String(d && d.name ? d.name : "").trim();
      var value = Math.round((Number(d && d.value) || 0) * 1000);
      return name + ":" + value;
    })
    .join("|");
}

function _buildRadarDimensionsFromAssessment(data) {
  var profile = data || {};
  var chapterMastery = profile.chapter_mastery || {};
  return Object.keys(chapterMastery).map(function (key) {
    var item = chapterMastery[key];
    var mastery = Number(typeof item === "object" ? item.mastery : item) || 0;
    return {
      name: _displayChapterName((typeof item === "object" ? item.name : key) || key),
      value: mastery / 100,
    };
  });
}

function _hasPositiveRadarSignal(dims) {
  return (dims || []).some(function (item) {
    return Number(item && item.value) > 0;
  });
}

function _normalizeRadarDimensions(radarData) {
  return ((radarData && radarData.dimensions) || []).map(function (item) {
    var score = Number(item.score);
    var value =
      typeof item.value === "number"
        ? item.value
        : Number.isFinite(score)
        ? score / 100
        : 0;
    return {
      name: _displayChapterName(item.label || item.name || item.key || ""),
      value: value || 0,
    };
  });
}

function _buildRadarViewModel(dims) {
  var strong = 0;
  var normal = 0;
  var weak = 0;
  (dims || []).forEach(function (d) {
    var pct = Math.round((d.value || 0) * 100);
    if (pct >= 70) strong++;
    else if (pct >= 40) normal++;
    else weak++;
  });
  var avg = Math.round(
    ((dims || []).reduce(function (sum, d) {
      return sum + (d.value || 0);
    }, 0) /
      Math.max((dims || []).length, 1)) *
      100,
  );
  var dimList = (dims || [])
    .slice()
    .sort(function (a, b) {
      return (a.value || 0) - (b.value || 0);
    })
    .map(function (d, index) {
      var pct = Math.round((d.value || 0) * 100);
      return {
        rank: index + 1,
        name: d.name,
        pct: pct,
        cls: pct >= 70 ? "strong" : pct >= 40 ? "normal" : "weak",
        color: pct >= 70 ? "#34d399" : pct >= 40 ? "#fbbf24" : "#f87171",
      };
    });
  return {
    strongCount: strong,
    normalCount: normal,
    weakCount: weak,
    avgScore: avg,
    dimList: dimList,
  };
}

function _pickPrimaryTopic(groups, hotspots, dimList, focusHint) {
  var candidates = [];
  (hotspots || []).forEach(function (item) {
    if (item && item.name) candidates.push(item.name);
  });
  (groups || []).forEach(function (group) {
    (group && group.chapters ? group.chapters : []).forEach(function (chapter) {
      if (chapter && chapter.name) candidates.push(chapter.name);
    });
  });
  (dimList || []).forEach(function (item) {
    if (item && item.name) candidates.push(item.name);
  });

  if (focusHint) {
    var matched = candidates.find(function (name) {
      return focusHint.indexOf(name) >= 0;
    });
    if (matched) return matched;
  }

  var weakGroup = (groups || []).find(function (group) {
    return group && group.name === "需要加强" && Array.isArray(group.chapters) && group.chapters.length;
  });
  if (weakGroup && weakGroup.chapters[0] && weakGroup.chapters[0].name) {
    return weakGroup.chapters[0].name;
  }
  if (hotspots && hotspots[0] && hotspots[0].name) {
    return hotspots[0].name;
  }
  if (dimList && dimList[0] && dimList[0].name) {
    return dimList[0].name;
  }
  return "";
}

function _buildBattlePlanModel(input) {
  var data = input || {};
  var topic = _pickPrimaryTopic(data.masteryGroups, data.hotspots, data.dimList, data.focusHint);
  var dueToday = Number(data.dueTodayCount) || 0;
  var totalDue = Number((data.reviewSummary || {}).total_due) || 0;
  var overdueCount = Number((data.reviewSummary || {}).overdue_count) || 0;
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var remainingTarget = Math.max(dailyTarget - todayDone, 0);
  var questionCount = Math.max(Math.min(remainingTarget || 5, 5), 3);
  var priorityTask = "";
  var studyMethod = "";
  var timeBudget = "";
  var coachNote = "";

  if (totalDue > 0 && topic) {
    priorityTask = "先清理 " + Math.min(totalDue, 3) + " 个待复习点，再围绕“" + topic + "”做 " + questionCount + " 题巩固";
  } else if (topic) {
    priorityTask = "先围绕“" + topic + "”速练 " + questionCount + " 题，尽快把薄弱点拉回主线";
  } else if (remainingTarget > 0) {
    priorityTask = "先完成今天剩余的 " + remainingTarget + " 题目标，保持学习节奏";
  } else {
    priorityTask = "先完成一轮短练习，系统会继续更新你的薄弱点判断";
  }

  if (topic) {
    studyMethod = "先看“" + topic + "”考点梳理，再做真题强化，最后回看错题";
  } else if (dueToday > 0) {
    studyMethod = "先复习再练题，把今天待回看的内容优先清掉";
  } else {
    studyMethod = "先做短练，再按错题回看考点，保持诊断持续更新";
  }

  if (totalDue > 0 || overdueCount > 0) {
    timeBudget = "约 15 分钟，优先清理复习任务";
  } else if (remainingTarget > 0) {
    timeBudget = "约 12 分钟，完成今日目标后再加练一轮";
  } else {
    timeBudget = "约 10 分钟，保持今天的学习节奏";
  }

  if (data.focusHint) {
    coachNote = data.focusHint;
  } else if (topic) {
    coachNote = "当前最值得优先补强的章节是“" + topic + "”";
  } else if ((data.hotspots || []).length) {
    coachNote = "系统检测到热点失分项，建议优先处理高频问题";
  } else {
    coachNote = "先保持练习频率，系统会继续为你收敛更准确的作战建议";
  }

  return {
    focusTopic: topic || "今天先稳住基础节奏",
    priorityTask: priorityTask,
    studyMethod: studyMethod,
    timeBudget: timeBudget,
    coachNote: coachNote,
  };
}

function _normalizeBattlePlan(raw) {
  var plan = raw || {};
  var focusTopic = String(plan.focus_topic || plan.focusTopic || "").trim();
  var priorityTask = String(plan.priority_task || plan.priorityTask || "").trim();
  var studyMethod = String(plan.study_method || plan.studyMethod || "").trim();
  var timeBudget = String(plan.time_budget || plan.timeBudget || "").trim();
  var coachNote = String(plan.coach_note || plan.coachNote || "").trim();

  if (!(focusTopic || priorityTask || studyMethod || timeBudget || coachNote)) {
    return null;
  }

  return {
    focusTopic: focusTopic || "今天先稳住基础节奏",
    priorityTask: priorityTask,
    studyMethod: studyMethod,
    timeBudget: timeBudget,
    coachNote: coachNote,
  };
}

function _buildProgressCards(input) {
  var data = input || {};
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var streakDays = Number(data.streakDays) || 0;
  var dueToday = Number(data.dueTodayCount) || 0;
  var hotspotCount = Array.isArray(data.hotspots) ? data.hotspots.length : 0;
  var progressPct = dailyTarget > 0 ? Math.min(100, Math.round((todayDone / dailyTarget) * 100)) : 0;

  return [
    {
      label: "今日完成",
      value: dailyTarget > 0 ? todayDone + "/" + dailyTarget : String(todayDone),
      detail: dailyTarget > 0 ? "目标进度 " + progressPct + "%" : "今天已完成练习",
      toneClass: progressPct >= 100 ? "tone-good" : "tone-accent",
    },
    {
      label: "连续学习",
      value: streakDays + "天",
      detail: streakDays > 0 ? "节奏正在形成" : "今天开始建立节奏",
      toneClass: streakDays >= 3 ? "tone-good" : "tone-accent",
    },
    {
      label: "待复习",
      value: String(dueToday),
      detail: dueToday > 0 ? "建议今天优先清理" : "复习节奏稳定",
      toneClass: dueToday > 0 ? "tone-warn" : "tone-good",
    },
    {
      label: "热点关注",
      value: String(hotspotCount),
      detail: hotspotCount > 0 ? "优先看高频失分点" : "当前无明显热点",
      toneClass: hotspotCount > 0 ? "tone-warn" : "tone-good",
    },
  ];
}

function _buildProgressInsight(input) {
  var data = input || {};
  var dueToday = Number(data.dueTodayCount) || 0;
  var hotspotCount = Array.isArray(data.hotspots) ? data.hotspots.length : 0;
  var weakGroup = (data.masteryGroups || []).find(function (group) {
    return group && group.name === "需要加强" && Array.isArray(group.chapters) && group.chapters.length;
  });
  var weakChapter = weakGroup && weakGroup.chapters[0] ? weakGroup.chapters[0].name : "";

  if (data.focusHint) return data.focusHint;
  if (weakChapter) {
    return "当前最值得观察的变化点在“" + weakChapter + "”，继续推进后这里最容易先出现抬升";
  }
  if (dueToday > 0) {
    return "今天还有 " + dueToday + " 个待复习点，先清掉它们，后面的进步反馈会更扎实";
  }
  if (hotspotCount > 0) {
    return "系统检测到 " + hotspotCount + " 个高频失分热点，先处理这些点更容易看到掌握度变化";
  }
  return "先保持今天的学习动作，系统会持续把你的节奏变化沉淀成可见反馈";
}

function _buildProgressSummary(input) {
  var data = input || {};
  var streakDays = Number(data.streakDays) || 0;
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  if (dailyTarget > 0) {
    return (
      (streakDays > 0 ? "已连续学习 " + streakDays + " 天" : "今天是新的起点") +
      "，当前已完成 " +
      todayDone +
      "/" +
      dailyTarget +
      "，继续保持就能看到更稳的进步反馈"
    );
  }
  return streakDays > 0
    ? "已连续学习 " + streakDays + " 天，继续保持，系统会持续记录你的进步轨迹"
    : "开始完成今天的第一轮练习后，这里会出现更清晰的进步反馈";
}

function _buildProgressMilestones(input) {
  var data = input || {};
  var milestones = [];
  var todayDone = Number(data.todayDone) || 0;
  var dailyTarget = Number(data.dailyTarget) || 0;
  var streakDays = Number(data.streakDays) || 0;
  var dueToday = Number(data.dueTodayCount) || 0;
  var weakGroup = (data.masteryGroups || []).find(function (group) {
    return group && group.name === "需要加强" && Array.isArray(group.chapters) && group.chapters.length;
  });
  var weakChapter = weakGroup && weakGroup.chapters[0] ? weakGroup.chapters[0] : null;

  if (todayDone > 0) {
    milestones.push({
      title: "今日学习已经启动",
      detail:
        dailyTarget > 0
          ? "今天已完成 " + todayDone + "/" + dailyTarget + "，继续推进后这里会更快出现正向反馈"
          : "今天已经完成 " + todayDone + " 题，系统开始记录你的变化轨迹",
      toneClass: "tone-accent",
    });
  }

  if (weakChapter && weakChapter.name) {
    milestones.push({
      title: "薄弱章节已经锁定",
      detail: "当前最需要优先拉升的是“" + weakChapter.name + "”，掌握度 " + weakChapter.mastery + "%",
      toneClass: "tone-warn",
    });
  }

  if (streakDays > 0) {
    milestones.push({
      title: streakDays >= 3 ? "连续学习节奏已形成" : "连续学习正在建立",
      detail:
        streakDays >= 3
          ? "已经连续学习 " + streakDays + " 天，继续保持更容易看到掌握度抬升"
          : "已连续学习 " + streakDays + " 天，再保持几天就能形成更稳定的进步曲线",
      toneClass: streakDays >= 3 ? "tone-good" : "tone-accent",
    });
  }

  if (dueToday > 0) {
    milestones.push({
      title: "复习压力还需要处理",
      detail: "今天还有 " + dueToday + " 个待复习点，先清理这些内容，再加练会更高效",
      toneClass: "tone-warn",
    });
  }

  return milestones.slice(0, 3);
}

function _normalizeProgressFeedback(raw) {
  var feedback = raw || {};
  var summary = String(feedback.summary || "").trim();
  var insight = String(feedback.insight || "").trim();
  var cards = (feedback.cards || []).map(function (item) {
    return {
      label: String(item.label || "").trim(),
      value: String(item.value || "").trim(),
      detail: String(item.detail || "").trim(),
      toneClass: String(item.tone_class || item.toneClass || "tone-accent").trim() || "tone-accent",
    };
  }).filter(function (item) {
    return item.label || item.value || item.detail;
  });
  var milestones = (feedback.milestones || []).map(function (item) {
    return {
      title: String(item.title || "").trim(),
      detail: String(item.detail || "").trim(),
      toneClass: String(item.tone_class || item.toneClass || "tone-accent").trim() || "tone-accent",
    };
  }).filter(function (item) {
    return item.title || item.detail;
  });

  if (!(summary || insight || cards.length || milestones.length)) {
    return null;
  }

  return {
    summary: summary,
    insight: insight,
    cards: cards,
    milestones: milestones,
  };
}

function _hasSnapshotData(value) {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.length > 0;
  return Object.keys(value).length > 0;
}

function _snapshotValue(snapshot, key) {
  var value = snapshot && snapshot[key];
  return _hasSnapshotData(value) ? value : null;
}

function _unwrapSnapshotItem(raw) {
  var value = api.unwrapResponse(raw);
  return _hasSnapshotData(value) ? value : null;
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,

    // WXML 不支持 HTML 实体，用 data 绑定传入 Unicode 字符
    warnIcon: "\u26A0\uFE0F",
    radarIcon: "\uD83D\uDCE1",

    isDark: true,

    // 加载状态
    radarLoading: true,
    masteryLoading: true,
    radarError: false,
    masteryError: false,

    // 雷达图数据
    radarDimensions: [],
    strongCount: 0,
    normalCount: 0,
    weakCount: 0,
    avgScore: 0,

    // 维度详情列表（按 value 升序 = 薄弱优先）
    dimList: [],

    // 雷达图渲染后的图片（解决 canvas 不跟随滚动的问题）
    radarImage: "",

    // 掌握度数据
    overallMastery: 0,
    masteryGroups: [],
    hotspots: [],
    reviewSummary: { total_due: 0, overdue_count: 0 },
    todayDone: 0,
    dailyTarget: 0,
    streakDays: 0,
    dueTodayCount: 0,
    weakNodeCount: 0,
    focusHint: "",
    homeStudyPlan: null,
    homeProgressFeedback: null,
    learnerLevel: "",
    learnerLevelName: "",
    learnerStageTitle: "当前学习状态",
    studyTip: "",
    diagnosticScore: 0,
    battlePlan: {
      focusTopic: "系统正在生成今日主攻",
      priorityTask: "学情同步后，这里会给你最优先的一步动作",
      studyMethod: "系统会结合薄弱点、热点和今日任务，自动给出学习顺序",
      timeBudget: "约 10 分钟",
      coachNote: "完成更多练习后，AI 作战建议会更准确",
    },
    progressSummary: "完成更多练习后，这里会出现更清晰的进步反馈",
    progressInsight: "先开始今天的练习，系统会逐步把你的变化沉淀成更清晰的反馈",
    progressCards: _buildProgressCards({}),
    progressMilestones: _buildProgressMilestones({}),
    navBackLabel: "对话",
    assessmentEnabled: true,
  },

  _radarRenderSeq: 0,
  _radarRenderPending: false,
  _radarImageSignature: "",
  _radarSignature: "",
  _reportSnapshot: null,

  onLoad() {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
    });
  },

  onShow() {
    var workspaceBack = runtime.getWorkspaceBack(route.report());
    if (!flags.ensureFeatureEnabled("report")) return;
    this.setData({ isDark: helpers.isDark() });
    this.setData({
      navBackLabel: workspaceBack ? workspaceBack.label : "对话",
      assessmentEnabled: flags.isFeatureEnabled("assessment"),
    });
    helpers.syncTabBar(this, 2, {
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    runtime.checkAuth(() => {
      this.setData({
        radarLoading: true,
        masteryLoading: true,
        radarError: false,
        masteryError: false,
      });
      this._loadReportPage();
    });
  },

  async _loadReportSnapshot() {
    const tasks = [
      api.getTodayProgress().catch(() => null),
      api.getHomeDashboard().catch(() => null),
      api.getAssessmentProfile().catch(() => null),
      api.getMasteryDashboard().catch(() => null),
    ];
    const result = await Promise.all(tasks);
    return {
      progress: _unwrapSnapshotItem(result[0]),
      home: _unwrapSnapshotItem(result[1]),
      assessment: _unwrapSnapshotItem(result[2]),
      mastery: _unwrapSnapshotItem(result[3]),
    };
  },

  async _loadReportPage() {
    var snapshot = await this._loadReportSnapshot();
    this._reportSnapshot = snapshot;
    await Promise.all([
      this._loadOverview(snapshot),
      this._loadRadar(snapshot),
      this._loadMastery(snapshot),
    ]);
    this._syncExperienceSections();
  },

  onReady() {
    this._canvasReady = true;
    this._ensureRadarRendered(
      this.data.radarDimensions,
      this._radarSignature || _buildRadarSignature(this.data.radarDimensions),
    );
  },

  // ── 返回首页 ───────────────────────────────────────
  goHome() {
    var workspaceBack = runtime.consumeWorkspaceBack(route.report());
    if (workspaceBack && workspaceBack.url) {
      wx.reLaunch({ url: workspaceBack.url });
      return;
    }
    runtime.setWorkspaceBack(route.report(), "学情");
    runtime.markGoHome();
    wx.reLaunch({ url: route.chat() });
  },

  goAssessment() {
    if (!flags.ensureFeatureEnabled("assessment")) return;
    helpers.vibrate("light");
    wx.navigateTo({ url: route.assessment() });
  },

  async _loadOverview(snapshot) {
    try {
      const progress =
        _snapshotValue(snapshot, "progress")
          ? _snapshotValue(snapshot, "progress")
          : api.unwrapResponse(await api.getTodayProgress()) || {};
      const home =
        _snapshotValue(snapshot, "home")
          ? _snapshotValue(snapshot, "home")
          : api.unwrapResponse(await api.getHomeDashboard()) || {};
      const assessment =
        _snapshotValue(snapshot, "assessment")
          ? _snapshotValue(snapshot, "assessment")
          : api.unwrapResponse(await api.getAssessmentProfile()) || {};

      const weakNodes = ((home.mastery || {}).weak_nodes || []).filter(Boolean);
      const diagnosticFeedback = assessment.diagnostic_feedback || {};
      const learnerProfile = diagnosticFeedback.learner_profile || {};

      this.setData({
        todayDone: progress.today_done || 0,
        dailyTarget: progress.daily_target || 0,
        streakDays: progress.streak_days || 0,
        dueTodayCount: ((home.review || {}).due_today || 0),
        weakNodeCount: weakNodes.length,
        focusHint: ((home.today || {}).hint || ""),
        homeStudyPlan: home.study_plan || null,
        homeProgressFeedback: home.progress_feedback || null,
        learnerLevel: _displayLevelName(assessment.level || ""),
        learnerLevelName: _displayLevelName(assessment.level || ""),
        learnerStageTitle: assessment.level
          ? _displayLevelName(assessment.level) + "阶段"
          : "当前学习状态",
        studyTip: learnerProfile.study_tip || "",
      });
    } catch (_) {}
  },

  // ── 加载学情数据（统一使用 assessment profile API）────
  async _loadRadar(snapshot) {
    try {
      var dims = [];
      var assessmentData =
        _snapshotValue(snapshot, "assessment")
          ? _snapshotValue(snapshot, "assessment")
          : api.unwrapResponse(await api.getAssessmentProfile()) || {};
      dims = _buildRadarDimensionsFromAssessment(assessmentData);

      if (!dims.length || !_hasPositiveRadarSignal(dims)) {
        try {
          var radarResult = await api.getRadarData(RADAR_SELF_SUBJECT);
          var radarData = api.unwrapResponse(radarResult) || {};
          var radarDims = _normalizeRadarDimensions(radarData);
          if (radarDims.length && _hasPositiveRadarSignal(radarDims)) {
            dims = radarDims;
          }
        } catch (_) {}
      }

      if (dims.length === 0) {
        this.setData({ radarLoading: false, radarError: false });
        return;
      }

      var viewModel = _buildRadarViewModel(dims);
      var signature = _buildRadarSignature(dims);

      this.setData({
        radarDimensions: dims,
        strongCount: viewModel.strongCount,
        normalCount: viewModel.normalCount,
        weakCount: viewModel.weakCount,
        avgScore: viewModel.avgScore,
        dimList: viewModel.dimList,
        radarLoading: false,
      });

      this._radarSignature = signature;
      this._ensureRadarRendered(dims, signature);
    } catch (e) {
      try {
        var fallbackDims = [];
        try {
          var radarFallback = await api.getRadarData(RADAR_SELF_SUBJECT);
          var radarFallbackData = api.unwrapResponse(radarFallback) || {};
          var radarDims = _normalizeRadarDimensions(radarFallbackData);
          if (radarDims.length && _hasPositiveRadarSignal(radarDims)) {
            fallbackDims = radarDims;
          }
        } catch (_) {}
        if (!fallbackDims.length) {
          this.setData({ radarLoading: false, radarError: true });
          return;
        }
        var fallbackViewModel = _buildRadarViewModel(fallbackDims);
        var signature = _buildRadarSignature(fallbackDims);
        this.setData({
          radarDimensions: fallbackDims,
          strongCount: fallbackViewModel.strongCount,
          normalCount: fallbackViewModel.normalCount,
          weakCount: fallbackViewModel.weakCount,
          avgScore: fallbackViewModel.avgScore,
          dimList: fallbackViewModel.dimList,
          radarLoading: false,
          radarError: false,
        });
        this._radarSignature = signature;
        this._ensureRadarRendered(fallbackDims, signature);
      } catch (_) {
        // 雷达数据加载失败，通过 radarError 状态展示
        this.setData({ radarLoading: false, radarError: true });
      }
    }
  },

  // ── 加载掌握度数据（也从 assessment profile 获取）────
  async _loadMastery(snapshot) {
    try {
      var data =
        _snapshotValue(snapshot, "mastery")
          ? _snapshotValue(snapshot, "mastery")
          : api.unwrapResponse(await api.getMasteryDashboard()) || {};
      var groups = (data.groups || []).map(function (group) {
        var chapters = (group.chapters || []).map(function (chapter) {
          var mastery = Math.round(chapter.mastery || 0);
          return {
            name: _displayChapterName(chapter.name || ""),
            mastery: mastery,
            color:
              mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
          };
        });
        chapters.sort(function (a, b) {
          return a.mastery - b.mastery;
        });
        return {
          name: group.name || "",
          avgMastery: Math.round(group.avg_mastery || 0),
          chapters: chapters,
        };
      });

      var hotspots = (data.hotspots || []).map(function (item) {
        var mastery = Math.round(item.mastery || 0);
        return {
          name: _displayChapterName(item.name || ""),
          mastery: mastery,
          rateText: mastery + "%",
        };
      });

      var overall = Math.round(data.overall_mastery || 0);
      var reviewSummary = data.review_summary || { total_due: 0, overdue_count: 0 };

      if (!groups.length && !overall) {
        var fallbackData =
          _snapshotValue(snapshot, "assessment")
            ? _snapshotValue(snapshot, "assessment")
            : api.unwrapResponse(await api.getAssessmentProfile()) || {};
        var cm = fallbackData.chapter_mastery || {};
        var weakChapters = [];
        var normalChapters = [];
        var strongChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = _displayChapterName((typeof v === "object" ? v.name : k) || k);
          var mastery = (typeof v === "object" ? v.mastery : v) || 0;
          var item = {
            name: name,
            mastery: mastery,
            color:
              mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
          };
          if (mastery >= 70) strongChapters.push(item);
          else if (mastery >= 40) normalChapters.push(item);
          else weakChapters.push(item);
        });

        groups = [];
        if (weakChapters.length) groups.push({ name: "需要加强", avgMastery: 0, chapters: weakChapters });
        if (normalChapters.length) groups.push({ name: "基本掌握", avgMastery: 0, chapters: normalChapters });
        if (strongChapters.length) groups.push({ name: "掌握较好", avgMastery: 0, chapters: strongChapters });
        groups.forEach(function (g) {
          if (!g.chapters.length) return;
          g.chapters.sort(function (a, b) {
            return a.mastery - b.mastery;
          });
          g.avgMastery = Math.round(
            g.chapters.reduce(function (s, c) {
              return s + c.mastery;
            }, 0) / g.chapters.length,
          );
        });

        var allMastery = Object.keys(cm).map(function (k) {
          var v = cm[k];
          return (typeof v === "object" ? v.mastery : v) || 0;
        });
        overall = allMastery.length
          ? Math.round(
              allMastery.reduce(function (a, b) {
                return a + b;
              }, 0) / allMastery.length,
            )
          : 0;
        hotspots = [];
        reviewSummary = { total_due: 0, overdue_count: 0 };
      }

      this.setData({
        overallMastery: overall,
        masteryGroups: groups,
        hotspots: hotspots,
        reviewSummary: reviewSummary,
        masteryLoading: false,
      });
    } catch (e) {
      // 掌握度数据加载失败，通过 masteryError 状态展示
      this.setData({ masteryLoading: false, masteryError: true });
    }
  },

  _syncExperienceSections() {
    var diagnosticScore = this.data.overallMastery || this.data.avgScore || 0;
    var sharedInput = {
      masteryGroups: this.data.masteryGroups,
      hotspots: this.data.hotspots,
      dimList: this.data.dimList,
      dueTodayCount: this.data.dueTodayCount,
      reviewSummary: this.data.reviewSummary,
      todayDone: this.data.todayDone,
      dailyTarget: this.data.dailyTarget,
      streakDays: this.data.streakDays,
      focusHint: this.data.focusHint,
    };
    var progressFeedback = _normalizeProgressFeedback(this.data.homeProgressFeedback);

    this.setData({
      diagnosticScore: diagnosticScore,
      battlePlan: _normalizeBattlePlan(this.data.homeStudyPlan) || _buildBattlePlanModel(sharedInput),
      progressSummary: (progressFeedback && progressFeedback.summary) || _buildProgressSummary(sharedInput),
      progressInsight: (progressFeedback && progressFeedback.insight) || _buildProgressInsight(sharedInput),
      progressCards:
        (progressFeedback && progressFeedback.cards && progressFeedback.cards.length
          ? progressFeedback.cards
          : null) || _buildProgressCards(sharedInput),
      progressMilestones:
        (progressFeedback && progressFeedback.milestones && progressFeedback.milestones.length
          ? progressFeedback.milestones
          : null) || _buildProgressMilestones(sharedInput),
    });
  },

  // ── 重试 ──────────────────────────────────────────
  retryRadar() {
    this._radarImageSignature = "";
    this._radarSignature = "";
    this._radarRenderPending = false;
    this._radarRenderSeq += 1;
    this.setData({ radarError: false, radarLoading: true, radarImage: "" });
    this._loadRadar();
  },

  retryMastery() {
    this.setData({ masteryError: false, masteryLoading: true });
    this._loadMastery();
  },

  // ── Canvas 2D 绘制雷达图 ──────────────────────────
  _ensureRadarRendered(dims, signature) {
    signature = signature || _buildRadarSignature(dims);
    if (!this._canvasReady) return;
    if (!Array.isArray(dims) || dims.length === 0) return;
    if (this._radarRenderPending) return;
    if (this.data.radarImage && this._radarImageSignature === signature) return;
    this._drawRadar(dims, signature);
  },

  _drawRadar(dims, signature) {
    signature = signature || _buildRadarSignature(dims);
    var renderSeq = ++this._radarRenderSeq;
    this._radarRenderPending = true;
    const query = wx.createSelectorQuery().in(this);
    query
      .select("#radarCanvas")
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          if (renderSeq === this._radarRenderSeq) {
            this._radarRenderPending = false;
          }
          return;
        }
        if (renderSeq !== this._radarRenderSeq) return;

        const canvas = res[0].node;
        const ctx = canvas.getContext("2d");
        const dpr = helpers.getWindowInfo().pixelRatio || 2;
        const width = res[0].width;
        const height = res[0].height;

        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        const cx = width / 2;
        const cy = height / 2;
        const r = Math.min(cx, cy) - 24;
        const n = dims.length;
        const values = dims.map((d) => d.value || 0);
        const labels = dims.map((d) => {
          const name = d.name || "";
          return name.length > 5 ? name.slice(0, 5) + "…" : name;
        });
        const palette = this.data.isDark
          ? {
              grid: "rgba(255,255,255,0.12)",
              axis: "rgba(255,255,255,0.08)",
              fill: "rgba(99,102,241,0.18)",
              line: "rgba(129,140,248,0.78)",
              point: "rgba(129,140,248,0.95)",
              label: "rgba(255,255,255,0.72)",
            }
          : {
              grid: "rgba(51,65,85,0.18)",
              axis: "rgba(51,65,85,0.12)",
              fill: "rgba(47,107,255,0.14)",
              line: "rgba(37,99,235,0.76)",
              point: "rgba(37,99,235,0.92)",
              label: "rgba(15,23,42,0.76)",
            };

        ctx.clearRect(0, 0, width, height);

        // 网格（4 层同心多边形）
        for (let ring = 1; ring <= 4; ring++) {
          ctx.beginPath();
          const rr = (r * ring) / 4;
          for (let i = 0; i <= n; i++) {
            const angle = (Math.PI * 2 * (i % n)) / n - Math.PI / 2;
            const x = cx + rr * Math.cos(angle);
            const y = cy + rr * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.closePath();
          ctx.strokeStyle = palette.grid;
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        // 轴线
        for (let i = 0; i < n; i++) {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.lineTo(cx + r * Math.cos(angle), cy + r * Math.sin(angle));
          ctx.strokeStyle = palette.axis;
          ctx.stroke();
        }

        // 数据多边形
        ctx.beginPath();
        for (let i = 0; i <= n; i++) {
          const idx = i % n;
          const angle = (Math.PI * 2 * idx) / n - Math.PI / 2;
          const v = values[idx] * r;
          const x = cx + v * Math.cos(angle);
          const y = cy + v * Math.sin(angle);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fillStyle = palette.fill;
        ctx.fill();
        ctx.strokeStyle = palette.line;
        ctx.lineWidth = 2;
        ctx.stroke();

        // 数据点 + 标签
        const labelOffset = r + 14;
        ctx.font = "10px -apple-system, sans-serif";
        for (let i = 0; i < n; i++) {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const v = values[i] * r;
          const x = cx + v * Math.cos(angle);
          const y = cy + v * Math.sin(angle);

          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fillStyle = palette.point;
          ctx.fill();

          const cosA = Math.cos(angle);
          const sinA = Math.sin(angle);
          let lx = cx + labelOffset * cosA;
          let ly = cy + labelOffset * sinA;

          // 根据角度动态对齐
          if (cosA > 0.3) ctx.textAlign = "left";
          else if (cosA < -0.3) ctx.textAlign = "right";
          else ctx.textAlign = "center";

          if (sinA < -0.3) ctx.textBaseline = "bottom";
          else if (sinA > 0.3) ctx.textBaseline = "top";
          else ctx.textBaseline = "middle";

          // 防止标签溢出画布边界
          const pad = 2;
          const tw = ctx.measureText
            ? ctx.measureText(labels[i]).width
            : labels[i].length * 10;
          if (ctx.textAlign === "left" && lx + tw > width - pad) {
            lx = width - pad - tw;
          } else if (ctx.textAlign === "right" && lx - tw < pad) {
            lx = pad + tw;
          }
          if (ly < pad + 10) ly = pad + 10;
          if (ly > height - pad) ly = height - pad;

          ctx.fillStyle = palette.label;
          ctx.fillText(labels[i], lx, ly);
        }

        // 仅在 canvas 完成本次绘制后导出一次图片，避免靠定时器猜测时机
        wx.nextTick(() => {
          if (renderSeq !== this._radarRenderSeq) return;
          wx.canvasToTempFilePath({
            canvas: canvas,
            success: (result) => {
              if (renderSeq !== this._radarRenderSeq) return;
              this._radarImageSignature = signature;
              this.setData({ radarImage: result.tempFilePath });
            },
            fail: () => {},
            complete: () => {
              if (renderSeq === this._radarRenderSeq) {
                this._radarRenderPending = false;
              }
            },
          });
        });
      });
  },

  // ── 跳转练习 ─────────────────────────────────────
  goPractice() {
    wx.navigateTo({ url: route.practice() });
  },
});
