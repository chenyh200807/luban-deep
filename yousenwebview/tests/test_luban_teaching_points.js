// Run: node yousenwebview/tests/test_luban_teaching_points.js
// 74 集是 published lesson 页的只读投影，不是 74 份学习进度/练习包。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var source = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/teaching-points/teaching-points.js"),
  "utf8",
);
var definition = null;
var navigatedTo = "";
// 付费墙上限现在来自服务端 wallet.teaching_video_limit(前端不自算)。页面级 onLoad
// 测试把它 mock 成 2(3 集 payload 下,第 3 集应 locked),验证 wallet→flags→locked 的接线。
var serverTeachingVideoLimit = 2;
var walletShouldFail = false;
// 真实 flags 模块(不 mock 决策逻辑),让 resolveTeachingVideoLimit 的优先级/fail-closed 真跑。
var realFlags = require(path.join(__dirname, "../packageDeeptutor/utils/flags.js"));
var apiPayload = {
  teaching_point_universe: 3,
  teaching_topic_universe: 1,
  teaching_points: [
    { teaching_point_id: "D14:lesson:1", pack_id: "D14", title: "吊顶质量", episode_index: 1, episode_total: 3, episode_label: "上集", card_url: "https://cdn/d14/lesson.html" },
    { teaching_point_id: "D14:lesson:2", pack_id: "D14", title: "吊顶质量", episode_index: 2, episode_total: 3, episode_label: "中集", card_url: "https://cdn/d14/lesson2.html" },
    { teaching_point_id: "D14:lesson:3", pack_id: "D14", title: "吊顶质量", episode_index: 3, episode_total: 3, episode_label: "下集", card_url: "https://cdn/d14/lesson3.html" },
  ],
};
var sandbox = {
  Promise: Promise,
  Number: Number,
  Object: Object,
  String: String,
  Array: Array,
  console: console,
  require: function (request) {
    if (request === "../../../utils/api") {
      return {
        getLubanLessons: function () { return Promise.resolve(apiPayload); },
        // 付费墙上限的服务端来源:wallet.teaching_video_limit。失败态验证 fail-closed。
        getWallet: function () {
          if (walletShouldFail) return Promise.reject(new Error("wallet unavailable"));
          return Promise.resolve({ teaching_video_limit: serverTeachingVideoLimit });
        },
        unwrapResponse: function (body) { return body; },
        describeRequestError: function (_err, fallback) { return fallback; },
      };
    }
    if (request === "../../../utils/auth") return { isLoggedIn: function () { return true; } };
    if (request === "../../../utils/helpers") {
      return { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} };
    }
    if (request === "../../../utils/route") {
      return {
        lubanTeachingPoints: function () { return "/teaching-points"; },
        lubanStations: function () { return "/stations"; },
        learn: function () { return "/learn"; },
        lubanStation: function (packId, episode) { return "/station?pack_id=" + packId + "&episode=" + episode; },
      };
    }
    if (request === "../../../utils/runtime") return { redirectToLogin: function () {} };
    if (request === "../../../utils/pack-short-names") {
      return {
        shortName: function (packId, fallback) {
          return packId === "B02" ? "基坑支护" : fallback;
        },
      };
    }
    if (request === "../../../utils/surface-telemetry") {
      return { trackProductBehavior: function () {}, trackModuleView: function () {}, trackModuleExit: function () {} };
    }
    if (request === "../../../utils/flags") {
      // 用真实 flags 决策逻辑(不 mock),让 wallet 下发的 serverLimit 真正流过优先级/fail-closed。
      return realFlags;
    }
    throw new Error("unexpected require: " + request);
  },
  wx: {
    getSystemInfoSync: function () { return { statusBarHeight: 20 }; },
    navigateTo: function (payload) { navigatedTo = payload.url; },
  },
  Page: function (page) { definition = page; },
  module: { exports: {} },
  exports: {},
};
vm.runInNewContext(source, sandbox, { filename: "teaching-points.js" });

var groups = sandbox.module.exports.buildEpisodeGroups(apiPayload.teaching_points);
assert.strictEqual(groups.length, 1);
assert.strictEqual(groups[0].episodes.map(function (episode) { return episode.label; }).join("/"), "上集/中集/下集");
assert.strictEqual(groups[0].displayTitle, "吊顶质量");
assert.strictEqual(
  sandbox.module.exports.buildEpisodeGroups([
    apiPayload.teaching_points[0],
    apiPayload.teaching_points[2],
  ]).length,
  0,
  "缺 lesson2 时整套不展示，不能让用户看错序视频",
);

var orderedGroups = sandbox.module.exports.buildEpisodeGroups([
  { teaching_point_id: "B02:lesson:1", pack_id: "B02", title: "第二站", episode_index: 1, episode_total: 1, episode_label: "完整讲解", card_url: "https://cdn/b02/lesson.html" },
  { teaching_point_id: "A01:lesson:1", pack_id: "A01", title: "第一站", episode_index: 1, episode_total: 1, episode_label: "完整讲解", card_url: "https://cdn/a01/lesson.html" },
]);
assert.strictEqual(orderedGroups.map(function (group) { return group.packId; }).join("/"), "B02/A01", "前端不得按 pack_id 覆盖 API 路线顺序");
assert.strictEqual(orderedGroups[0].displayTitle, "基坑支护", "竖排卡应复用唯一显示层短名，避免长标题折列");

var colorPackIds = sandbox.module.exports.CHAPTER_LAYOUT[0].packIds;
var colorPoints = colorPackIds.map(function (packId, index) {
  return { teaching_point_id: packId + ":lesson:1", pack_id: packId, title: "测试考点" + index, episode_index: 1, episode_total: 1, episode_label: "完整讲解", card_url: "https://cdn/" + packId + "/lesson.html" };
});
var colorChapters = sandbox.module.exports.buildChapterSections(colorPoints);
assert.strictEqual(colorChapters.length, 1);
assert.strictEqual(colorChapters[0].topicCount, 8);
assert.strictEqual(colorChapters[0].lessonCount, 8);
assert.strictEqual(
  colorChapters[0].cards.map(function (card) { return card.tone; }).join("/"),
  "ink/paper/red/paper/paper/paper/red/paper",
  "C 版必须按重色行、全纸行、镜像重色行的固定节拍排列",
);
assert.strictEqual(
  sandbox.module.exports.C_TONE_PATTERN.map(function (row) { return row.join("/"); }).join("|"),
  "ink/paper/red|paper/paper/paper|red/paper/ink|paper/paper/paper",
  "C 版视觉节拍必须是强句、停顿、镜像强句、停顿",
);

var chapters = sandbox.module.exports.buildChapterSections(apiPayload.teaching_points);
assert.strictEqual(chapters.length, 1);
assert.strictEqual(chapters[0].title, "装饰与防水工程");
assert.strictEqual(chapters[0].lessonCount, 3);
assert.strictEqual(chapters[0].cards.map(function (card) { return card.tone; }).join("/"), "ink/paper/red");
assert.strictEqual(chapters[0].cards.map(function (card) { return card.labelShort; }).join("/"), "上/中/下");
assert.strictEqual(
  sandbox.module.exports.CHAPTER_LAYOUT.reduce(function (all, chapter) { return all.concat(chapter.packIds); }, []).join("/"),
  "A01/A02/B02/C01/C04/C05/C06/C07/D11/D12/D13/D14/F02/F03/F04/F05/F16/G01/G02/G03/G04/J01/R01/S01/C02/E05/K01/N01/N02/N03/Q01/Q02/Q03/S02/S05/S06/S07/X01/X02/X03",
  "五章必须显式覆盖40个正式考点且不靠API顺序猜归属",
);

// ── 免费引子 20 集上限:超出的集不丢弃,只打 locked(保住投影完整性),按全局顺序跨章计数 ──
var allPackIds = sandbox.module.exports.CHAPTER_LAYOUT.reduce(function (all, chapter) {
  return all.concat(chapter.packIds);
}, []);
var freeGatePoints = allPackIds.slice(0, 25).map(function (packId, index) {
  return { teaching_point_id: packId + ":lesson:1", pack_id: packId, title: "考点" + index, episode_index: 1, episode_total: 1, episode_label: "完整讲解", card_url: "https://cdn/" + packId + "/lesson.html" };
});
var gatedChapters = sandbox.module.exports.buildChapterSections(freeGatePoints, 20);
var gatedCards = gatedChapters.reduce(function (all, chapter) { return all.concat(chapter.cards); }, []);
assert.strictEqual(gatedCards.length, 25, "待开放的集不能被丢弃——投影完整性(可见集数==全集数)必须守住");
assert.strictEqual(gatedCards.filter(function (card) { return !card.locked; }).length, 20, "免费引子应恰好开放前 20 集");
assert.strictEqual(gatedCards.slice(0, 20).every(function (card) { return card.locked !== true; }), true, "前 20 集必须可看");
assert.strictEqual(gatedCards.slice(20).every(function (card) { return card.locked === true; }), true, "第 20 集之后必须标记待开放");

var openChapters = sandbox.module.exports.buildChapterSections(freeGatePoints, null);
var openCards = openChapters.reduce(function (all, chapter) { return all.concat(chapter.cards); }, []);
assert.strictEqual(openCards.some(function (card) { return card.locked; }), false, "开关开(limit=null)时全部解锁,无待开放");

// ── 付费墙上限决策(真实 flags.resolveTeachingVideoLimit):服务端 teaching_video_limit 驱动 ──
assert.strictEqual(realFlags.resolveTeachingVideoLimit(20), 20, "服务端下发整数 20 → 上限 20");
assert.strictEqual(realFlags.resolveTeachingVideoLimit(30), 30, "服务端下发整数 30 → 上限 30(会员等级不同上限不同)");
assert.strictEqual(realFlags.resolveTeachingVideoLimit(null), null, "服务端明确 null → 无限(全开放)");
assert.strictEqual(realFlags.resolveTeachingVideoLimit(undefined), 0, "服务端值拿不到 → fail-closed 全锁");
assert.strictEqual(realFlags.resolveTeachingVideoLimit("bad"), 0, "服务端下发非法值 → fail-closed 全锁");
assert.strictEqual(realFlags.resolveTeachingVideoLimit(-5), 0, "服务端下发负数 → fail-closed 全锁");

var page = Object.assign({}, definition);
page.data = JSON.parse(JSON.stringify(definition.data));
page.setData = function (patch) { Object.assign(this.data, patch || {}); };

(async function () {
  page.onLoad();
  await new Promise(function (resolve) { setTimeout(resolve, 0); });
  assert.strictEqual(page.data.teachingPointUniverse, 3);
  assert.strictEqual(page.data.topicUniverse, 1);
  assert.strictEqual(page.data.chapterSections[0].cards.length, 3);
  // 服务端 wallet.teaching_video_limit=2(mock):前 2 集可看,第 3 集待开放;
  // 可见集数仍 3(不丢卡,投影完整)。这条验证 wallet→flags→locked/unlockedCount 的接线。
  assert.strictEqual(page.data.unlockedCount, 2, "已开放集数应为服务端下发的上限");
  assert.strictEqual(page.data.chapterSections[0].cards[0].locked !== true, true, "第 1 集必须可看");
  assert.strictEqual(page.data.chapterSections[0].cards[2].locked, true, "第 3 集(超上限)必须待开放");

  // fail-closed 接线:服务端 wallet 请求失败 → 全锁但仍投影目录,页面不崩。
  walletShouldFail = true;
  var failPage = Object.assign({}, definition);
  failPage.data = JSON.parse(JSON.stringify(definition.data));
  failPage.setData = function (patch) { Object.assign(this.data, patch || {}); };
  failPage.onLoad();
  await new Promise(function (resolve) { setTimeout(resolve, 0); });
  assert.strictEqual(failPage.data.errorText, "", "wallet 拿不到时不应把整页判失败(教学集接口本身成功)");
  assert.strictEqual(failPage.data.chapterSections[0].cards.length, 3, "wallet 失败仍如实投影全部教学集");
  assert.strictEqual(failPage.data.unlockedCount, 0, "wallet 失败 → fail-closed 全锁,不由客户端猜权益");
  walletShouldFail = false;
  page.openEpisode({ currentTarget: { dataset: { packId: "D14", episode: 2, cardUrl: "https://cdn/d14/lesson2.html" } } });
  assert.strictEqual(navigatedTo, "/station?pack_id=D14&episode=2");
  // 待开放集点击:只提示、不跳转、不发播放埋点。
  navigatedTo = "";
  page.openEpisode({ currentTarget: { dataset: { packId: "D14", episode: 3, cardUrl: "https://cdn/d14/lesson3.html", locked: true } } });
  assert.strictEqual(navigatedTo, "", "待开放集点击不得跳转进站");

  var appConfig = fs.readFileSync(path.join(__dirname, "../app.json"), "utf8");
  var wxml = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/pages/luban/teaching-points/teaching-points.wxml"), "utf8");
  var routeSource = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/utils/route.js"), "utf8");
  var route = require(path.join(__dirname, "../packageDeeptutor/utils/route.js"));
  var packNames = require(path.join(__dirname, "../packageDeeptutor/utils/pack-short-names.js"));
  assert(appConfig.indexOf("pages/luban/teaching-points/teaching-points") >= 0, "教学集页必须注册到小程序分包");
  assert(routeSource.indexOf("pages/luban/teaching-points/teaching-points") >= 0, "登录回跳白名单必须识别教学集页");
  assert.strictEqual(route.lubanStations(), route.lubanTeachingPoints(), "所有完整路线入口必须立即归一到 C 版 74 集页面");
  assert(wxml.indexOf("chapterSections") >= 0, "74 张课卡必须由章节投影渲染");
  assert(wxml.indexOf("tp-card--{{card.tone}}") >= 0, "课卡必须消费 C 版固定色序");
  assert(wxml.indexOf("tp-card--locked") >= 0, "待开放集必须有锁态样式类");
  assert(wxml.indexOf("data-locked") >= 0, "openEpisode 需能从 dataset 判定待开放集");
  assert(wxml.indexOf("待开放") >= 0, "待开放集必须如实展示文案,不冒充可播放");
  assert.strictEqual(Object.keys(packNames.SHORT_MAP).length, 40, "40 个当前考点都应有单列竖排短名");
  assert.strictEqual(packNames.shortName("C02", ""), "进度计量", "显示短名不得沿用旧版错位映射");
  assert(Object.keys(packNames.SHORT_MAP).every(function (packId) { return packNames.SHORT_MAP[packId].length <= 5; }), "竖排短名不得折成两列");
  assert.strictEqual(route.lubanStation("D14", 2), "/packageDeeptutor/pages/luban/station/station?pack_id=D14&episode=2");
  console.log("PASS test_luban_teaching_points.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
