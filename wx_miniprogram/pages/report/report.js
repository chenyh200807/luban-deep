// pages/report/report.js — 学习报告：能力雷达 + 摸底报告

const api = require("../../utils/api");
const helpers = require("../../utils/helpers");

const RADAR_SELF_SUBJECT = "self";

function buildRadarDimensionsFromAssessment(data) {
  var mastery = (data && data.chapter_mastery) || {};
  return Object.keys(mastery).map(function (key) {
    var item = mastery[key];
    var score = (typeof item === "object" ? item.mastery : item) || 0;
    return {
      name: (typeof item === "object" ? item.name : key) || key,
      value: Number(score || 0) / 100,
    };
  });
}

function hasPositiveRadarSignal(dims) {
  return (dims || []).some(function (item) {
    return Number(item && item.value) > 0;
  });
}

function normalizeRadarDimensions(radarData) {
  return ((radarData && radarData.dimensions) || []).map(function (item) {
    var score = Number(item.score);
    var value =
      typeof item.value === "number"
        ? item.value
        : Number.isFinite(score)
        ? score / 100
        : 0;
    return {
      name: item.label || item.name || item.key || "",
      value: value || 0,
    };
  });
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
    masteryExpanded: false,
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
    userPoints: 0,
    todayDone: 0,
    dailyTarget: 0,
    streakDays: 0,
    dueTodayCount: 0,
    weakNodeCount: 0,
    focusHint: "",
    learnerLevel: "",
    studyTip: "",
  },

  onLoad() {
    const windowInfo = helpers.getWindowInfo();
    const navHeight = windowInfo.statusBarHeight + 44;
    this.setData({
      statusBarHeight: windowInfo.statusBarHeight,
      navHeight,
    });
  },

  onShow() {
    this.setData({ isDark: helpers.isDark() });
    helpers.syncTabBar(this, 2);
    const app = getApp();
    app.checkAuth(() => {
      this._loadOverview();
      this._loadRadar();
      this._loadMastery();
      this._loadPoints();
    });
  },

  async _loadPoints() {
    try {
      const data = await api.getWallet();
      this.setData({ userPoints: data.balance || 0 });
    } catch (_) {}
  },

  goBilling() {
    wx.navigateTo({ url: "/pages/billing/billing" });
  },

  onReady() {
    this._canvasReady = true;
    if (this.data.radarDimensions.length > 0) {
      this._drawRadar(this.data.radarDimensions);
    }
  },

  // ── 返回首页 ───────────────────────────────────────
  goHome() {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },

  goAssessment() {
    helpers.vibrate("light");
    wx.navigateTo({ url: "/pages/assessment/assessment" });
  },

  async _loadOverview() {
    try {
      const tasks = [
        api.getTodayProgress().catch(() => null),
        api.getHomeDashboard().catch(() => null),
        api.getAssessmentProfile().catch(() => null),
      ];

      const result = await Promise.all(tasks);
      const progress = api.unwrapResponse(result[0]) || {};
      const home = api.unwrapResponse(result[1]) || {};
      const assessment = api.unwrapResponse(result[2]) || {};

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
        learnerLevel: assessment.level || "",
        studyTip: learnerProfile.study_tip || "",
      });
    } catch (_) {}
  },

  toggleMastery() {
    helpers.vibrate("light");
    this.setData({ masteryExpanded: !this.data.masteryExpanded });
  },

  // ── 加载学情数据（assessment profile 为唯一主 authority）────
  async _loadRadar() {
    try {
      var dims = [];
      var result = await api.getAssessmentProfile();
      var data = api.unwrapResponse(result) || {};
      dims = buildRadarDimensionsFromAssessment(data);

      if (!dims.length || !hasPositiveRadarSignal(dims)) {
        try {
          var radarResult = await api.getRadarData(RADAR_SELF_SUBJECT);
          var radarData = api.unwrapResponse(radarResult) || {};
          var radarDims = normalizeRadarDimensions(radarData);
          if (radarDims.length && hasPositiveRadarSignal(radarDims)) {
            dims = radarDims;
          }
        } catch (_) {}
      }

      if (dims.length === 0) {
        this.setData({ radarLoading: false });
        return;
      }

      var strong = 0,
        normal = 0,
        weak = 0;
      dims.forEach(function (d) {
        var pct = Math.round((d.value || 0) * 100);
        if (pct >= 70) strong++;
        else if (pct >= 40) normal++;
        else weak++;
      });

      var avg = Math.round(
        (dims.reduce(function (s, d) {
          return s + (d.value || 0);
        }, 0) /
          dims.length) *
          100,
      );

      var sorted = dims.slice().sort(function (a, b) {
        return (a.value || 0) - (b.value || 0);
      });
      var dimList = sorted.map(function (d, i) {
        var pct = Math.round((d.value || 0) * 100);
        return {
          rank: i + 1,
          name: d.name,
          pct: pct,
          cls: pct >= 70 ? "strong" : pct >= 40 ? "normal" : "weak",
          color: pct >= 70 ? "#34d399" : pct >= 40 ? "#fbbf24" : "#f87171",
        };
      });

      this.setData({
        radarDimensions: dims,
        strongCount: strong,
        normalCount: normal,
        weakCount: weak,
        avgScore: avg,
        dimList: dimList,
        radarLoading: false,
      });

      if (this._canvasReady) {
        this._drawRadar(dims);
      }
    } catch (e) {
      // 雷达数据加载失败，通过 radarError 状态展示
      this.setData({ radarLoading: false, radarError: true });
    }
  },

  // ── 加载掌握度数据（也从 assessment profile 获取）────
  async _loadMastery() {
    try {
      var result = await api.getMasteryDashboard();
      var data = api.unwrapResponse(result) || {};
      var groups = (data.groups || []).map(function (group) {
        return {
          name: group.name || "",
          avgMastery: Math.round(group.avg_mastery || 0),
          chapters: (group.chapters || []).map(function (chapter) {
            var mastery = Math.round(chapter.mastery || 0);
            return {
              name: chapter.name || "",
              mastery: mastery,
              color:
                mastery >= 70 ? "#34d399" : mastery >= 40 ? "#fbbf24" : "#f87171",
            };
          }),
        };
      });

      var hotspots = (data.hotspots || []).map(function (item) {
        var mastery = Math.round(item.mastery || 0);
        return {
          name: item.name || "",
          mastery: mastery,
          rateText: mastery + "%",
        };
      });

      var overall = Math.round(data.overall_mastery || 0);
      var reviewSummary = data.review_summary || { total_due: 0, overdue_count: 0 };

      if (!groups.length && !overall) {
        var fallback = await api.getAssessmentProfile();
        var fallbackData = api.unwrapResponse(fallback) || {};
        var cm = fallbackData.chapter_mastery || {};
        var weakChapters = [];
        var normalChapters = [];
        var strongChapters = [];
        Object.keys(cm).forEach(function (k) {
          var v = cm[k];
          var name = (typeof v === "object" ? v.name : k) || k;
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

  // ── 重试 ──────────────────────────────────────────
  retryRadar() {
    this.setData({ radarError: false, radarLoading: true, radarImage: "" });
    this._loadRadar();
  },

  retryMastery() {
    this.setData({ masteryError: false, masteryLoading: true });
    this._loadMastery();
  },

  // ── Canvas 2D 绘制雷达图 ──────────────────────────
  _drawRadar(dims) {
    const query = wx.createSelectorQuery().in(this);
    query
      .select("#radarCanvas")
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) return;

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

        // 转为图片，解决 canvas 不跟随 scroll-view 滚动的问题
        setTimeout(() => {
          wx.canvasToTempFilePath({
            canvas: canvas,
            success: (result) => {
              this.setData({ radarImage: result.tempFilePath });
            },
            fail: () => {},
          });
        }, 100);
      });
  },

  // ── 跳转练习 ─────────────────────────────────────
  goPractice() {
    wx.navigateTo({ url: "/pages/practice/practice" });
  },
});
