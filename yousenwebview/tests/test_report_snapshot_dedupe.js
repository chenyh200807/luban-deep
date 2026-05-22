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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push(
      "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
    );
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadReportPage(stubs) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
    "utf8",
  );
  var pageDef = null;
  var storage = {};
  var storageWrites = [];
  var toastCalls = [];
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Page: function (def) {
      pageDef = def;
    },
    wx: {
      nextTick: function (fn) {
        if (typeof fn === "function") fn();
      },
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storageWrites.push({ key: key, value: value });
        storage[key] = value;
      },
      showModal: function () {},
      showToast: function (opts) {
        toastCalls.push(opts || {});
      },
      navigateTo: function () {},
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") return stubs.api;
      if (request === "../../utils/auth") return stubs.auth;
      if (request === "../../utils/helpers") return stubs.helpers;
      if (request === "../../utils/runtime") return stubs.runtime;
      if (request === "../../utils/route") return stubs.route;
      if (request === "../../utils/flags") return stubs.flags;
      if (request === "../../utils/learning-report-view-model") {
        return require(path.join(
          __dirname,
          "../packageDeeptutor/utils/learning-report-view-model.js",
        ));
      }
      if (request === "../../utils/taxonomy") {
        return require(path.join(
          __dirname,
          "../packageDeeptutor/utils/taxonomy.js",
        ));
      }
      return {};
    },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/report/report.js",
  });
  pageDef.__sandbox = {
    storage: storage,
    storageWrites: storageWrites,
    toastCalls: toastCalls,
  };
  return pageDef;
}

function createPageInstance(pageDef) {
  var page = Object.assign({}, pageDef);
  page.data = Object.assign({}, pageDef.data);
  page.setData = function (patch) {
    this.data = Object.assign({}, this.data, patch);
  };
  page._ensureRadarRendered = function () {};
  return page;
}

(async function main() {
  var reportSource = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
    "utf8",
  );
  assert(
    reportSource.indexOf("schemaVersion === 1 || schemaVersion === 2") >= 0,
    "yousen report page must accept learning-report schema v1 and v2 payloads",
  );
  assert(
    reportSource.indexOf("REPORT_UNIFIED_READ_TIMEOUT_MS = 8000") >= 0 &&
      reportSource.indexOf(
        "_reportOptionalRead(api.getLearningReport(100, optionalReadOpts), REPORT_UNIFIED_READ_TIMEOUT_MS)",
      ) >= 0,
    "yousen unified learning-report read must not fall back before a normal 3.5s+ mobile response can return",
  );
  assert(
    reportSource.indexOf("CHAPTER_CODE_LABELS") < 0 &&
      reportSource.indexOf("LEARNING_BRAIN_OBJECT_LABELS") < 0 &&
      reportSource.indexOf("LEARNING_BRAIN_EDGE_LABELS") < 0 &&
      reportSource.indexOf("LEARNING_BRAIN_ERROR_LABELS") < 0,
    "package report page should not keep Learning Brain taxonomy truth in the UI layer",
  );

  // G5 静态契约：yousen 学情页不得消费 legacy_compat（plan §数据契约）
  assert(
    reportSource.indexOf("legacy_compat") < 0,
    "yousen report page must not consume legacy_compat — it is for backend reconciliation only",
  );
  // G5 静态契约：fallback 必须只在 unified snapshot 缺失时触发（_loadReportSnapshot 返回 null）
  assert(
    reportSource.indexOf("if (!report) {") >= 0 &&
      reportSource.indexOf("_hydrateFromUnifiedReport") >= 0,
    "yousen _loadReportSnapshot must short-circuit when unified report payload is unavailable",
  );
  assert(
    reportSource.indexOf('return "综合能力"') < 0 &&
      reportSource.indexOf('return "知识点 " + text.toUpperCase()') < 0 &&
      reportSource.indexOf('require("../../utils/taxonomy")') >= 0,
    "yousen report page must route chapter taxonomy through the shared utils/taxonomy authority — must NOT expose raw chapter codes or collapse them into the meaningless 综合能力 label",
  );
  assert(
    reportSource.indexOf('code === "M01"') >= 0 &&
      reportSource.indexOf('code === "M10"') >= 0,
    "yousen report stale-data fallback should cover the full MCQ error taxonomy",
  );

  await run(
    "report onShow should hydrate all state from one snapshot without duplicate assessment reads",
    async function () {
      var counters = {
        report: 0,
        today: 0,
        home: 0,
        assessment: 0,
        mastery: 0,
        brain: 0,
        radar: 0,
        saveMistake: 0,
      };
      var pageDef = loadReportPage({
        api: {
          unwrapResponse: function (raw) {
            return raw;
          },
          getLearningReport: async function () {
            counters.report += 1;
            return {
              ok: true,
              schema_version: 2,
              authority: {
                read_model: "learning-report-read-model",
                progress_source: "learner_memory_events.learning_evidence",
                learning_brain_source: "dry_run_learning_evidence",
                deprecated_page_sources: [],
              },
              degraded: false,
              degraded_sources: [],
              source_status: {},
              freshness: {
                event_count: 2,
                unknown_date_count: 0,
                window_truncated: false,
              },
              overview: {
                today_done: 6,
                daily_target: 12,
                streak_days: 3,
                due_today_count: 2,
                weak_node_count: 1,
                focus_hint: "继续推进防水工程专项训练",
                learner_level: "intermediate",
                study_tip: "先补防水工程",
              },
              progress_feedback: {
                summary: "后端下发：近 3 天累计完成 18 题，比前 3 天多 6 题",
                insight: "后端下发：系统已经把“防水工程”锁定为当前主攻",
                cards: [
                  {
                    label: "近 3 天完成",
                    value: "18题",
                    detail: "比前 3 天多 6 题",
                    tone_class: "tone-good",
                  },
                  {
                    label: "连续学习",
                    value: "3天",
                    detail: "学习节奏正在形成",
                    tone_class: "tone-good",
                  },
                ],
                milestones: [
                  {
                    title: "刚完成一次专题梳理",
                    detail: "最近完成了屋面卷材铺贴、节点收头的梳理",
                    tone_class: "tone-good",
                  },
                ],
              },
              study_plan: {
                focus_topic: "防水工程",
                priority_task: "后端下发：先补 3 个待复习点，再做 5 题巩固",
                study_method:
                  "后端下发：先梳理防水工程，再做真题强化，最后回看错题",
                time_budget: "约 18 分钟，先复习后加练",
                coach_note: "后端下发：这是 learner-state 统一生成的作战建议",
              },
              radar_dimensions: [
                { name: "建筑构造", value: 0.8 },
                { name: "防水工程", value: 0.2 },
              ],
              mastery: {
                overall_mastery: 50,
                groups: [
                  {
                    name: "需要加强",
                    avg_mastery: 20,
                    chapters: [{ name: "防水工程", mastery: 20 }],
                  },
                ],
                hotspots: [{ name: "防水工程", mastery: 20 }],
                review_summary: { total_due: 2, overdue_count: 1 },
              },
              learning_brain: await this.getLearningBrainProjection(),
              learner_facing: {
                summary: {
                  title: "今日学习复盘",
                  headline: "最近 2 次练习里，重点关注主体结构。",
                  today_done: 2,
                  recent_three_done: 2,
                  primary_focus: "主体结构",
                  weak_count: 1,
                },
                recent_attempts: [
                  {
                    key: "attempt-0",
                    attempt_ref: "signed-ref",
                    subject_id: "construction_exam_1",
                    bot_id: "construction-exam",
                    time_label: "今天 09:20",
                    title: "关于主体结构验收条件的说法，正确的是？",
                    question_text: "关于主体结构验收条件的说法，正确的是？",
                    concept: "主体结构",
                    result_label: "答错",
                    tone: "wrong",
                    answer_line: "你选：A（错误做法）；正确：B（正确做法）",
                    diagnosis: "多选漏选",
                    diagnosis_detail: "你漏掉了需要同时满足的验收条件。",
                    explanation:
                      "解析：先看题干问的是验收条件，再逐项核对规范表述，不能只按经验选相近选项。",
                    evidence_label: "最近一次批改",
                    collectable: true,
                  },
                ],
                diagnoses: [
                  {
                    key: "主体结构::多选漏选",
                    level_label: "需要重点补",
                    title: "主体结构：多选漏选",
                    concept: "主体结构",
                    error: "多选漏选",
                    meta: "最近出现 2 次",
                    detail: "多选题容易只选一个确定项，遗漏并列正确条件。",
                    action: "先做 3 道主体结构相关辨析题",
                    count: 2,
                  },
                ],
                training_loops: [
                  {
                    key: "loop-0",
                    title: "多选漏选",
                    from: "错因：主体结构 / 多选漏选",
                    training: "训练：先做 3 道主体结构相关辨析题",
                    outcome: "变化：仍需通过下一轮训练验证",
                    tone: "not-improved",
                  },
                ],
                next_action: {
                  title: "先做 3 道“主体结构”专项题",
                  subtitle: "目标：把“多选漏选”这一类错误拉回主线",
                  cta: "开始训练",
                  estimated_minutes: 8,
                },
              },
            };
          },
          saveMistakeBookItem: async function (payload) {
            counters.saveMistake += 1;
            counters.savedMistakePayload = payload;
            return { ok: true, item: { etag: "etag-1" } };
          },
          getTodayProgress: async function () {
            counters.today += 1;
            return { today_done: 6, daily_target: 12, streak_days: 3 };
          },
          getHomeDashboard: async function () {
            counters.home += 1;
            return {
              review: { due_today: 2 },
              mastery: { weak_nodes: [{ name: "防水工程" }] },
              today: { hint: "继续推进防水工程专项训练" },
              study_plan: {
                focus_topic: "防水工程",
                priority_task: "后端下发：先补 3 个待复习点，再做 5 题巩固",
                study_method:
                  "后端下发：先梳理防水工程，再做真题强化，最后回看错题",
                time_budget: "约 18 分钟，先复习后加练",
                coach_note: "后端下发：这是 learner-state 统一生成的作战建议",
              },
              progress_feedback: {
                summary: "后端下发：近 3 天累计完成 18 题，比前 3 天多 6 题",
                insight: "后端下发：系统已经把“防水工程”锁定为当前主攻",
                cards: [
                  {
                    label: "近 3 天完成",
                    value: "18题",
                    detail: "比前 3 天多 6 题",
                    tone_class: "tone-good",
                  },
                  {
                    label: "连续学习",
                    value: "3天",
                    detail: "学习节奏正在形成",
                    tone_class: "tone-good",
                  },
                ],
                milestones: [
                  {
                    title: "刚完成一次专题梳理",
                    detail: "最近完成了屋面卷材铺贴、节点收头的梳理",
                    tone_class: "tone-good",
                  },
                ],
              },
            };
          },
          getAssessmentProfile: async function () {
            counters.assessment += 1;
            return {
              level: "intermediate",
              chapter_mastery: {
                建筑构造: { name: "建筑构造", mastery: 80 },
                防水工程: { name: "防水工程", mastery: 20 },
              },
              diagnostic_feedback: {
                learner_profile: {
                  study_tip: "先补防水工程",
                },
              },
            };
          },
          getMasteryDashboard: async function () {
            counters.mastery += 1;
            return {
              overall_mastery: 50,
              groups: [
                {
                  name: "需要加强",
                  avg_mastery: 20,
                  chapters: [{ name: "防水工程", mastery: 20 }],
                },
              ],
              hotspots: [{ name: "防水工程", mastery: 20 }],
              review_summary: { total_due: 2, overdue_count: 1 },
            };
          },
          getLearningBrainProjection: async function () {
            counters.brain += 1;
            return {
              event_count: 2,
              created_claim_count: 1,
              typed_graph_edge_count: 7,
              compiled_objects: {
                "concept:1A432000": {
                  current_truth: "专项施工方案程序存在重复漏点",
                  evidence_level: "L1_repeated",
                  supporting_event_ids: ["evt1", "evt2"],
                },
              },
              visible_sections: {
                current_truth: [
                  {
                    object_key: "concept:1A432000",
                    current_truth:
                      "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                    evidence_level: "L1_repeated",
                    evidence_level_label: "重复出现",
                    display_label: "知识点",
                    display_title:
                      "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                    display_meta: "知识点：工程招标投标与合同管理",
                    supporting_event_ids: ["evt1", "evt2"],
                  },
                  {
                    object_key:
                      "error:我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题:M07",
                    current_truth:
                      "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 上出现 M07 错因",
                    evidence_level: "L0_observed",
                    evidence_level_label: "单次观察",
                    display_label: "错因",
                    display_title:
                      "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 上出现 M07 错因",
                    display_meta: "错因：错因 M07",
                    supporting_event_ids: ["e8b7f3a8123456782c60"],
                  },
                ],
                evidence_flow: [
                  {
                    event_id: "evt1",
                    edge_type: "question_tests_concept",
                    display_label: "题目考查知识点",
                    display_title: "题目考查知识点",
                    display_path:
                      "案例题：第 1 题 → 知识点：工程招标投标与合同管理",
                  },
                  {
                    event_id: "evt2",
                    edge_type: "training_not_improved_error",
                    display_label: "训练后仍需巩固",
                    display_title: "训练后仍需巩固",
                    display_path:
                      "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
                  },
                  {
                    event_id: "e8b7f3a8123456782c60",
                    edge_type: "error_points_to_training",
                    display_title:
                      "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 上出现 M06 错因",
                    display_path:
                      "训练建议：practice / 我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 -> 案例题： q_1",
                  },
                ],
                next_training: [
                  {
                    concept_id: "1A432000",
                    error_code: "E02",
                    display_label: "训练建议",
                    display_title:
                      "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                    display_meta:
                      "知识点：工程招标投标与合同管理；错因：采分点遗漏；案例题补强",
                  },
                ],
              },
              weak_points: [],
              typed_graph_edges: [
                {
                  edge_type: "question_tests_concept",
                  from: { id: "case-1", type: "question" },
                  to: { id: "1A432000", type: "concept" },
                  evidence_event_id: "evt1",
                  display_title: "题目考查知识点",
                  display_path:
                    "案例题：第 1 题 → 知识点：工程招标投标与合同管理",
                },
              ],
              graph_chain: {
                training_uses_question: [
                  {
                    edge_type: "training_uses_question",
                    from: {
                      id: "1A432000:E02:case_repair",
                      type: "next_training",
                    },
                    to: { id: "case-2", type: "question" },
                    reason_edge_event_id: "evt2",
                    display_path: "训练建议：案例题补强 → 案例题：第 2 题",
                  },
                ],
                training_not_improved_error: [
                  {
                    edge_type: "training_not_improved_error",
                    from: {
                      id: "1A432000:E02:case_repair",
                      type: "next_training",
                    },
                    to: { id: "1A432000:E02", type: "error" },
                    question_id: "case-2",
                    reason_edge_event_id: "evt2",
                    display_meta:
                      "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
                    display_path:
                      "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
                  },
                ],
              },
            };
          },
          getRadarData: async function () {
            counters.radar += 1;
            return {
              dimensions: [{ label: "防水工程", score: 20, value: 0.2 }],
            };
          },
        },
        auth: {
          getUserId: function () {
            return "report-user";
          },
        },
        helpers: {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
          isDark: function () {
            return true;
          },
          syncTabBar: function () {},
          vibrate: function () {},
        },
        runtime: {
          getWorkspaceBack: function () {
            return null;
          },
          checkAuth: function (cb) {
            cb();
          },
        },
        route: {
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          billing: function () {
            return "/packageDeeptutor/pages/billing/billing";
          },
          assessment: function () {
            return "/packageDeeptutor/pages/assessment/assessment";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        },
        flags: {
          ensureFeatureEnabled: function () {
            return true;
          },
          isFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        },
      });
      var page = createPageInstance(pageDef);

      await page._loadReportPage();

      assert(
        counters.report === 1,
        "report bootstrap should read unified learning report once",
      );
      assert(
        counters.today === 0,
        "report page should not read legacy today progress directly",
      );
      assert(
        counters.home === 0,
        "report page should not read legacy homepage dashboard directly",
      );
      assert(
        counters.assessment === 0,
        "report page should not read legacy assessment profile directly",
      );
      assert(
        counters.mastery === 0,
        "report page should not read legacy mastery dashboard directly",
      );
      assert(
        counters.brain === 1,
        "mock learning report should compose Learning Brain once",
      );
      assert(
        counters.radar === 0,
        "positive assessment profile should avoid dedicated radar fallback",
      );
      assert(
        page.data.learnerLevel === "中级",
        "report bootstrap should hydrate overview from shared snapshot",
      );
      assert(
        page.data.avgScore === 50,
        "report bootstrap should hydrate radar from shared assessment snapshot",
      );
      assert(
        page.data.learnerStageTitle === "中级阶段",
        "report bootstrap should expose a user-facing learner stage title",
      );
      assert(
        page.data.battlePlan && page.data.battlePlan.focusTopic === "防水工程",
        "report bootstrap should hydrate AI battle plan focus from backend study plan authority",
      );
      assert(
        page.data.battlePlan &&
          page.data.battlePlan.priorityTask ===
            "后端下发：先补 3 个待复习点，再做 5 题巩固",
        "report bootstrap should prefer backend study plan over local battle-plan synthesis",
      );
      assert(
        page.data.battlePlan &&
          page.data.battlePlan.coachNote ===
            "后端下发：这是 learner-state 统一生成的作战建议",
        "report bootstrap should preserve backend coach note from study plan authority",
      );
      assert(
        page.data.progressSummary ===
          "后端下发：近 3 天累计完成 18 题，比前 3 天多 6 题",
        "report bootstrap should prefer backend progress feedback summary over local synthesis",
      );
      assert(
        page.data.progressInsight ===
          "后端下发：系统已经把“防水工程”锁定为当前主攻",
        "report bootstrap should hydrate backend progress feedback insight",
      );
      assert(
        Array.isArray(page.data.progressCards) &&
          page.data.progressCards.length === 2,
        "report bootstrap should prefer backend progress feedback cards over local fallback cards",
      );
      assert(
        Array.isArray(page.data.progressMilestones) &&
          page.data.progressMilestones.length === 1,
        "report bootstrap should hydrate backend progress milestones",
      );
      assert(
        Array.isArray(page.data.learningBrainChains) &&
          page.data.learningBrainChains[0] &&
          page.data.learningBrainChains[0].outcome === "本次训练结果：未改善",
        "report bootstrap should expose Learning Brain error -> training -> not-improved chain",
      );
      assert(
        page.data.learningReviewSummary &&
          page.data.learningReviewSummary.headline.indexOf("主体结构") >= 0,
        "report page should hydrate learner-facing review summary from unified read model",
      );
      assert(
        Array.isArray(page.data.learningAttemptCards) &&
          page.data.learningAttemptCards[0] &&
          page.data.learningAttemptCards[0].questionText.indexOf(
            "主体结构验收",
          ) >= 0 &&
          page.data.learningAttemptCards[0].answerLine.indexOf("你选：") >= 0 &&
          page.data.learningAttemptCards[0].explanation.indexOf("解析：") >= 0,
        "Learning Brain evidence should point to concrete answer records with answer and explanation",
      );
      assert(
        Array.isArray(page.data.learningDiagnosisCards) &&
          page.data.learningDiagnosisCards[0] &&
          page.data.learningDiagnosisCards[0].action.indexOf("主体结构") >= 0,
        "current truth should expose learner-facing weakness and action instead of graph-only evidence",
      );
      assert(
        Array.isArray(page.data.learningTrainingLoops) &&
          page.data.learningTrainingLoops[0] &&
          page.data.learningTrainingLoops[0].outcome.indexOf("仍需") >= 0,
        "training loop should preserve wrong cause -> training -> outcome chain in learner-facing language",
      );
      // 错题集 authority 收敛到云端 `learner_mistake_book_items`（计划文档
      // 2026-05-21-luban-learning-report-world-class-optimization-plan.md §-1.2 #3）。
      // yousen 端不允许用 wx storage 充当第二套 truth source。
      assert(
        !("mistakeBookCount" in page.data) &&
          !("mistakeBookItems" in page.data),
        "page state must not carry local mistake-book authority fields",
      );
      var preToastCallCount = pageDef.__sandbox.toastCalls.length;
      var preStorageWriteCount = pageDef.__sandbox.storageWrites.length;
      await page.toggleMistakeBookmark({
        currentTarget: {
          dataset: { key: page.data.learningAttemptCards[0].key },
        },
      });
      await flushPromises();
      assert(
        pageDef.__sandbox.storageWrites.length === preStorageWriteCount,
        "toggleMistakeBookmark must not write to wx storage; mistake book authority lives in cloud `learner_mistake_book_items`",
      );
      assert(counters.saveMistake === 1, "toggleMistakeBookmark must call the cloud mistake-book authority");
      assert(
        counters.savedMistakePayload &&
          counters.savedMistakePayload.attempt_ref === "signed-ref" &&
          counters.savedMistakePayload.subject_id === "construction_exam_1",
        "mistake-book save should send the attempt ref and backend-provided subject id",
      );
      var emittedToasts = pageDef.__sandbox.toastCalls.slice(preToastCallCount);
      assert(
        emittedToasts.length === 1 &&
          String(emittedToasts[0].title || "").indexOf("已收藏") >= 0,
        "toggleMistakeBookmark must surface cloud save success",
      );
      assert(
        !("mistakeBookCount" in page.data) &&
          !("mistakeBookItems" in page.data),
        "toggleMistakeBookmark must not introduce mistakeBook* fields into page state",
      );
      assert(
        !page.data.learningAttemptCards.some(function (card) {
          return (
            card && Object.prototype.hasOwnProperty.call(card, "bookmarked")
          );
        }),
        "attempt cards must not carry a local-only bookmarked flag (cloud authority will own this)",
      );
      assert(
        page.data.learningBrainTruths[0] &&
          page.data.learningBrainTruths[0].levelLabel === "重复出现" &&
          page.data.learningBrainTruths[0].meta.indexOf(
            "工程招标投标与合同管理",
          ) >= 0,
        "Learning Brain truth should expose learner-facing evidence level and taxonomy label",
      );
      assert(
        page.data.learningBrainEvidence[0] &&
          page.data.learningBrainEvidence[0].type === "题目考查知识点" &&
          page.data.learningBrainEvidence[0].path.indexOf(
            "知识点：工程招标投标与合同管理",
          ) >= 0,
        "Learning Brain evidence should translate typed graph labels before rendering",
      );
      assert(
        page.data.learningBrainChains[0] &&
          page.data.learningBrainChains[0].title.indexOf("采分点遗漏") >= 0 &&
          page.data.learningBrainChains[0].training.indexOf("案例题补强") >= 0,
        "Learning Brain chain should hide raw graph ids from learner-facing copy",
      );
      assert(
        JSON.stringify(page.data).indexOf("concept:1A432000") < 0 &&
          JSON.stringify(page.data).indexOf("question_tests_concept") < 0,
        "Learning Brain report state should prefer backend display fields over machine taxonomy codes",
      );
      assert(
        JSON.stringify(page.data).indexOf("M07") < 0 &&
          JSON.stringify(page.data).indexOf("M06") < 0 &&
          JSON.stringify(page.data).indexOf("e8b7f3a8") < 0 &&
          JSON.stringify(page.data).indexOf("practice /") < 0 &&
          JSON.stringify(page.data).indexOf("q_1") < 0,
        "Learning Brain report state should hide stale backend raw error codes, event ids, and training ids",
      );
      assert(
        JSON.stringify(page.data).indexOf("主体结构") >= 0 &&
          JSON.stringify(page.data).indexOf("多选错选") >= 0 &&
          JSON.stringify(page.data).indexOf("多选漏选") >= 0,
        "stale backend Learning Brain fields should still become learner-readable Chinese copy",
      );
    },
  );

  await run(
    "_load* with a unified snapshot must not touch legacy endpoints (G5)",
    async function () {
      var counters = { mastery: 0, assessment: 0, radar: 0, brain: 0 };
      var pageDef = loadReportPage({
        api: {
          unwrapResponse: function (raw) {
            return raw;
          },
          getMasteryDashboard: async function () {
            counters.mastery += 1;
            return {};
          },
          getAssessmentProfile: async function () {
            counters.assessment += 1;
            return {};
          },
          getRadarData: async function () {
            counters.radar += 1;
            return { dimensions: [] };
          },
          getLearningBrainProjection: async function () {
            counters.brain += 1;
            return {};
          },
        },
        auth: {},
        helpers: {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
        },
        runtime: {},
        route: {},
        flags: {},
      });
      var page = createPageInstance(pageDef);
      var stubSnapshot = {
        mastery: {},
        assessment: {},
        home: {},
        progress: {},
        learningBrain: {},
      };

      await page._loadMastery(stubSnapshot);
      await page._loadRadar(stubSnapshot);
      await page._loadLearningBrain(stubSnapshot);
      await page._loadOverview(stubSnapshot);

      assert(
        counters.mastery === 0,
        "unified snapshot present → _loadMastery must NOT call legacy mastery dashboard",
      );
      assert(
        counters.assessment === 0,
        "unified snapshot present → _loadRadar/_loadOverview must NOT call legacy assessment profile",
      );
      assert(
        counters.radar === 0,
        "unified snapshot present → _loadRadar must NOT call legacy radar API",
      );
      assert(
        counters.brain === 0,
        "unified snapshot present → _loadLearningBrain must NOT call legacy brain projection",
      );
    },
  );

  await run(
    "unified payload failure triggers degraded fallback with hint (G5)",
    async function () {
      var counters = { report: 0, mastery: 0, assessment: 0, brain: 0 };
      var pageDef = loadReportPage({
        api: {
          unwrapResponse: function (raw) {
            return raw;
          },
          getLearningReport: async function () {
            counters.report += 1;
            // 模拟 5xx / payload contract 断裂 → 返回 null 让 _reportOptionalRead 触发 fallback
            throw new Error("simulated 5xx");
          },
          getTodayProgress: async function () {
            return { today_done: 1, daily_target: 5, streak_days: 0 };
          },
          getHomeDashboard: async function () {
            return {
              review: { due_today: 0 },
              mastery: { weak_nodes: [] },
              today: { hint: "" },
            };
          },
          getAssessmentProfile: async function () {
            counters.assessment += 1;
            return { level: "beginner", chapter_mastery: {} };
          },
          getMasteryDashboard: async function () {
            counters.mastery += 1;
            return {
              overall_mastery: 0,
              groups: [],
              hotspots: [],
              review_summary: { total_due: 0 },
            };
          },
          getLearningBrainProjection: async function () {
            counters.brain += 1;
            return {};
          },
          getRadarData: async function () {
            return { dimensions: [] };
          },
        },
        auth: {
          getUserId: function () {
            return "report-user";
          },
        },
        helpers: {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
          isDark: function () {
            return false;
          },
          syncTabBar: function () {},
        },
        runtime: {
          getWorkspaceBack: function () {
            return null;
          },
          checkAuth: function (cb) {
            cb();
          },
        },
        route: {
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        },
        flags: {
          ensureFeatureEnabled: function () {
            return true;
          },
          isFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        },
      });
      var page = createPageInstance(pageDef);

      await page._loadReportPage();

      assert(
        counters.report === 1,
        "_loadReportPage should attempt unified endpoint exactly once",
      );
      assert(
        page.data.reportFallbackActive === true,
        "unified payload failure must mark reportFallbackActive=true",
      );
      assert(
        typeof page.data.degradedHint === "string" &&
          page.data.degradedHint.length > 0,
        "fallback path must expose a degradedHint string to the UI",
      );
      assert(
        Array.isArray(page.data.degradedSources) &&
          page.data.degradedSources.length > 0,
        "fallback path must list at least one degradedSources entry",
      );
      assert(
        counters.mastery === 0 &&
          counters.assessment === 0 &&
          counters.brain === 0,
        "unified payload failure must not revive legacy report readers as second authority",
      );
    },
  );

  await run(
    "unified snapshot with degraded=true propagates degradedHint to page data (G5)",
    async function () {
      var pageDef = loadReportPage({
        api: {
          unwrapResponse: function (raw) {
            return raw;
          },
          getLearningReport: async function () {
            return {
              ok: true,
              schema_version: 1,
              authority: {
                read_model: "learning-report-read-model",
                progress_source: "learner_memory_events.learning_evidence",
                learning_brain_source: "dry_run_learning_evidence",
                deprecated_page_sources: [],
              },
              degraded: true,
              degraded_sources: ["mastery_dashboard"],
              source_status: {
                mastery_dashboard: {
                  ok: false,
                  latency_ms: 10,
                  error: "RuntimeError: offline",
                },
                today_progress: { ok: true, latency_ms: 3, error: null },
              },
              freshness: {
                event_count: 1,
                unknown_date_count: 0,
                window_truncated: false,
              },
              overview: {
                today_done: 1,
                recent_three_done: 1,
                attempt_count: 1,
                today_unique_questions: 1,
                recent_three_unique_questions: 1,
                unique_question_count: 1,
                daily_target: 30,
                streak_days: 1,
              },
              mastery: {
                overall_mastery: 0,
                groups: [],
                hotspots: [],
                review_summary: { total_due: 0 },
              },
              radar_dimensions: [],
              learning_brain: {},
              progress_feedback: { cards: [], milestones: [] },
            };
          },
        },
        auth: {
          getUserId: function () {
            return "report-user";
          },
        },
        helpers: {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
          isDark: function () {
            return false;
          },
          syncTabBar: function () {},
        },
        runtime: {
          getWorkspaceBack: function () {
            return null;
          },
          checkAuth: function (cb) {
            cb();
          },
        },
        route: {
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        },
        flags: {
          ensureFeatureEnabled: function () {
            return true;
          },
          isFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        },
      });
      var page = createPageInstance(pageDef);

      await page._loadReportPage();

      assert(
        page.data.reportFallbackActive === false,
        "unified payload still succeeded (only some sources degraded) → reportFallbackActive=false",
      );
      assert(
        page.data.degradedHint &&
          page.data.degradedHint.indexOf("掌握度看板") >= 0,
        "degradedHint must surface human-readable source name (mastery_dashboard → 掌握度看板)",
      );
      assert(
        Array.isArray(page.data.degradedSources) &&
          page.data.degradedSources.indexOf("mastery_dashboard") >= 0,
        "degradedSources must mirror the unified payload",
      );
    },
  );

  await run(
    "unified snapshot with window_truncated=true marks recent window degraded",
    async function () {
      var pageDef = loadReportPage({
        api: {
          unwrapResponse: function (raw) {
            return raw;
          },
          getLearningReport: async function () {
            return {
              ok: true,
              schema_version: 1,
              authority: {
                read_model: "learning-report-read-model",
                progress_source: "learner_memory_events.learning_evidence",
                learning_brain_source: "dry_run_learning_evidence",
                deprecated_page_sources: [],
              },
              degraded: false,
              degraded_sources: [],
              source_status: {},
              freshness: {
                event_count: 100,
                unknown_date_count: 0,
                window_truncated: true,
              },
              overview: {
                today_done: 2,
                recent_three_done: 100,
                attempt_count: 100,
                today_unique_questions: 1,
                recent_three_unique_questions: 50,
                unique_question_count: 50,
                daily_target: 30,
                streak_days: 1,
              },
              mastery: {
                overall_mastery: 0,
                groups: [],
                hotspots: [],
                review_summary: { total_due: 0 },
              },
              radar_dimensions: [],
              learning_brain: {},
              progress_feedback: { cards: [], milestones: [] },
            };
          },
        },
        auth: {
          getUserId: function () {
            return "report-user";
          },
        },
        helpers: {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
          isDark: function () {
            return false;
          },
          syncTabBar: function () {},
        },
        runtime: {
          getWorkspaceBack: function () {
            return null;
          },
          checkAuth: function (cb) {
            cb();
          },
        },
        route: {
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        },
        flags: {
          ensureFeatureEnabled: function () {
            return true;
          },
          isFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        },
      });
      var page = createPageInstance(pageDef);

      await page._loadReportPage();

      assert(
        page.data.reportFallbackActive === false,
        "window_truncated payload still uses unified report, not legacy fallback",
      );
      assert(
        page.data.degradedHint &&
          page.data.degradedHint.indexOf("近 3 天窗口") >= 0,
        "window_truncated=true must surface recent-window degraded hint",
      );
      assert(
        Array.isArray(page.data.degradedSources) &&
          page.data.degradedSources.indexOf("learning_report_window") >= 0,
        "window_truncated=true must include learning_report_window source",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_snapshot_dedupe.js (" + pass + " assertions)");
})();
