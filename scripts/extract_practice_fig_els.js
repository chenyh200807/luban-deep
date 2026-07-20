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
  } else {
    // 模板分支形态(S07): 图形在模板标记里, 无法泛化求值——显式跳过。
    process.stderr.write("SKIP station: no evaluable fig renderer (template-branch figures)\n");
  }

  // 键序确定性: 数字键按 JS 对象语义天然升序, 元素字段按白名单构造序。
  process.stdout.write(JSON.stringify(out));
}

main();
