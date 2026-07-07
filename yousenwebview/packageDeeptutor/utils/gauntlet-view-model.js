// gauntlet-view-model.js — 实务闯关(回忆→半写→核对)纯函数视图模型
//
// 供给边界(缺供给降级不造数):
// - 题面 = signed 变体池 read model(/luban/lessons/{pack}/retest-items),
//   与 retest 页同一读源, 不造新供给。①回忆展示变体题干, 采分点只露数量。
// - ②半写: runtime 无 R6 挖空 bank → 首版如实降级为自由默写输入区
//   (页面文案明说「精确挖空在准备中」, 不伪装挖空)。
//   ── R6 挖空 bank 接口位形状(给后续内容管线) ──
//   请求键: { pack_id: "F16" }
//   响应形状: { skeleton_sentences: [{ text_before, blank_hint, text_after }],
//               recall_prompt: "<整句默写引导>" }
//   供给上线后把响应喂给 buildGauntletViewModel 的 halfWrite 参数即换成精确挖空。
// - ③核对 = 既有本地确定性判分(retest 同款 choice === expected_ok),
//   命中/漏点只做呈现层暖反馈; 漏点不写任何学情/错因记账
//   (错因记账真值只归判分内核 writeback, 前端无签发权——文案不造「已记进」)。
// - 档位③「全量作答」(buildFullAnswerVerdict): ②半写自由文本提交既有判分内核
//   seam(POST /luban/lessons/{pack}/full-answer), 逐采分点 verdict 由后端给。
//   与上面本地核对分界: 此档后端走 write_grading_error_events(promoting), 故
//   「漏点入错因银行」是后端 writeback_count 兑现的如实转述, 非前端假声明。
//   前端仍零判分、零改分; L0_observed 封顶如实披露, 不假装稳定掌握(红线)。
// - 文案铁律: 帮你变强基调, 禁审视揭短词(测试钉死禁词表)。

function _obj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function _arr(v) {
  return Array.isArray(v) ? v : [];
}
function _str(v) {
  return v == null ? "" : String(v).trim();
}

/**
 * retest-items 响应 → 闯关 data(与 retest.js 同一字段映射)。
 * @param {object} body GET /api/v1/luban/lessons/{pack}/retest-items 响应 body
 */
function buildGauntletViewModel(body) {
  var raw = _arr(_obj(body).items);
  var items = raw.map(function (item, idx) {
    var o = _obj(item);
    return {
      key: _str(o.variant_id) || "v_" + idx,
      variant_id: _str(o.variant_id),
      rule_group: _str(o.rule_group),
      surface: _str(o.surface),
      expected_ok: o.expected_ok === true,
      correct_statement: _str(o.correct_statement),
      anchor: _str(o.anchor),
      answered: false,
      correct: null,
      chosenOk: null,
    };
  });
  return {
    items: items,
    total: items.length,
    // ①回忆: 采分点只露数量——主动回忆是这一关存在的理由
    pointCountLine: items.length
      ? "这一关有 " + items.length + " 个判断点。想一想：每条做法妥不妥当？依据是哪条规矩？"
      : "",
    isEmpty: items.length === 0,
  };
}

/**
 * 本地确定性判分(档位①, 与 retest 同款唯一机制): 选择 === expected_ok。
 */
function gradeChoice(item, choiceOk) {
  return Boolean(choiceOk) === Boolean(_obj(item).expected_ok);
}

/**
 * ③核对完成后的结果投影: 命中环 + 暖标题。
 * 只做呈现层汇总, 不派生任何掌握结论。
 */
function buildVerdict(items) {
  var list = _arr(items);
  var answered = list.filter(function (item) {
    return _obj(item).answered;
  });
  var hit = answered.filter(function (item) {
    return _obj(item).correct === true;
  }).length;
  var total = list.length;
  var done = total > 0 && answered.length >= total;
  var missed = total - hit;
  var title;
  if (hit >= total) {
    title = "全部命中 · 这一关你赢了";
  } else if (missed === 1) {
    title = "命中 " + hit + " 条 · 就差一步";
  } else {
    title = "命中 " + hit + " 条 · 底子已经有了";
  }
  return {
    done: done,
    hitCount: hit,
    total: total,
    hitLabel: hit + "/" + total,
    percent: total ? Math.round((hit / total) * 100) : 0,
    heroTitle: title,
    heroDesc:
      missed > 0
        ? "漏的再看一眼就稳了——逐条对下去"
        : "判别逻辑在你手里了——明天换个皮验一遍",
  };
}

/**
 * 档位③全量作答: 判分内核响应 → 呈现层投影(纯函数, 零判分)。
 *
 * 权威边界(红线):
 * - 前端零判分、零改分——status / awarded_score 全部原样透传内核结论, 只做呈现映射。
 * - 后端投影已剥离 keywords / required_terms(防再认泄漏, PRD 红线 D16); 本函数不
 *   重建任何候选词, criterion 仅作判后反馈展示(非输入期提示)。
 * - 诚实封顶: stable_truth_eligible=false / L0_observed 时不假装稳定掌握, 明说
 *   「已记录 · 待权威采分点上线后升级」。
 * - 漏点入错因银行由后端 writeback 兑现(writeback_count, 内核唯一 sink); 前端只在
 *   后端确有写入(writeCount>0)时如实转述, 无写入不假声明记账。
 *
 * @param {object} resp POST /api/v1/luban/lessons/{pack}/full-answer 响应 body
 */
function buildFullAnswerVerdict(resp) {
  var body = _obj(resp);
  var points = _arr(body.scoring_points).map(function (p, idx) {
    var o = _obj(p);
    var status = _str(o.status).toLowerCase(); // full | partial | miss
    return {
      key: "sp_" + idx,
      criterion: _str(o.criterion),
      status: status,
      hit: status === "full",
      miss: status === "miss",
      // 命中竹青(grn) / 漏点赭暖(och) / 部分中性
      chipClass: status === "full" ? "grn" : status === "miss" ? "och" : "line",
      statusLabel:
        status === "full" ? "✓ 命中" : status === "miss" ? "漏了这条" : "部分命中",
    };
  });
  var missCount = points.filter(function (p) {
    return p.miss;
  }).length;
  var stable = body.stable_truth_eligible === true;
  var writeCount = Number(body.writeback_count || 0);
  var scoreAwarded = Number(body.score_awarded || 0);
  var maxScore = Number(body.max_score || 0);
  return {
    graded: true,
    scoreAwarded: scoreAwarded,
    maxScore: maxScore,
    scoreLine:
      maxScore > 0 ? Math.round(scoreAwarded * 10) / 10 + " / " + maxScore : "",
    points: points,
    hasPoints: points.length > 0,
    missCount: missCount,
    // 诚实封顶: L0 不进稳定掌握, 如实告知升级路径(不假装满分掌握)
    stableEligible: stable,
    evidenceLevel: _str(body.evidence_level) || "L0_observed",
    capNote: stable
      ? "这次判分已计入稳定掌握"
      : "已记录你这次的作答——等权威采分点上线，会把它升级成稳定掌握",
    // 漏点入错因银行: 只有后端内核确有写入才如实转述(前端无记账签发权)
    mistakeNote:
      missCount > 0 && writeCount > 0
        ? "漏的这几点已经进你的错因银行，之后会拎出来陪你再练"
        : "",
  };
}

/** 草稿(本地 storage)形状: 退出留草稿承诺的唯一载体 */
function buildDraft(text, step) {
  return {
    text: _str(text),
    step: Number(step) >= 2 ? 2 : 1, // ③核对不落草稿(答案即时判分, 无半成品)
    savedAt: Date.now(),
  };
}

function draftStorageKey(packId) {
  return "luban_gauntlet_draft:" + _str(packId).toUpperCase();
}

module.exports = {
  buildGauntletViewModel: buildGauntletViewModel,
  gradeChoice: gradeChoice,
  buildVerdict: buildVerdict,
  buildFullAnswerVerdict: buildFullAnswerVerdict,
  buildDraft: buildDraft,
  draftStorageKey: draftStorageKey,
};
