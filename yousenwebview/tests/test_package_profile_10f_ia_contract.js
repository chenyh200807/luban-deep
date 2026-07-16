// test_package_profile_10f_ia_contract.js — 我的 tab 第10轮 10f IA 契约
//
// 权威：docs/plan/鲁班移动端提分闭环/2026-07-02-luban-five-module-ia-frontend-brief.md
//      + 设计资产第10轮定稿 10f 区块 + owner 口径（免费额度无读接口→静态降级）。
// 铁律：历史/学习统计绝不放「我的」；学习统计只做去学情页的入口；
//      点亮判定唯一权威 = utils/learn-view-model；缺字段降级不造数；文案禁审视词。
//
// Run: node yousenwebview/tests/test_package_profile_10f_ia_contract.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function flush() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

var profileDir = path.join(__dirname, "../packageDeeptutor/pages/profile");
var profileJs = fs.readFileSync(path.join(profileDir, "profile.js"), "utf8");
var profileWxml = fs.readFileSync(path.join(profileDir, "profile.wxml"), "utf8");
var profileWxss = fs.readFileSync(path.join(profileDir, "profile.wxss"), "utf8");
var paperInkWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/styles/paper-ink.wxss"),
  "utf8",
);

// ── IA 铁律：学习统计并入学情，不在我的单列 ──────────────────
assert(!/getBadges/.test(profileJs), "profile must not load badges (学习统计并入学情)");
assert(!/onBadgeTap/.test(profileJs), "profile must not keep badge interactions");
assert(!/我的成就/.test(profileWxml), "profile must not render an achievements section");
assert(!/badges-grid/.test(profileWxml), "profile must not render the badge grid");
assert(!/Lv\.\{\{/.test(profileWxml) && !/\{\{xp\}\}/.test(profileWxml), "profile must not render Lv/XP stats");
assert(
  /id:\s*"diagnostic",\s*title:\s*"学习统计"/.test(profileJs),
  "profile should keep exactly one 学习统计 entry that routes to the report page",
);

// ── IA 铁律：历史绝不放「我的」──────────────────────────────
assert(!/route\.history\(/.test(profileJs), "profile must not link to conversation history");
assert(!/id:\s*"history"/.test(profileJs), "profile link items must not contain a history entry");
assert(!/link-title">历史/.test(profileWxml), "profile wxml must not surface a history entry");

// ── 文案禁审视词（全产品铁律）───────────────────────────────
["看穿", "识破", "揭穿", "露馅"].forEach(function (word) {
  assert(
    profileJs.indexOf(word) < 0 && profileWxml.indexOf(word) < 0 && profileWxss.indexOf(word) < 0,
    "profile copy must not contain the forbidden word " + word,
  );
});

// ── 10f 结构：路线卡 / 复习提醒 / 考试日期旁注 / 底部铭牌 ────
assert(/class="pk-card route-card"/.test(profileWxml), "profile should render the route card");
assert(
  /wx:if="\{\{routeCard\}\}"/.test(profileWxml),
  "route count claims must be gated on real read-model data (no fabricated counts)",
);
assert(
  /learn-view-model/.test(profileJs) && !/practiced|mastered|dormant/.test(profileJs),
  "lit-station authority must stay in learn-view-model (no second lifecycle decider in profile)",
);
assert(/会员解锁的是/.test(profileWxml) && /不是题库/.test(profileWxml), "route card should keep the membership copy");
assert(/永久可回炉，不计费/.test(profileWxml), "route card should keep the free-review-forever statement");
assert(/不按题收费/.test(profileWxml), "profile should keep the pricing footnote");
assert(/bindchange="onReminderChange"/.test(profileWxml), "profile should keep the review reminder switch");
assert(/review_reminder/.test(profileJs), "reminder switch must persist the backend review_reminder field");
assert(/用于安排你的复习节奏/.test(profileWxml), "exam date row should carry the scheduling side note");
assert(/exam_date/.test(profileJs), "exam date must persist through profile settings");
assert(/TODO\(time_budget\)/.test(profileJs), "daily target must carry the time_budget mapping TODO");

// ── 纸墨朱竹 token（共享 authority，页面不得复制 palette）────
assert(
  /@import\s+"\/packageDeeptutor\/styles\/paper-ink\.wxss"/.test(profileWxss),
  "profile must consume the shared paper-ink authority",
);
assert(/class="[^"]*\bpaper\b/.test(profileWxml), "profile root must mount the paper theme");
assert(/\.paper\s*\{[^}]*--pk-paper:\s*#1c1a15/.test(paperInkWxss), "dark paper-ink tokens must match the 10f2 palette");
assert(/\.paper\.light\s*\{[^}]*--pk-paper:\s*#f5f3ec/.test(paperInkWxss), "light paper-ink tokens must match the 10f palette");
assert(!/--pk-card:|--pk-red:/.test(profileWxss), "profile must not keep a second palette copy");

// ── 动态契约：免费档静态降级 + 路线卡诚实投影 ────────────────
function loadProfilePage(apiOverrides) {
  var pageDef = null;
  var navigations = [];
  var api = Object.assign(
    {
      unwrapResponse: function (raw) {
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({ username: "chenyh2008", exam_date: "2026-09-19" });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 0 });
      },
      getUsage: function () {
        return Promise.resolve({ windows: [] });
      },
      getLedger: function () {
        return Promise.resolve({ entries: [] });
      },
      getLearningReport: function () {
        return Promise.resolve({
          pack_lifecycle: {
            packs: {
              F16: { lifecycle_state: "practiced" },
              N01: { lifecycle_state: "exposed" },
            },
          },
        });
      },
      getLubanLessons: function () {
        return Promise.resolve({
          lessons: [{ pack_id: "F16", title: "现浇结构验收" }],
        });
      },
      updateSettings: function () {
        return Promise.resolve({});
      },
    },
    apiOverrides || {},
  );
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      getFileSystemManager: function () {
        return { saveFile: function () {} };
      },
      chooseMedia: function () {},
      showToast: function () {},
      showModal: function () {},
      navigateTo: function (payload) {
        navigations.push(payload);
      },
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") return api;
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
          isDarkOr: function (fb) {
            return fb !== "light";
          },
          syncTabBar: function () {},
          vibrate: function () {},
        };
      }
      if (request === "../../utils/runtime") {
        return {
          getWorkspaceBack: function () {
            return null;
          },
          consumeWorkspaceBack: function () {
            return null;
          },
          setWorkspaceBack: function () {},
          markGoHome: function () {},
          redirectToLogin: function () {},
          logout: function () {},
        };
      }
      if (request === "../../utils/route") {
        return {
          profile: function () {
            return "/packageDeeptutor/pages/profile/profile";
          },
          billing: function () {
            return "/packageDeeptutor/pages/billing/billing";
          },
          assessment: function () {
            return "/packageDeeptutor/pages/assessment/assessment";
          },
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          terms: function () {
            return "/packageDeeptutor/pages/legal/terms";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
          learn: function () {
            return "/packageDeeptutor/pages/learn/learn";
          },
          feedback: function () {
            return "/packageDeeptutor/pages/feedback/feedback?source=profile";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          getWorkspaceFlags: function () {
            return {};
          },
          ensureFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return false;
          },
        };
      }
      if (request === "../../utils/learn-view-model") {
        // 纯函数视图模型（点亮判定单一权威），直接用真模块
        return require("../packageDeeptutor/utils/learn-view-model");
      }
      throw new Error("unexpected require: " + request);
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(profileDir, "profile.js"), "utf8"),
    sandbox,
    { filename: "packageDeeptutor/pages/profile/profile.js" },
  );
  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, navigations: navigations };
}

(async function main() {
  // 1) 免费档（balance 0）→ 静态规则说明，绝不显示自算计数
  var freeUser = loadProfilePage();
  freeUser.page.onLoad();
  freeUser.page.onShow();
  await flush();
  await flush();
  assert(freeUser.page.data.freeTier === true, "zero wallet balance should enter free tier presentation");
  assert(
    freeUser.page.data.usagePrimaryLabel === "免费体验中",
    "free tier should show the honest static label instead of 剩余 0%",
  );
  assert(freeUser.page.data.usageRows.length === 0, "free tier should not project wallet percentage rows");

  // 2) 路线卡：pack_lifecycle 1 站 practiced → 1/40 已点亮（单一权威口径）
  assert(
    freeUser.page.data.routeCard && freeUser.page.data.routeCard.label === "路线 1 / 40 站已点亮",
    "route card should project lit stations from pack_lifecycle via learn-view-model",
  );
  assert(
    freeUser.page.data.examDateLabel.indexOf("考试日 9 月 19 日") === 0,
    "user subtitle should derive from exam_date",
  );

  // 3) 会员（balance > 0）→ 钱包百分比展示，免费块关闭
  var member = loadProfilePage({
    getWallet: function () {
      return Promise.resolve({ balance: 88 });
    },
    getLedger: function () {
      return Promise.resolve({ entries: [{ delta: 100 }] });
    },
  });
  member.page.onLoad();
  member.page.onShow();
  await flush();
  await flush();
  assert(member.page.data.freeTier === false, "positive wallet balance should keep the member wallet view");
  assert(member.page.data.usagePrimaryLabel === "剩余 88%", "member view keeps the wallet percentage label");

  // 4) learning-report 读不到 → routeCard 为 null，不声称任何点亮数
  var degraded = loadProfilePage({
    getLearningReport: function () {
      return Promise.reject(new Error("report unavailable"));
    },
  });
  degraded.page.onLoad();
  degraded.page.onShow();
  await flush();
  await flush();
  assert(degraded.page.data.routeCard === null, "route card must stay silent when pack_lifecycle is unreadable");

  // 5) 学习统计入口 → 学情页（不在我的单列）
  var nav = loadProfilePage();
  nav.page.onLoad();
  nav.page.onShow();
  await flush();
  nav.page.openLink({ currentTarget: { dataset: { id: "diagnostic" } } });
  assert(
    nav.navigations.some(function (n) {
      return n.url === "/packageDeeptutor/pages/report/report";
    }),
    "学习统计 entry should navigate to the report (学情) page",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_package_profile_10f_ia_contract.js (" + pass + " assertions)");
})().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
