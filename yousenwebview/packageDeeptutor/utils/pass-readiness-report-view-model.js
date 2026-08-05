// pass-readiness-report-view-model.js — 过线体检结果页(S5 屏 3-9)纯函数视图模型
//
// 字段契约(§7.2, 冻结): estimated_score_band(可为 null, band_status=evidence_insufficient)、
// pass_line(96)、ability_readiness(档位+粗区间)、prep_feasibility、risk_band、
// evidence_coverage、reference_pass_interval(low 档为空串则不渲染)。
// 首屏禁出精确整数就绪度(§7.2 first-screen precision discipline):
// 本模型只输出 readinessTier + readinessRange 两个字符串, 不输出任何精确整数字段。
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
  return Number.isFinite(parsed) ? parsed : 0;
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

// ── 屏 3: 结果首屏 ───────────────────────────────────────────
function buildResultModel(report) {
  var body = _obj(report);
  var bandStatus = _str(body.band_status);
  var bandText = _str(body.estimated_score_band);
  var bandAvailable = bandStatus !== "evidence_insufficient" && !!bandText;
  var passLine = Math.floor(_num(body.pass_line)) || 96;
  var parsed = bandAvailable ? parseBand(bandText) : null;
  var readiness = splitReadiness(body.ability_readiness);
  var coverageRaw = _str(body.evidence_coverage).toLowerCase();
  var referenceInterval = _str(body.reference_pass_interval);

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

  // 「离过线还差最多 X 分」框架(§7.2): 只做 pass_line − band_low 的呈现层算术
  var gapLine = "";
  if (parsed) {
    var gapMax = passLine - parsed.low;
    if (gapMax > 0) {
      gapLine = "离过线还差最多 " + gapMax + " 分";
    } else {
      gapLine = "预估分数带已越过过线线——用复测把它坐实";
    }
  }

  return {
    bandAvailable: bandAvailable,
    bandText: bandAvailable ? bandText : "",
    bandStatus: bandStatus || (bandAvailable ? "ok" : "evidence_insufficient"),
    bandUnavailableCopy: bandAvailable
      ? ""
      : "本次证据还不够给出可靠的分数带——先看已定位的采分点证据，补上再测。",
    passLine: passLine,
    passLineLabel: "过线 " + passLine + " 分",
    geometry: geometry,
    gapLine: gapLine,
    riskBand: _str(body.risk_band),
    readinessTier: readiness.tier,
    readinessRange: readiness.range,
    prepFeasibility: _str(body.prep_feasibility),
    evidenceCoverage: coverageRaw,
    evidenceCoverageLabel: COVERAGE_LABELS[coverageRaw] || _str(body.evidence_coverage),
    bandPolicyVersion: _str(body.band_policy_version),
    referencePassInterval: referenceInterval,
    showReferenceInterval: !!referenceInterval,
    diagnosis: _str(body.diagnosis || body.one_sentence_diagnosis),
    disclaimer: BAND_DISCLAIMER,
    primaryCta: "先补最影响得分的这一点",
  };
}

// ── 屏 4: 证据屏 ─────────────────────────────────────────────
// 槽位: 题目 / 学员作答 / 采分点 / 易错点(空则占位) / why-missed 句 / 教材来源。
// lesson/retest 绑定缺失 → 对应按钮整块不渲染(§7.6 禁 dead button), 显示诚实占位。
function buildEvidenceModel(report) {
  var body = _obj(report);
  var rows = _arr(body.evidence_items).length
    ? _arr(body.evidence_items)
    : _arr(body.evidence);
  var items = rows.map(function (raw, idx) {
    var item = _obj(raw);
    var pitfall = _str(item.pitfall || item.misconception);
    return {
      index: idx + 1,
      questionStem: _str(item.question_stem || item.stem),
      learnerAnswer: _str(item.learner_answer),
      scoringPoint: _str(item.scoring_point || item.scoring_point_text),
      scoringWording: _str(item.scoring_wording || item.earning_wording),
      pitfall: pitfall || PITFALL_PLACEHOLDER,
      pitfallAvailable: !!pitfall,
      whyMissed: _str(item.why_missed || item.why_missed_copy),
      source: _str(item.source || item.textbook_source || item.source_ref),
      lessonPackId: _str(item.lesson_pack_id),
      retestPackId: _str(item.retest_pack_id),
    };
  });
  return {
    items: items,
    isEmpty: !items.length,
    emptyCopy: "本次没有可展示的采分点证据——先完成一次复测积累新证据。",
    lessonCta: "看 8 分钟微课，把这个点补上",
    lessonMissingCopy: "该采分点的微课绑定整理中",
    retestCta: "直接复测这个采分点",
  };
}

// ── 屏 5: 三优先计划预览(数据二波接 exam_prep_plan_projection) ──
// 本波只有静态结构 + loading 态; 无 payload 时零假数据、零可点按钮。
function buildPlanPreviewModel(planPayload) {
  var body = _obj(planPayload);
  var rows = _arr(body.items).slice(0, 3);
  if (!rows.length) {
    return {
      status: "pending",
      pendingCopy: "完整学习计划正在生成——保存报告后即可查看。",
      slots: [
        { index: 1, roleLabel: "立即证明任务", desc: "一节微课 + 一次平行复测" },
        { index: 2, roleLabel: "下一个失分风险", desc: "绑定对应的学习与练习路径" },
        { index: 3, roleLabel: "明确暂缓项", desc: "现在不该花时间的部分和原因" },
      ],
      items: [],
    };
  }
  return {
    status: "ready",
    pendingCopy: "",
    slots: [],
    items: rows.map(function (raw, idx) {
      var item = _obj(raw);
      return {
        index: idx + 1,
        title: _str(item.title),
        desc: _str(item.desc || item.description),
        evidenceSource: _str(item.evidence_source),
        expectedTime: _str(item.expected_time),
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
  var daysToExam = Math.floor(_num(ctx.daysToExam || ctx.days_to_exam));
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

module.exports = {
  BAND_DISCLAIMER: BAND_DISCLAIMER,
  RETEST_RECEIPT_COPY: RETEST_RECEIPT_COPY,
  PITFALL_PLACEHOLDER: PITFALL_PLACEHOLDER,
  parseBand: parseBand,
  splitReadiness: splitReadiness,
  buildResultModel: buildResultModel,
  buildEvidenceModel: buildEvidenceModel,
  buildPlanPreviewModel: buildPlanPreviewModel,
  buildReceiptModel: buildReceiptModel,
  buildSaveModel: buildSaveModel,
  buildMembershipCta: buildMembershipCta,
};
