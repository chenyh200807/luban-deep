// pass-readiness-view-model.js — 过线体检(S5)九屏旅程 · 纯函数视图模型(旅程侧)
//
// 契约来源(冻结, 不许自造):
// - 计划: docs/plan/测评题库与考试模块/2026-08-04-luban-pass-readiness-acquisition-diagnostic-plan.md
//   §4.1 落地页六要素 / §5.1 登录 UI 合同 / §6.2 纯点选 + 6 题检查点 / §11 Phase 3 九屏 UX 规则
// - 登录: 授权车道 = 既有 POST /wechat/mp/login(phone_code);
//   拒绝车道 = POST /api/v1/wechat/mp/login-basic {code} → 标准 auth 响应。
//   同一 handler 内分车道, 拒绝路径零二次弹窗/零挽留/零 toast, tap 数与授权路径相同。
// - 测评: create_assessment(assessment_type="pass_readiness") 响应含
//   checkpoint_after(中场检查点由此驱动, 前端不得写死 6)、scored_count、profile_count、
//   15 questions(答案已 redact, 全部 single_choice/multi_choice/profile_probe 纯点选);
//   提交走既有 submit_assessment, 答案 wire = dict[str,str] 字母。
// - 检查点屏红线(§6.2): 只给粗带位 + coverage=low 文案 + 唯一 CTA;
//   不出任何证据、不点名任何弱点。粗带数值只能来自服务端字段, 前端不本地估分
//   (§9.3 禁 frontend weakness calculator)。

function _obj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _arr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v).trim();
}
function _num(v) {
  var parsed = Number(v);
  return Number.isFinite(parsed) ? parsed : 0;
}

// ── 落地页六要素(§4.1, 文案逐字来自计划) ─────────────────────
var LANDING_COPY = {
  productName: "鲁班智考 · 一建过线体检",
  h1: "离 96 分过线，你还差几分？",
  subtitle: "10分钟 · 2015–2025 十一年真题考法 · 定位到具体采分点",
  antiQuizLine: "不是心理测试——每个结论都能点开看：哪道题、哪个采分点、丢在哪",
  sampleReportCaption: "样例报告 · 分数带 vs 过线线",
  ctaLogin: "微信一键登录 · 开始测评",
  ctaLoggedIn: "开始测评",
  phoneAuthReason:
    "手机号用于绑定你的报告和学习记录——换手机/换微信不丢，考前提醒可随时退订。不影响本次测评。",
};

// ── 登录车道解析(§5.1 UI 合同) ───────────────────────────────
// getPhoneNumber 事件 detail 里有 code/phoneCode → 授权车道;
// 没有(用户在微信弹窗点了「拒绝」) → 拒绝车道, 同一 handler 直接走 login-basic。
// 隐私协议中断(privacy)单独识别: 那不是「拒绝手机号」, 不得静默降级登录。
function resolveLoginLane(detail) {
  var d = _obj(detail);
  var phoneCode = _str(d.code || d.phoneCode);
  if (phoneCode) {
    return { lane: "phone", phoneCode: phoneCode, privacyInterrupted: false };
  }
  var errMsg = _str(d.errMsg || d.err_msg || d.message).toLowerCase();
  var privacyInterrupted =
    errMsg.indexOf("privacy") >= 0 || errMsg.indexOf("隐私") >= 0;
  return { lane: "basic", phoneCode: "", privacyInterrupted: privacyInterrupted };
}

// ── 会话规整(create / resume 共用) ───────────────────────────
function normalizeOptions(rawOptions) {
  var opts = rawOptions || [];
  if (Array.isArray(opts)) {
    return opts
      .map(function (o) {
        var option = _obj(o);
        return {
          key: _str(option.key),
          text: _str(option.text || option.label || option.value),
        };
      })
      .filter(function (o) {
        return o.key && o.text;
      });
  }
  return Object.keys(_obj(opts))
    .sort()
    .map(function (k) {
      return { key: k, text: _str(opts[k]) };
    })
    .filter(function (o) {
      return o.key && o.text;
    });
}

var QUESTION_TYPE_LABELS = {
  single_choice: "单选题",
  multi_choice: "多选题",
  profile_probe: "备考情况",
};

function normalizeQuestionType(value) {
  var type = _str(value);
  return QUESTION_TYPE_LABELS[type] ? type : "single_choice";
}

// 案例微进度: 按题目携带的 case 分组字段(case_id/material_id)推导「案例 i/n」。
// 只有携带分组字段的题目会得到 caseTag; 无案例字段 → 空串(不渲染)。
function buildCaseTags(questions) {
  var order = [];
  var seen = {};
  questions.forEach(function (q) {
    var caseId = _str(q.__caseId);
    if (caseId && !seen[caseId]) {
      seen[caseId] = true;
      order.push(caseId);
    }
  });
  var total = order.length;
  return questions.map(function (q) {
    var caseId = _str(q.__caseId);
    if (!caseId || !total) return "";
    return "案例 " + (order.indexOf(caseId) + 1) + "/" + total;
  });
}

function normalizeSession(payload) {
  var body = _obj(_obj(payload).data && !_obj(payload).quiz_id ? payload.data : payload);
  var rawQuestions = _arr(body.questions);
  var questions = rawQuestions
    .map(function (raw, idx) {
      var q = _obj(raw);
      var stem = _str(q.question_stem || q.stem || q.text || q.content);
      var id = _str(q.question_id || q.id) || (stem ? "q_" + (idx + 1) : "");
      if (!id || !stem) return null;
      var type = normalizeQuestionType(q.question_type);
      return {
        id: id,
        question_stem: stem,
        options: normalizeOptions(q.options),
        question_type: type,
        typeLabel: QUESTION_TYPE_LABELS[type],
        scored: type !== "profile_probe" && q.scored !== false,
        __caseId: _str(q.case_id || q.material_id || q.case_group_id),
        caseMaterial: _str(q.case_material || q.material_text),
      };
    })
    .filter(Boolean);
  var caseTags = buildCaseTags(questions);
  questions = questions.map(function (q, idx) {
    return {
      id: q.id,
      question_stem: q.question_stem,
      options: q.options,
      question_type: q.question_type,
      typeLabel: q.typeLabel,
      scored: q.scored,
      caseTag: caseTags[idx],
      caseMaterial: q.caseMaterial,
    };
  });
  // checkpoint_after 唯一来源 = 服务端响应; 缺失 → 0 = 本次无中场检查点。
  var checkpointAfter = Math.max(0, Math.floor(_num(body.checkpoint_after)));
  var scoredCount =
    Math.max(0, Math.floor(_num(body.scored_count))) ||
    questions.filter(function (q) {
      return q.scored;
    }).length;
  return {
    quizId: _str(body.quiz_id),
    checkpointAfter: checkpointAfter,
    scoredCount: scoredCount,
    profileCount: Math.max(0, Math.floor(_num(body.profile_count))),
    blueprintVersion: _str(body.blueprint_version),
    formVersion: _str(body.form_version || body.form_id),
    // 服务端可选的中场粗带投影(若无则检查点屏只给 coverage=low 文案, 不本地造数)
    midpointBand: _str(body.midpoint_band || (_obj(body.midpoint).band || "")),
    questions: questions,
    // 服务端草稿快照(resume 时冲突以它为准)
    serverAnswers: _obj(body.draft_answer_snapshot),
  };
}

// ── 进度模型 ─────────────────────────────────────────────────
function buildAnswerState(questions, selectedKeys, currentIndex) {
  var list = _arr(questions);
  var keys = _obj(selectedKeys);
  var sheet = [];
  var answeredCount = 0;
  var answeredScoredCount = 0;
  for (var i = 0; i < list.length; i++) {
    var q = list[i];
    var answered = !!_str(keys[q.id]);
    if (answered) {
      answeredCount += 1;
      if (q.scored) answeredScoredCount += 1;
    }
    sheet.push({
      id: q.id,
      index: i,
      number: i + 1,
      answered: answered,
      current: i === currentIndex,
    });
  }
  return {
    answerSheet: sheet,
    answeredCount: answeredCount,
    answeredScoredCount: answeredScoredCount,
    unansweredCount: list.length - answeredCount,
  };
}

// ── 本地草稿 + 服务端 resume(冲突服务端赢) ──────────────────
var DRAFT_STORAGE_KEY = "deeptutor.passReadiness.draft";
var REPORT_STORAGE_KEY = "deeptutor.passReadiness.lastReport";

function buildDraft(quizId, selectedKeys, currentIndex, checkpointSeen) {
  return {
    quizId: _str(quizId),
    selectedKeys: _obj(selectedKeys),
    currentIndex: Math.max(0, Math.floor(_num(currentIndex))),
    checkpointSeen: !!checkpointSeen,
    updatedAt: Date.now(),
  };
}

// 合并次序: 先取本地草稿, 再让服务端快照逐题覆盖(服务端赢)。
function mergeResumeAnswers(serverAnswers, localDraftKeys) {
  var merged = {};
  var local = _obj(localDraftKeys);
  Object.keys(local).forEach(function (qId) {
    var value = _str(local[qId]);
    if (value) merged[qId] = value;
  });
  var server = _obj(serverAnswers);
  Object.keys(server).forEach(function (qId) {
    var value = _str(server[qId]);
    if (value) merged[qId] = value;
  });
  return merged;
}

// ── 中场检查点(§6.2) ────────────────────────────────────────
// 触发: 服务端 checkpoint_after > 0, 且已答计分题数达到 checkpoint_after,
// 且本次会话尚未展示过。checkpoint_after 缺失(=0)时永不触发。
function shouldShowCheckpoint(session, answeredScoredCount, checkpointSeen) {
  var s = _obj(session);
  var after = Math.max(0, Math.floor(_num(s.checkpointAfter)));
  if (!after || checkpointSeen) return false;
  return _num(answeredScoredCount) >= after;
}

function buildCheckpointModel(session) {
  var s = _obj(session);
  var after = Math.max(0, Math.floor(_num(s.checkpointAfter)));
  var scored = Math.max(after, Math.floor(_num(s.scoredCount)));
  var remaining = Math.max(0, scored - after);
  return {
    title: "中场小结 · 已完成 " + after + "/" + scored + " 道计分题",
    // coverage=low 的诚实文案: 6 题不满足 §7.4 两次独立观察门, 不点名弱点。
    coverageLabel: "证据覆盖：低",
    coverageLine:
      "当前证据只够给出一个很宽的分数带，还不足以定位你的失分采分点。",
    // 粗带位: 只投影服务端字段; 服务端没给就整块隐藏, 前端不本地估分。
    bandLine: _str(s.midpointBand),
    cta: "再答 " + remaining + " 题：收窄分数带 + 定位失分采分点",
  };
}

// ── 提交 wire(dict[str,str], 与既有 submit_assessment 一致) ──
function buildSubmitAnswers(selectedKeys) {
  var answers = {};
  var keys = _obj(selectedKeys);
  Object.keys(keys).forEach(function (qId) {
    var value = _str(keys[qId]);
    if (value) answers[qId] = value;
  });
  return answers;
}

// ── 完成后落点(跑道反转第 1 步的接线点) ─────────────────────
// 新用户完成诊断后的默认落点是「计划页(跑道视图)」——计划页二波交付。
// 当前值先指向本模块报告页的保存成功态; 计划页路由落地后, 只改这一个常量
// (把值换成计划页路由), 页面代码不用动。
var POST_DIAGNOSTIC_LANDING_PATH =
  "/packageDeeptutor/pages/luban/pass-readiness/report/report?section=saved";

function postDiagnosticLandingRoute(quizId) {
  var id = _str(quizId);
  return POST_DIAGNOSTIC_LANDING_PATH + (id ? "&quiz_id=" + encodeURIComponent(id) : "");
}

module.exports = {
  LANDING_COPY: LANDING_COPY,
  DRAFT_STORAGE_KEY: DRAFT_STORAGE_KEY,
  REPORT_STORAGE_KEY: REPORT_STORAGE_KEY,
  resolveLoginLane: resolveLoginLane,
  normalizeSession: normalizeSession,
  buildAnswerState: buildAnswerState,
  buildDraft: buildDraft,
  mergeResumeAnswers: mergeResumeAnswers,
  shouldShowCheckpoint: shouldShowCheckpoint,
  buildCheckpointModel: buildCheckpointModel,
  buildSubmitAnswers: buildSubmitAnswers,
  postDiagnosticLandingRoute: postDiagnosticLandingRoute,
};
