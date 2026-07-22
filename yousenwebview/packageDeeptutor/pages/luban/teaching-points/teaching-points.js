// 鲁班学习双轮 · 全部教学集
// 40 个考点是进度/练习/掌握的唯一归属；这里仅把已发布 lesson*.html 投影成可点视频集。
// 不写学习证据，不缓存或自造 episode 名单；后端缺页时 fail-closed，前端宁可少展示。
const api = require("../../../utils/api");
const helpers = require("../../../utils/helpers");
const auth = require("../../../utils/auth");
const route = require("../../../utils/route");
const runtime = require("../../../utils/runtime");
const packNames = require("../../../utils/pack-short-names");
const telemetry = require("../../../utils/surface-telemetry");
const flags = require("../../../utils/flags");

// 五章只是 40 pack 路线的版式分段，不参与知识分类、练习或掌握判定。
const CHAPTER_LAYOUT = [
  { id: "01", title: "验收与基础施工", subtitle: "程序 · 支护 · 主体基础", packIds: ["A01", "A02", "B02", "C01", "C04", "C05", "C06", "C07"] },
  { id: "02", title: "装饰与防水工程", subtitle: "砌体 · 装饰 · 防水构造", packIds: ["D11", "D12", "D13", "D14", "F02", "F03", "F04", "F05"] },
  { id: "03", title: "地基防水与专项工程", subtitle: "起鼓 · 地基 · 危大 · 支架", packIds: ["F16", "G01", "G02", "G03", "G04", "J01", "R01", "S01"] },
  { id: "04", title: "进度质量与索赔", subtitle: "进度 · 质量 · 网络计划", packIds: ["C02", "E05", "K01", "N01", "N02", "N03", "Q01", "Q02"] },
  { id: "05", title: "安全管理与施工组织", subtitle: "安全 · 现场 · 绿色施工", packIds: ["Q03", "S02", "S05", "S06", "S07", "X01", "X02", "X03"] },
];
// C 版：重色行 / 全纸行交替；下一重色行黑红镜像。
const C_TONE_PATTERN = [
  ["ink", "paper", "red"],
  ["paper", "paper", "paper"],
  ["red", "paper", "ink"],
  ["paper", "paper", "paper"],
];

function compactTitle(title) {
  const value = String(title || "").trim();
  return value.length > 6 ? value.slice(0, 6) : value;
}

function buildEpisodeGroups(rawPoints) {
  const byPack = Object.create(null);
  const packOrder = [];
  (Array.isArray(rawPoints) ? rawPoints : []).forEach(function (point) {
    const item = point || {};
    const packId = String(item.pack_id || "").trim().toUpperCase();
    const index = Number(item.episode_index);
    const total = Number(item.episode_total);
    if (!packId || !Number.isInteger(index) || !Number.isInteger(total) || index < 1 || total < index) return;
    if (!byPack[packId]) {
      packOrder.push(packId);
      byPack[packId] = {
        packId: packId,
        title: String(item.title || ""),
        total: total,
        episodes: [],
      };
    }
    const group = byPack[packId];
    if (group.total !== total || group.episodes.some(function (episode) { return episode.index === index; })) return;
    group.episodes.push({
      id: String(item.teaching_point_id || packId + ":lesson:" + index),
      index: index,
      total: total,
      label: String(item.episode_label || "第 " + index + " 集"),
      cardUrl: String(item.card_url || ""),
    });
  });

  return packOrder
    .map(function (packId) {
      const group = byPack[packId];
      group.episodes.sort(function (left, right) { return left.index - right.index; });
      // 只展示 1..N 无缺口的真实完整集；避免接口异常时把错序页露给学员。
      if (group.episodes.length !== group.total || group.episodes.some(function (episode, index) {
        return episode.index !== index + 1;
      })) return null;
      return Object.assign(group, {
        displayTitle: packNames.shortName(group.packId, compactTitle(group.title)),
      });
    })
    .filter(function (group) { return group; });
}

// limit: 免费引子可开放的教学集上限(全局跨章计数)。null/undefined = 不限(全解锁)。
// 超出上限的卡不丢弃,只打 locked=true 显示「待开放」——保住「可见集数==后端全集数」的投影完整性,
// 同时让学员看得到还有多少集待开放(引子暗示,不是硬藏)。
function buildChapterSections(rawPoints, limit) {
  const groups = buildEpisodeGroups(rawPoints);
  const groupsByPack = Object.create(null);
  groups.forEach(function (group) { groupsByPack[group.packId] = group; });
  const freeLimit = limit === null || limit === undefined ? Infinity : limit;
  let globalIndex = 0;
  return CHAPTER_LAYOUT.map(function (chapter) {
    // 章节归属是显式展示配置；不能按 API 字母序每 8 个硬切，否则进度款会落进基础施工。
    const chapterGroups = chapter.packIds.map(function (packId) { return groupsByPack[packId]; })
      .filter(function (group) { return group; });
    const cards = [];
    chapterGroups.forEach(function (group) {
      group.episodes.forEach(function (episode) {
        const localIndex = cards.length;
        const row = Math.floor(localIndex / 3);
        const column = localIndex % 3;
        const locked = globalIndex >= freeLimit;
        globalIndex += 1;
        cards.push({
          id: episode.id,
          packId: group.packId,
          title: group.title,
          displayTitle: group.displayTitle,
          index: episode.index,
          total: episode.total,
          label: episode.label,
          labelShort: episode.total === 1 ? "讲" : episode.label.slice(0, 1),
          cardUrl: episode.cardUrl,
          locked: locked,
          tone: C_TONE_PATTERN[row % C_TONE_PATTERN.length][column],
          dots: Array.from({ length: episode.total }, function (_unused, dotIndex) {
            return { key: dotIndex + 1, active: dotIndex + 1 === episode.index };
          }),
        });
      });
    });
    return {
      id: chapter.id,
      title: chapter.title,
      subtitle: chapter.subtitle,
      topicCount: chapterGroups.length,
      lessonCount: cards.length,
      cards: cards,
    };
  }).filter(function (chapter) { return chapter.cards.length; });
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    loading: true,
    errorText: "",
    chapterSections: [],
    teachingPointUniverse: 0,
    topicUniverse: 0,
    unlockedCount: 0,
  },

  onLoad: function () {
    const info = typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    const statusBarHeight = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: statusBarHeight, navHeight: statusBarHeight + 48, isDark: helpers.isDarkOr("light") });
    if (!this._requireAuth()) return;
    this._load();
  },

  _requireAuth: function () {
    if (auth.isLoggedIn()) {
      this._authRedirectPending = false;
      return true;
    }
    if (!this._authRedirectPending) {
      this._authRedirectPending = true;
      runtime.redirectToLogin(route.lubanTeachingPoints());
    }
    return false;
  },

  goBack: function () {
    const pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.redirectTo) wx.redirectTo({ url: route.learn() });
  },

  retry: function () {
    this.setData({ loading: true, errorText: "" });
    this._load();
  },

  openEpisode: function (event) {
    const dataset = (event && event.currentTarget && event.currentTarget.dataset) || {};
    const packId = String(dataset.packId || "").trim();
    const index = Number(dataset.episode);
    if (!packId || !Number.isInteger(index) || index < 1) return;
    // 待开放集(免费引子上限之外):不跳转、不发播放埋点,只如实提示。
    if (dataset.locked) {
      if (typeof wx !== "undefined" && wx.showToast) wx.showToast({ title: "这一集待开放", icon: "none" });
      return;
    }
    if (!dataset.cardUrl) {
      if (typeof wx !== "undefined" && wx.showToast) wx.showToast({ title: "视频正在部署，请稍后再试", icon: "none" });
      return;
    }
    // 选某集微课(episode 粒度)。dataset 只暴露 pack-id/episode(见 wxml 绑定),
    // card.id(=teaching_point_id `<pack>:lesson:<idx>`)未进 dataset,故 object_id
    // 用 tp 占位符,与 station 页 _showLessonCard 同构可 join 成「列表选集→进站开讲」漏斗。
    telemetry.trackProductBehavior("learning_action_started", {
      module: "learning",
      action: "open_detail",
      objectType: "microlesson",
      objectId: packId + ":tp:" + index,
    });
    // 进站预热:station onLoad 会发同一 GET(requestStateGet dedupeInFlight 并流),
    // 把 detail 的 RTT 与页面导航并行。无状态不落缓存(本页章程:不缓存 episode 名单),
    // 失败静默,station 自有 fail-closed 错误路径。
    try {
      api.getLubanLessonDetail(packId, { episode: index, silent: true, suppressAuthRedirect: true }).catch(function () {});
    } catch (_e) {}
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.lubanStation(packId, index) });
    }
  },

  // 教学视频付费墙上限来自服务端:GET /api/v1/billing/wallet 的 teaching_video_limit。
  // 前端不自算,只消费。请求失败/未登录/字段缺失 → 返回 undefined,交给 flags 层 fail-closed 回引子。
  _loadTeachingVideoLimit: function () {
    return api.getWallet()
      .then(function (raw) {
        const wallet = api.unwrapResponse ? api.unwrapResponse(raw) : (raw || {});
        if (wallet && Object.prototype.hasOwnProperty.call(wallet, "teaching_video_limit")) {
          return wallet.teaching_video_limit; // 整数=上限;null=服务端明确无限。
        }
        return undefined; // 字段缺失 → fail-closed。
      })
      .catch(function () {
        return undefined; // 请求失败/未登录 → fail-closed,绝不因拿不到就放全部。
      });
  },

  _load: function () {
    const that = this;
    if (!this._requireAuth()) return Promise.resolve();
    return Promise.all([
      api.getLubanLessons({ silent: true, suppressAuthRedirect: true }),
      that._loadTeachingVideoLimit(),
    ])
      .then(function (results) {
        const response = results[0];
        const serverLimit = results[1];
        if (!auth.isLoggedIn()) {
          that._requireAuth();
          return null;
        }
        const body = api.unwrapResponse(response) || {};
        // 最终上限:promo 总开关 > 服务端 teaching_video_limit > fail-closed 引子(20)。
        const freeLimit = flags.resolveTeachingVideoLimit(serverLimit);
        const chapters = buildChapterSections(body.teaching_points, freeLimit);
        const visibleTeachingPointCount = chapters.reduce(function (total, chapter) {
          return total + chapter.lessonCount;
        }, 0);
        const publishedTeachingPointCount = Number(body.teaching_point_universe || 0);
        const publishedTopicCount = Number(body.teaching_topic_universe || 0);
        const visibleTopicCount = chapters.reduce(function (total, chapter) {
          return total + chapter.topicCount;
        }, 0);
        if (publishedTeachingPointCount !== visibleTeachingPointCount) {
          throw new Error("teaching_point_projection_mismatch");
        }
        if (publishedTopicCount !== visibleTopicCount) {
          throw new Error("teaching_topic_projection_mismatch");
        }
        // 已开放集数:免费引子态 = min(上限, 全集);全解锁态 = 全集。> 上限的部分显示「待开放」。
        const unlockedCount = freeLimit === null || freeLimit === undefined
          ? visibleTeachingPointCount
          : Math.min(freeLimit, visibleTeachingPointCount);
        that.setData({
          chapterSections: chapters,
          teachingPointUniverse: publishedTeachingPointCount,
          topicUniverse: publishedTopicCount,
          unlockedCount: unlockedCount,
          loading: false,
          errorText: "",
        });
        return null;
      })
      .catch(function (error) {
        if (!auth.isLoggedIn()) {
          that._requireAuth();
          return null;
        }
        that.setData({
          loading: false,
          errorText: api.describeRequestError(error, "教学集加载失败，请稍后重试"),
        });
        return null;
      });
  },
});

module.exports = {
  CHAPTER_LAYOUT: CHAPTER_LAYOUT,
  C_TONE_PATTERN: C_TONE_PATTERN,
  buildEpisodeGroups: buildEpisodeGroups,
  buildChapterSections: buildChapterSections,
};
