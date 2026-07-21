#!/usr/bin/env node
"use strict";
/**
 * 编译期题给图形求值器 —— practice dc.html 的 fig 绘制代码 → 结构化元素列表。
 *
 * 背景:成品练习页每题的「题给」视觉面板由站内手写的 figFor(qi)/fig(name)
 * 绘制函数生成(像素级定位元素),提取管道此前只收判分字段,视觉信息全部
 * 丢失(owner 2026-07-21 拍板完整恢复)。本脚本在编译期把绘制函数跑一遍,
 * 把**绘制结果**(确定性元素列表)作为数据带出——不改 41+ 站源码,不移植
 * 每张图。
 *
 * 输出(stdout JSON, 键排序确定性):
 *   { "<source_index>": { "label": "...", "caption": "...", "els": [...],
 *                          "h": <px>, "w": 334 }, ... }
 * els 元素字段白名单: x, top, w, h, bg, bd, r, fg, fs, fw, ai, jc, ta, p, lab
 * (px 坐标系, 画板宽 334 与成品页一致; 前端按比例缩放渲染)。
 *
 * 覆盖形态(2026-07-21 实测 44 源):
 *   - figFor(qi) + this.qAt(qi): 42 站 —— 用提取的题目数组 shim qAt;
 *   - fig(name)(A02): 按题目 fig 键逐个求值;
 *   - 模板分支(S07 figRuler/figPipe/...): 不可泛化求值, 显式记 SKIP 到 stderr
 *     (禁静默截断), 输出中无该站条目。
 *
 * 确定性: 绘制函数是常量算术, 无 Date/random/DOM 依赖; 沙箱内仅注入
 * Object/Math。同输入必同输出(digest 稳定)。
 */

const fs = require("fs");
const vm = require("vm");

const EL_FIELDS = ["x", "top", "w", "h", "bg", "bd", "r", "fg", "fs", "fw", "ai", "jc", "ta", "p", "lab"];
const BOARD_W = 334; // 成品页画板坐标系宽度(px)

function fail(msg) {
  process.stderr.write("extract_practice_fig_els: " + msg + "\n");
  process.exit(2);
}

// ── 平衡扫描: 与 practice_html.py::_array_after 同构(引号/转义安全) ──
function arrayAfter(html, markerRe) {
  const m = markerRe.exec(html);
  if (!m) return null;
  let i = html.indexOf("[", m.index + m[0].length - 1);
  if (i < 0) return null;
  let depth = 0, quote = null;
  for (let j = i; j < html.length; j += 1) {
    const ch = html[j];
    if (quote) {
      if (ch === "\\") j += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") { quote = ch; continue; }
    if (ch === "[") depth += 1;
    else if (ch === "]") {
      depth -= 1;
      if (depth === 0) return html.slice(i, j + 1);
    }
  }
  return null;
}

// 平衡扫描提取方法体: 命中 `name(args){` 后取到配对 `}`(含引号安全)。
function methodSource(html, headRe) {
  const m = headRe.exec(html);
  if (!m) return null;
  let i = html.indexOf("{", m.index + m[0].length - 1);
  if (i < 0) return null;
  let depth = 0, quote = null;
  for (let j = i; j < html.length; j += 1) {
    const ch = html[j];
    if (quote) {
      if (ch === "\\") j += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") { quote = ch; continue; }
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return html.slice(m.index, j + 1);
    }
  }
  return null;
}

function sandboxEval(code, context) {
  // 仅注入必需全局; 无 require/process/Date/Math.random(确定性红线)。
  const ctx = Object.assign({ Object: Object, Math: Math }, context || {});
  return vm.runInNewContext(code, ctx, { timeout: 5000 });
}

// 题目数组按提取管道同序拼装: Q/POOL 直取; bank 形态 A 组后接 Dg 组。
function questionRows(html) {
  const qSrc = arrayAfter(html, /\bQ\s*=\s*\[/);
  const poolSrc = arrayAfter(html, /\bPOOL\s*=\s*\[/);
  const direct = poolSrc || qSrc;
  if (direct) {
    const rows = sandboxEval("(" + direct + ")");
    return Array.isArray(rows) ? rows : null;
  }
  const rows = [];
  for (const marker of [/\bconst\s+A\s*=\s*\[/, /\bconst\s+Dg\s*=\s*\[/]) {
    const src = arrayAfter(html, marker);
    if (!src) continue;
    const part = sandboxEval("(" + src + ")");
    if (Array.isArray(part)) rows.push(...part);
  }
  return rows.length ? rows : null;
}

function normalizeEl(el) {
  const out = {};
  for (const key of EL_FIELDS) {
    const alias = key === "p" && el.p === undefined ? el.pad : el[key];
    if (alias === undefined || alias === null) continue;
    out[key] = typeof alias === "number" ? alias : String(alias);
  }
  return out;
}

// 文字亮度启发: 各站图形按各自页面主题作画(D12 深字浅底 / A02 浅字深底)。
// 取带文字元素的 fg 亮度中位判板底色, 避免浅字落白底隐形。确定性纯算术。
function hexLuminance(color) {
  const m = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(String(color || "").trim());
  if (!m) return null;
  let hex = m[1];
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const r = parseInt(hex.slice(0, 2), 16), g = parseInt(hex.slice(2, 4), 16), b = parseInt(hex.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

// 站级板底: 渲染器 D() 的默认 fg 是作者的主题声明(深字=浅板/浅字=深板),
// 一站一主题(与作画现实一致); 逐题启发会被 chip 白字污染, 弃用。
function boardBackgroundFromRenderer(rendererSrc) {
  const m = /fg\s*:\s*"(#[0-9a-fA-F]{3,6})"/.exec(rendererSrc || "");
  const lum = m ? hexLuminance(m[1]) : null;
  return lum !== null && lum > 0.62 ? "#23282b" : "#ffffff";
}

// ── S07 模板分支适配器 ──────────────────────────────────────────────
// S07 的题给图形不是 figFor/fig(name) 生成 els, 而是模板 sc-if 分支形态:
// viewmodel 按 q.fig 键("ruler"/"pipe"/"group"/"diag")点亮 figRuler/figPipe/
// figGroup/figDiag 布尔位, 模板各分支写死图形标记, 数据来自题目字段。此适配器
// 把模板各分支的标记与内联样式(全部来自 P40_S07.practice.dc.html 逐行常量)
// 翻译成与站内其它 44 源同构的 els 列表(334px 板坐标)。零臆造: 每个色值/文案/
// 档位区间均转写自模板, 数据(deathVal/lossVal 等)取题目字段(与 viewmodel 同默认)。

// 模板 <!-- fig: ruler --> 四档色带常量(bg/fg 逐段, 三行区间文案)。
const S07_SEG_BG = ["#dff0e6", "#fdeed1", "#fadcd6", "#f1c9c1"];
const S07_SEG_FG = ["#2c8a5b", "#c98a3e", "#cf4436", "#a3271c"];
const S07_RULER_HEADERS = ["一般", "较大", "重大", "特别重大"];
const S07_RULER_ROWS = [
  { label: "死亡", labelFg: "#cf4436", segFs: 8, segs: ["<3", "3~10", "10~30", "≥30"], valKey: "deathVal", colKey: "deathColor" },
  { label: "重伤", labelFg: "#8b9398", segFs: 7.5, segs: ["<10", "10~50", "50~100", "≥100"], valKey: "injuryVal", colKey: "injuryColor" },
  { label: "损失", labelFg: "#8b9398", segFs: 7.5, segs: ["<1000万", "1000~5000万", "5000万~1亿", "≥1亿"], valKey: "lossVal", colKey: "lossColor" },
];
// ruler 行几何: 左标签列 58, 四段色带 58→288, 右侧数值列 46(合计 334)。
const S07_SEG_X = [58, 115, 173, 230];
const S07_SEG_W = [57, 58, 57, 58];
const S07_VAL_X = 288;
const S07_VAL_W = 46;

function s07El(over) {
  // 只用 EL_FIELDS 白名单; 文字元素默认透明底(渲染器跳过 transparent)。
  return Object.assign({ bg: "transparent", p: "0" }, over);
}

function s07RulerEls(q) {
  const els = [];
  // 表头四档名(对齐四段色带)。
  for (let i = 0; i < 4; i += 1) {
    els.push(s07El({ x: S07_SEG_X[i], top: 0, w: S07_SEG_W[i], h: 12, fg: "#5c6469", fs: 8, fw: "800", ta: "center", lab: S07_RULER_HEADERS[i] }));
  }
  const rowTops = [15, 40, 63];
  const rowH = [20, 18, 18];
  S07_RULER_ROWS.forEach((row, r) => {
    const top = rowTops[r], h = rowH[r];
    // 行标签(死亡/重伤/损失), 左对齐。
    els.push(s07El({ x: 0, top: top, w: 58, h: h, fg: row.labelFg, fs: 10, fw: "800", ta: "left", jc: "flex-start", ai: "center", lab: row.label }));
    // 四段色带。
    for (let i = 0; i < 4; i += 1) {
      els.push(s07El({ x: S07_SEG_X[i], top: top, w: S07_SEG_W[i], h: h, bg: S07_SEG_BG[i], fg: S07_SEG_FG[i], fs: row.segFs, ta: "center", ai: "center", jc: "center", lab: row.segs[i] }));
    }
    // 右侧题给数值(色随题目字段, 默认灰 #9aa0a3 与 viewmodel 一致)。
    els.push(s07El({ x: S07_VAL_X, top: top, w: S07_VAL_W, h: h, fg: q[row.colKey] || "#9aa0a3", fs: 11, fw: "900", ta: "center", lab: String(q[row.valKey] || "—") }));
  });
  return { els: els, figH: 85 };
}

function s07PipeEls() {
  // <!-- fig: pipeline -->: 现场人员 —立即→ ？ —逐级→ 市级住建。
  const top = 8, h = 44;
  const els = [
    s07El({ x: 6, top: top, w: 58, h: h, bg: "#fff", bd: "2px solid #23282b", r: 8, fg: "#23282b", fs: 9.5, fw: "800", ta: "center", lab: "现场人员" }),
    s07El({ x: 68, top: top, w: 42, h: h, fg: "#cf4436", fs: 11, fw: "900", ta: "center", lab: "立即→" }),
    s07El({ x: 114, top: top, w: 50, h: h, bg: "#fff", bd: "2px dashed #cf4436", r: 8, fg: "#cf4436", fs: 18, fw: "900", ta: "center", lab: "？" }),
    s07El({ x: 168, top: top, w: 42, h: h, fg: "#2f6db0", fs: 11, fw: "900", ta: "center", lab: "逐级→" }),
    s07El({ x: 214, top: top, w: 58, h: h, bg: "#fff", bd: "2px solid #2f6db0", r: 8, fg: "#2f6db0", fs: 9.5, fw: "800", ta: "center", lab: "市级住建" }),
  ];
  return { els: els, figH: 58 };
}

function s07GroupEls() {
  // <!-- fig: group -->: 已写三家单位(绿) + 四个法定空位(？虚线金)。
  const els = [
    s07El({ x: 0, top: 0, w: 334, h: 13, fg: "#2c8a5b", fs: 9, fw: "800", ta: "center", lab: "学生只写了 ↓" }),
  ];
  const filled = ["施工单位", "建设单位", "监理单位"];
  const filledX = [60, 134, 208];
  filled.forEach((t, i) => {
    els.push(s07El({ x: filledX[i], top: 18, w: 66, h: 22, bg: "#e8f4ee", fg: "#2c8a5b", bd: "1.5px solid #b6ddc8", r: 13, fs: 10, fw: "700", ta: "center", lab: t }));
  });
  const gapX = [67, 119, 171, 223];
  gapX.forEach((x) => {
    els.push(s07El({ x: x, top: 46, w: 44, h: 22, bg: "#fff", fg: "#c9a24a", bd: "1.5px dashed #d8b24a", r: 13, fs: 11, fw: "900", ta: "center", lab: "？" }));
  });
  return { els: els, figH: 72 };
}

function s07DiagEls(q) {
  // <!-- fig: diagnose -->: 标题 + 虚线卡内逐行考生作答(diagLines)。
  const lines = Array.isArray(q.diagLines) ? q.diagLines : [];
  const boxTop = 17, pad = 10, lineH = 22;
  const boxH = pad * 2 + Math.max(lines.length, 1) * lineH;
  const els = [
    s07El({ x: 0, top: 0, w: 334, h: 14, fg: "#cf4436", fs: 9, fw: "800", ta: "left", jc: "flex-start", lab: "某考生的作答（请诊断）" }),
    // 卡片底(先入数组=底层, 后续行文本叠其上)。
    s07El({ x: 0, top: boxTop, w: 334, h: boxH, bg: "#fbfaf3", bd: "1.5px dashed #cf8a44", r: 8 }),
  ];
  lines.forEach((ln, i) => {
    els.push(s07El({ x: 12, top: boxTop + pad + i * lineH, w: 310, h: lineH, fg: "#3a3f42", fs: 12, ta: "left", jc: "flex-start", ai: "center", lab: String((ln && ln.t) || "") }));
  });
  return { els: els, figH: boxTop + boxH + 2 };
}

// S07 figLabel/figCaption 从 viewmodel(renderVals)对该题的取值逻辑逐字推导。
function s07FigLabel(q) {
  if (q.fig === "ruler") return (q.lossVal || "—") !== "—" ? "变化图 · 含经济损失" : "题给数据图";
  if (q.fig === "pipe") return "上报路径图";
  if (q.fig === "group") return "调查组诊断图";
  return "作答诊断图";
}

function s07FigCaption(q) {
  if (q.fig === "ruler" || q.fig === "diag") return String(q.diagBg || "");
  if (q.fig === "pipe") return "报告对象 / 时限 / 内容 —— 你来补";
  return "法定成员的空位，等你填满（漏一类扣一处）";
}

function s07FigRaw(q) {
  if (q.fig === "ruler") return s07RulerEls(q);
  if (q.fig === "pipe") return s07PipeEls();
  if (q.fig === "group") return s07GroupEls();
  if (q.fig === "diag") return s07DiagEls(q);
  return null;
}

function normalizeFig(raw, label, caption, boardBg) {
  const els = (raw && Array.isArray(raw.els) ? raw.els : []).map(normalizeEl);
  if (!els.length) return null;
  const h = Number(raw.figH !== undefined ? raw.figH : raw.h);
  return {
    label: String(label || ""),
    caption: String(caption || ""),
    els: els,
    h: Number.isFinite(h) && h > 0 ? h : 100,
    w: BOARD_W,
    bg: boardBg || "#ffffff",
  };
}

function main() {
  const path = process.argv[2];
  if (!path) fail("usage: extract_practice_fig_els.js <practice.dc.html>");
  let html;
  try {
    html = fs.readFileSync(path, "utf-8");
  } catch (err) {
    fail("unreadable: " + path);
  }
  const rows = questionRows(html);
  if (!rows) fail("question array not found: " + path);

  const figForSrc = methodSource(html, /\bfigFor\s*\(\s*qi\s*\)\s*\{/);
  const figNameSrc = figForSrc ? null : methodSource(html, /(?<![A-Za-z0-9_$])fig\s*\(\s*name\s*\)\s*\{/);

  const out = {};
  const boardBg = boardBackgroundFromRenderer(figForSrc || figNameSrc);
  if (figForSrc) {
    // figFor(qi){...} 依赖 this.qAt(qi) 或 this.Q[qi](实测两形态); shim 后逐题求值。
    const fn = sandboxEval("(function " + figForSrc + ")");
    rows.forEach((q, idx) => {
      let raw;
      try {
        raw = fn.call({ qAt: (i) => rows[i], Q: rows }, idx);
      } catch (err) {
        process.stderr.write(`SKIP q${idx + 1} figFor error: ${err.message}\n`);
        return;
      }
      const fig = normalizeFig(raw, q.figLabel, q.figCaption, boardBg);
      if (fig) out[String(idx)] = fig;
    });
  } else if (figNameSrc) {
    // fig(name){...}(A02 形态): 按题目 fig 键求值; label 兼容 top 字段。
    const fn = sandboxEval("(function " + figNameSrc + ")");
    rows.forEach((q, idx) => {
      if (!q || !q.fig) return;
      let raw;
      try {
        raw = fn.call({}, String(q.fig));
      } catch (err) {
        process.stderr.write(`SKIP q${idx + 1} fig(name) error: ${err.message}\n`);
        return;
      }
      const fig = normalizeFig(raw, q.figLabel || q.top, q.figCaption || q.sub, boardBg);
      if (fig) out[String(idx)] = fig;
    });
  } else if (/\{\{\s*figRuler\s*\}\}/.test(html) && rows.some((q) => q && q.fig)) {
    // 模板分支形态(S07): viewmodel 按 q.fig 键点亮 figRuler/figPipe/figGroup/
    // figDiag, 模板各分支写死图形标记。适配器把分支翻译成 els(见 s07*Els)。
    const boardBgS07 = "#ffffff"; // 模板 FIGURE 卡 background:#fff。
    rows.forEach((q, idx) => {
      if (!q || !q.fig) return;
      const raw = s07FigRaw(q);
      if (!raw) {
        process.stderr.write(`SKIP q${idx + 1} S07 unknown fig key: ${q.fig}\n`);
        return;
      }
      const fig = normalizeFig(raw, s07FigLabel(q), s07FigCaption(q), boardBgS07);
      if (fig) out[String(idx)] = fig;
    });
  } else {
    // 其它模板分支形态: 图形在模板标记里, 无法泛化求值——显式跳过。
    process.stderr.write("SKIP station: no evaluable fig renderer (template-branch figures)\n");
  }

  // 键序确定性: 数字键按 JS 对象语义天然升序, 元素字段按白名单构造序。
  process.stdout.write(JSON.stringify(out));
}

main();
