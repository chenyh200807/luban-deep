// pass-readiness-report-view-model.js — 过线体检结果页(S5 屏 3-9)纯函数视图模型
//
// 字段契约(C 线交付版, 冻结): 提交后 report 顶层含 `pass_readiness` 块:
// - band_status: "ok" | "evidence_insufficient"(后者 estimated_score_band=null,
//   band_copy="evidence insufficient for a band", 结果页必须处理该分支);
// - estimated_score_band("100–125 分") + band_lower/band_upper/band_width/band_tier;
// - pass_line: 96;
// - ability_readiness("中高 (75–85)" 档位+粗区间, 首屏只用这个;
//   精确值在 ability_readiness_detail, 只进证据详情屏);
// - prep_feasibility(独立字段, 只拼进风险措辞, 永不进带);
// - risk_band; evidence_coverage("low" 时 reference_pass_interval 为空串→不渲染);
// - unmeasured_dimensions(含 "answer_expression" 时禁称表达弱点);
// - self_reported_score_label("自报未核验", 非空时带子旁小字展示)。
// p0a 基础字段(items/wrong_items/score_summary)全保留, 错题渲染复用既有链。
// 首屏精确整数纪律(§7.2): 本模型首屏只输出档位+粗区间字符串, 不输出精确整数就绪度。
// 语气权威(§4.2/§4.3): 禁审视语, 弱点句必须与补救 CTA 同屏, wow 必须暖。

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
  return Number.isFinite(parsed) ? parsed : NaN;
}

// §4.1 信任文案(逐字)
var BAND_DISCLAIMER =
  "本分数带由本次有限作答与（如提供的）历史成绩按专家规则估算，尚未经过真实考试结果校准，不是考试结果承诺。完成复测后可重新诊断，获得基于更多证据的新分数带。";

// 复测收据文案(§6.5, 逐字; 永不说「已掌握」)
var RETEST_RECEIPT_COPY =
  "同一采分点、同难度锚的平行题，这次拿到了——这是一次新的正面证据";

// 易错点槽位空供给时的诚实占位(§7.3.4 omitted-rather-than-faked)
var PITFALL_PLACEHOLDER = "该采分点的易错点整理中";

var COVERAGE_LABELS = { low: "低", medium: "中", high: "高" };

// "75–95 分" / "75-95" → { low, high }; 解析失败 → null
function parseBand(text) {
  var raw = _str(text);
  if (!raw) return null;
  var match = /(\d+)\s*[–—~-]\s*(\d+)/.exec(raw);
  if (!match) return null;
  var low = Number(match[1]);
  var high = Number(match[2]);
  if (!Number.isFinite(low) || !Number.isFinite(high) || high < low) return null;
  return { low: low, high: high };
}

// "中低 (55–65)" → { tier: "中低", range: "55–65" }
function splitReadiness(text) {
  var raw = _str(text);
  if (!raw) return { tier: "", range: "" };
  var match = /^([^（(]+)[（(]([^）)]+)[）)]/.exec(raw);
  if (match) {
    return { tier: _str(match[1]), range: _str(match[2]) };
  }
  return { tier: raw, range: "" };
}

// report 顶层 → pass_readiness 块(容错: 块缺失时按根级字段读, 便于夹具/回放)
function passReadinessBlock(report) {
  var body = _obj(report);
  var block = _obj(body.pass_readiness);
  return Object.keys(block).length ? block : body;
}

// ── 屏 3: 结果首屏 ───────────────────────────────────────────
function buildResultModel(report) {
  var pr = passReadinessBlock(report);
  var bandStatus = _str(pr.band_status);
  var bandText = _str(pr.estimated_score_band);
  var bandAvailable = bandStatus !== "evidence_insufficient" && !!bandText;
  var passLine = Math.floor(_num(pr.pass_line)) || 96;
  // 数值优先用契约的 band_lower/band_upper; 缺失再解析展示串
  var lower = Math.floor(_num(pr.band_lower));
  var upper = Math.floor(_num(pr.band_upper));
  var parsed = null;
  if (bandAvailable) {
    if (Number.isFinite(lower) && Number.isFinite(upper) && upper >= lower) {
      parsed = { low: lower, high: upper };
    } else {
      parsed = parseBand(bandText);
    }
  }
  var readiness = splitReadiness(pr.ability_readiness);
  var coverageRaw = _str(pr.evidence_coverage).toLowerCase();
  var referenceInterval = _str(pr.reference_pass_interval);
  var unmeasured = _arr(pr.unmeasured_dimensions).map(_str);

  // 分数带 vs 过线线图形几何(0–160 分卷面): 纯呈现层比例, 不产生新数值结论
  var scaleMax = 160;
  var geometry = null;
  if (parsed) {
    geometry = {
      bandLeftPct: Math.max(0, Math.min(100, (parsed.low / scaleMax) * 100)),
      bandWidthPct: Math.max(
        2,
        Math.min(100, ((parsed.high - parsed.low) / scaleMax) * 100),
      ),
      passLinePct: Math.max(0, Math.min(100, (passLine / scaleMax) * 100)),
    };
  }

  // 「离过线还差最多 X 分」框架(§7.2): 只做 pass_line − band_lower 的呈现层算术
  var gapLine = "";
  if (parsed) {
    var gapMax = passLine - parsed.low;
    if (gapMax > 0) {
      gapLine = "离过线还差最多 " + gapMax + " 分";
    } else {
      gapLine = "预估分数带已越过过线线——用复测把它坐实";
    }
  }

  var nextPreview = buildNextPreview(report);

  // prep_feasibility 独立字段: 只拼进风险措辞, 永不改变分数带
  var riskBand = _str(pr.risk_band);
  var prepFeasibility = _str(pr.prep_feasibility);
  var riskLine = riskBand;
  if (riskBand && prepFeasibility) {
    riskLine = riskBand + " · " + prepFeasibility;
  } else if (prepFeasibility) {
    riskLine = prepFeasibility;
  }

  return {
    bandAvailable: bandAvailable,
    bandText: bandAvailable ? bandText : "",
    bandTier: _str(pr.band_tier),
    bandStatus: bandStatus || (bandAvailable ? "ok" : "evidence_insufficient"),
    bandUnavailableCopy: bandAvailable
      ? ""
      : _str(pr.band_copy) ||
        "本次证据还不够给出可靠的分数带——先看已定位的采分点证据，补上再测。",
    passLine: passLine,
    passLineLabel: "过线 " + passLine + " 分",
    geometry: geometry,
    gapLine: gapLine,
    riskBand: riskBand,
    riskLine: riskLine,
    readinessTier: readiness.tier,
    readinessRange: readiness.range,
    prepFeasibility: prepFeasibility,
    evidenceCoverage: coverageRaw,
    evidenceCoverageLabel: COVERAGE_LABELS[coverageRaw] || _str(pr.evidence_coverage),
    bandPolicyVersion: _str(pr.band_policy_version),
    referencePassInterval: referenceInterval,
    showReferenceInterval: !!referenceInterval,
    // 自报历史成绩标注: 非空时在带子旁小字展示
    selfReportedScoreLabel: _str(pr.self_reported_score_label),
    // 表达维度未测(含 answer_expression)时, 结果/证据页禁出表达弱点表述
    unmeasuredDimensions: unmeasured,
    expressionMeasured: unmeasured.indexOf("answer_expression") < 0,
    diagnosis: _str(pr.diagnosis || pr.one_sentence_diagnosis || _obj(report).diagnosis),
    disclaimer: BAND_DISCLAIMER,
    // 下一屏预告(§4.3 wow 必须暖):用真实定位到的失分采分点做"接下来你会看到",
    // 让首屏不止停在一个带子——数量与点名全部来自报告,零编造;无供给时整块不渲染。
    nextPreview: nextPreview,
    primaryCta: nextPreview.count
      ? "看这 " + nextPreview.count + " 个失分点怎么补回来"
      : "看我的采分点证据",
  };
}

// 首屏「接下来你会看到」预告:只点名报告里已定位的采分点(最多 3 个),
// 不足则少列,零供给则整块不渲染——不编造、不凑数。
function buildNextPreview(report) {
  var pr = passReadinessBlock(report);
  var body = _obj(report);
  var rows = _arr(pr.evidence_items).length
    ? _arr(pr.evidence_items)
    : _arr(body.evidence_items).length
      ? _arr(body.evidence_items)
      : _arr(body.wrong_items);
  var labels = [];
  rows.forEach(function (raw) {
    var item = _obj(raw);
    var label = _str(
      item.scoring_point || item.scoring_point_text || _arr(item.knowledge_points)[0],
    );
    if (label && labels.indexOf(label) < 0) labels.push(label);
  });
  return {
    count: rows.length,
    available: !!labels.length,
    kicker: "接下来你会看到",
    points: labels.slice(0, 3),
    moreCount: Math.max(labels.length - 3, 0),
  };
}

// ── 证据详情屏专用: 精确就绪度只在这里出(§7.2 首屏纪律) ──────
function buildReadinessDetail(report) {
  var pr = passReadinessBlock(report);
  var detail = pr.ability_readiness_detail;
  if (detail == null) return { available: false, text: "" };
  var text = _str(
    typeof detail === "object" ? _obj(detail).value || _obj(detail).text : detail,
  );
  return { available: !!text, text: text };
}

// ── 屏 4: 证据屏 ─────────────────────────────────────────────
// 槽位: 题目 / 学员作答 / 采分点 / 易错点(空则占位) / why-missed 句 / 教材来源。
// 供给优先级: evidence_items(专用投影) → p0a wrong_items(既有链字段)。
// lesson/retest 绑定缺失 → 对应按钮整块不渲染(§7.6 禁 dead button)。
function buildEvidenceModel(report, resultModel) {
  var body = _obj(report);
  var pr = passReadinessBlock(report);
  var expressionMeasured = resultModel
    ? !!resultModel.expressionMeasured
    : _arr(pr.unmeasured_dimensions).map(_str).indexOf("answer_expression") < 0;
  var rows = _arr(pr.evidence_items).length
    ? _arr(pr.evidence_items)
    : _arr(body.evidence_items).length
      ? _arr(body.evidence_items)
      : _arr(body.wrong_items);
  var items = rows
    .map(function (raw, idx) {
      var item = _obj(raw);
      var pitfall = _str(item.pitfall || item.misconception);
      var whyMissed = _str(
        item.why_missed || item.why_missed_copy || item.simple_explanation,
      );
      // 表达维度未测时抑制任何「表达失分」归因表述(§6.2/§7.3)
      if (!expressionMeasured && /表达/.test(whyMissed)) {
        whyMissed = "";
      }
      var learnerAnswer = _str(item.learner_answer);
      var correctAnswer = _str(item.correct_answer);
      return {
        index: idx + 1,
        questionId: _str(item.question_id),
        questionStem: _str(item.question_stem || item.stem),
        learnerAnswer: learnerAnswer,
        // 有选项原文用原文(「C. …」),快照缺文本退回裸字母;都没有则整行不渲染。
        learnerAnswerDisplay: _str(item.learner_option_text) || learnerAnswer,
        correctAnswer: correctAnswer,
        correctAnswerDisplay: _str(item.correct_option_text) || correctAnswer,
        correctWordingKnown: !!_str(item.scoring_wording || item.earning_wording),
        scoringPoint: _str(
          item.scoring_point ||
            item.scoring_point_text ||
            _arr(item.knowledge_points)[0],
        ),
        scoringWording: _str(item.scoring_wording || item.earning_wording),
        pitfall: pitfall || PITFALL_PLACEHOLDER,
        pitfallAvailable: !!pitfall,
        whyMissed: whyMissed,
        fix: _str(item.fix),
        // source_ref 是机器锚(排障用),人话来源由后端投影裁决;这里绝不回落。
        source: _str(item.source || item.textbook_source),
        lessonPackId: _str(item.lesson_pack_id),
        retestPackId: _str(item.retest_pack_id),
      };
    })
    .filter(function (item) {
      return item.questionStem;
    });
  return {
    items: items,
    isEmpty: !items.length,
    emptyCopy: "本次没有可展示的采分点证据——先完成一次复测积累新证据。",
    lessonCta: "看 8 分钟微课，把这个点补上",
    retestCta: "直接复测这个采分点",
    readinessDetail: buildReadinessDetail(report),
  };
}

// ── 屏 5: 三优先计划预览(GET /api/v1/luban/exam-prep-plan 投影) ──
// 响应形状(冻结): { enabled, days:[{date, tasks:[{task, why, expected_time,
// mode, target_pack_id, ...}]}], pass_readiness, exam_countdown_days, ... }。
// 取全 days 拍平后的前三个任务渲染三优先槽(任务标题 + why + 预期时长)。
// enabled:false / 请求失败 / 无任务 → 骨架 pending 态, 零假数据零可点按钮。
function buildPlanPreviewModel(planPayload) {
  var body = _obj(planPayload);
  var payload = _obj(body.data && body.days === undefined ? body.data : body);
  var pending = {
    status: "pending",
    pendingCopy: "完整学习计划正在生成——保存报告后即可查看。",
    slots: [
      { index: 1, roleLabel: "立即证明任务", desc: "一节微课 + 一次平行复测" },
      { index: 2, roleLabel: "下一个失分风险", desc: "绑定对应的学习与练习路径" },
      { index: 3, roleLabel: "明确暂缓项", desc: "现在不该花时间的部分和原因" },
    ],
    items: [],
  };
  if (payload.enabled === false) return pending;
  var flattened = [];
  _arr(payload.days).forEach(function (day) {
    var d = _obj(day);
    _arr(d.tasks).forEach(function (task) {
      flattened.push({ task: _obj(task), date: _str(d.date) });
    });
  });
  var rows = flattened.slice(0, 3);
  if (!rows.length) return pending;
  return {
    status: "ready",
    pendingCopy: "",
    slots: [],
    items: rows.map(function (row, idx) {
      var task = row.task;
      return {
        index: idx + 1,
        title: _str(task.task || task.title),
        desc: _str(task.why || task.desc),
        expectedTime: _str(task.expected_time),
        mode: _str(task.mode),
        targetPackId: _str(task.target_pack_id),
        date: row.date,
      };
    }),
  };
}

// ── 屏 7: 复测证明收据 ───────────────────────────────────────
function buildReceiptModel() {
  return {
    headline: RETEST_RECEIPT_COPY,
    // 一次正确复测 = 一次新的正面观察, 不是稳定掌握(§7.4)
    subline: "复测判定以复测页的服务端结果为准；这是一次新的正面观察，还不等于稳定掌握。",
    cta: "保存这份报告",
  };
}

// ── /assessment/profile → diagnostic_sources.pass_readiness ──
// 保存屏与老学员重测入口的唯一判断源(禁前端自判是否完成过诊断)。
function readDiagnosticSource(profilePayload) {
  var body = _obj(profilePayload);
  var payload = _obj(body.data && !body.diagnostic_sources ? body.data : body);
  var source = _obj(_obj(payload.diagnostic_sources).pass_readiness);
  return {
    completed: source.completed === true,
    quizId: _str(source.quiz_id),
    scoredAt: _str(source.scored_at),
  };
}

// ── 屏 8: 保存屏 ─────────────────────────────────────────────
function buildSaveModel(hasPhone) {
  if (hasPhone) {
    return {
      mode: "direct",
      title: "报告已绑定你的账号",
      desc: "换手机、换微信都不丢，复测后会生成新的对比报告。",
      cta: "查看我的下一步",
    };
  }
  return {
    mode: "phone_auth",
    title: "绑定手机号，保存完整报告",
    desc:
      "手机号用于绑定你的报告和学习记录——换手机/换微信不丢，考前提醒可随时退订。",
    cta: "微信一键绑定手机号",
    // 拒绝不拦结果(§5.1): 这行常驻展示, 不做任何弹窗/挽留
    declineNote: "不绑定也可以继续查看本次结果",
  };
}

// ── 屏 9: 会员 handoff(§8.3 损失框架; 文案红线清单钉死在域测试里) ──
function buildMembershipCta(context) {
  var ctx = _obj(context);
  var daysToExam = Math.floor(_num(ctx.daysToExam || ctx.days_to_exam)) || 0;
  var passedSubject = _str(ctx.passedSubjectLine || ctx.passed_subject_line);
  var parts = ["刚才这个点你已经补上。"];
  if (daysToExam > 0) {
    parts.push("距考试还有 " + daysToExam + " 天——");
  }
  parts.push("差 4 分和差 40 分，结果都是再等一年。");
  parts.push("继续按同样方式，把剩余的过线风险逐个消掉。");
  return {
    copy: parts.join(""),
    // 已过科目滚动作废个性化(服务端给出事实句才展示, 前端不推算年份)
    personalization: passedSubject,
    cta: "继续消掉剩余过线风险",
  };
}

// ── 证据卡内嵌鲁班深解析(owner 2026-08-07 拍板:报告即试驾) ──
// 只做只读投影: /items/{id}/explain 响应 → 渲染块;空字段整块不出(禁占位)。
function buildDeepExplanationModel(payload) {
  var body = _obj(payload);
  var exp = _obj(body.explanation || body);
  var blocks = [
    { label: "鲁班讲解", text: _str(exp.summary) },
    { label: "你为什么错", text: _str(exp.why_wrong) },
    { label: "错因分析", text: _str(exp.cause_analysis) },
    { label: "采分点拆解", text: _str(exp.scoring_points) },
    { label: "易错陷阱", text: _str(exp.pitfall) },
    { label: "记忆口诀", text: _str(exp.mnemonic) },
    { label: "依据", text: _str(exp.source_basis) },
    { label: "下一步", text: _str(exp.next_action) },
  ].filter(function (block) {
    return !!block.text;
  });
  var optionReviews = _arr(exp.option_reviews)
    .map(function (row) {
      var review = _obj(row);
      return {
        key: _str(review.key),
        status: _str(review.status) || "neutral",
        statusLabel: _str(review.status_label),
        review: _str(review.review),
      };
    })
    .filter(function (review) {
      return review.key && review.review;
    });
  var keyTerms = _arr(exp.key_terms).map(_str).filter(Boolean);
  return {
    available: blocks.length > 0 || optionReviews.length > 0,
    blocks: blocks,
    optionReviews: optionReviews,
    keyTerms: keyTerms,
  };
}

module.exports = {
  BAND_DISCLAIMER: BAND_DISCLAIMER,
  RETEST_RECEIPT_COPY: RETEST_RECEIPT_COPY,
  PITFALL_PLACEHOLDER: PITFALL_PLACEHOLDER,
  parseBand: parseBand,
  splitReadiness: splitReadiness,
  buildResultModel: buildResultModel,
  buildReadinessDetail: buildReadinessDetail,
  buildEvidenceModel: buildEvidenceModel,
  buildDeepExplanationModel: buildDeepExplanationModel,
  buildPlanPreviewModel: buildPlanPreviewModel,
  buildReceiptModel: buildReceiptModel,
  readDiagnosticSource: readDiagnosticSource,
  buildSaveModel: buildSaveModel,
  buildMembershipCta: buildMembershipCta,
};
