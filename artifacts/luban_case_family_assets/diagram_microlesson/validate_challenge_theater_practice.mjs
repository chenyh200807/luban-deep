#!/usr/bin/env node
// Runtime gate for the experimental Challenge Theater practice shell.
// It checks mobile space use before we promote the pattern into the workflow.

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [, , input] = process.argv;
if (!input || process.argv.includes("--help") || process.argv.includes("-h")) {
  console.error("usage: node validate_challenge_theater_practice.mjs <practice.html>");
  process.exit(input ? 0 : 2);
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const viewports = [
  { name: "portrait_390", width: 390, height: 844 },
  { name: "portrait_360", width: 360, height: 740 },
  { name: "landscape_844", width: 844, height: 390 },
  { name: "desktop_landscape_1432", width: 1432, height: 900, mobile: false },
];
const results = [];
const add = (level, check, message) => results.push({ level, check, message });
const pass = (check, message) => add("PASS", check, message);
const fail = (check, message) => add("FAIL", check, message);
const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

function cdp(ws) {
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  });
  const send = (method, params = {}) =>
    new Promise((resolveSend, reject) => {
      const callId = ++id;
      pending.set(callId, (message) => {
        if (message.error) reject(new Error(`${method}: ${JSON.stringify(message.error)}`));
        else resolveSend(message);
      });
      ws.send(JSON.stringify({ id: callId, method, params }));
    });
  return { send };
}

async function pageEndpoint(port) {
  for (let i = 0; i < 50; i++) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json`);
      const targets = await response.json();
      const page = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(100);
  }
  throw new Error("chrome page target not ready");
}

async function withChrome(viewport, fn) {
  const userDir = mkdtempSync(join(tmpdir(), "challenge-theater-"));
  const port = 9400 + Math.floor(Math.random() * 500);
  const chrome = spawn(CHROME, [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--hide-scrollbars",
  ], { stdio: "ignore" });
  const cleanup = () => {
    try { chrome.kill("SIGKILL"); } catch {}
    try { rmSync(userDir, { recursive: true, force: true }); } catch {}
  };
  try {
    const ws = new WebSocket(await pageEndpoint(port));
    await new Promise((resolveOpen) => ws.addEventListener("open", resolveOpen, { once: true }));
    const { send } = cdp(ws);
    await send("Page.enable");
    await send("Runtime.enable");
    await send("Emulation.setDeviceMetricsOverride", {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: viewport.mobile === false ? 1 : 2,
      mobile: viewport.mobile !== false,
    });
    await send("Page.navigate", { url: "file://" + resolve(input) });
    for (let i = 0; i < 60; i++) {
      const state = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
      if (state.result?.result?.value === "complete") break;
      await sleep(100);
    }
    await sleep(250);
    await fn(send);
    ws.close();
  } finally {
    cleanup();
  }
}

function checkMetric(viewport, metric) {
  const pfx = `${viewport.name}`;
  metric.shell === "challenge-theater"
    ? pass("shell", `${pfx}: challenge theater shell`)
    : fail("shell", `${pfx}: missing challenge theater shell`);
  metric.horizontalOverflow <= 1
    ? pass("horizontal_overflow", `${pfx}: no horizontal overflow`)
    : fail("horizontal_overflow", `${pfx}: overflow ${metric.horizontalOverflow}px`);
  const visualMin = viewport.width > viewport.height ? 0.54 : 0.30;
  const visualMax = viewport.width > viewport.height ? 0.72 : 0.42;
  metric.visualRatio >= visualMin && metric.visualRatio <= visualMax
    ? pass("visual_ratio", `${pfx}: diagram ratio ${(metric.visualRatio * 100).toFixed(1)}%`)
    : fail("visual_ratio", `${pfx}: diagram ratio ${(metric.visualRatio * 100).toFixed(1)}% outside ${(visualMin * 100).toFixed(0)}-${(visualMax * 100).toFixed(0)}%`);
  metric.promptChars <= 42
    ? pass("short_prompt", `${pfx}: prompt ${metric.promptChars} chars`)
    : fail("short_prompt", `${pfx}: prompt too long ${metric.promptChars} chars`);
  metric.optionChars <= 92
    ? pass("compact_options", `${pfx}: visible option labels ${metric.optionChars} chars`)
    : fail("compact_options", `${pfx}: options too verbose ${metric.optionChars} chars`);
  !metric.fullStemVisible
    ? pass("stem_collapsed", `${pfx}: full stem collapsed`)
    : fail("stem_collapsed", `${pfx}: full stem visible by default`);
  !metric.drawerOpen
    ? pass("option_drawer_collapsed", `${pfx}: option drawer collapsed`)
    : fail("option_drawer_collapsed", `${pfx}: option drawer open by default`);
  metric.touchMin >= 44
    ? pass("touch_targets", `${pfx}: min touch ${metric.touchMin}px`)
    : fail("touch_targets", `${pfx}: touch target ${metric.touchMin}px < 44`);
  metric.nextDisabled
    ? pass("answer_gate", `${pfx}: next disabled before answer`)
    : fail("answer_gate", `${pfx}: next not disabled before answer`);
  metric.navPosition !== "fixed" && metric.navPosition !== "sticky"
    ? pass("nav_not_overlay", `${pfx}: nav is in document flow`)
    : fail("nav_not_overlay", `${pfx}: nav uses ${metric.navPosition} overlay`);
  metric.clippedTextCount === 0
    ? pass("text_not_clipped", `${pfx}: visible text wraps without clipping`)
    : fail("text_not_clipped", `${pfx}: ${metric.clippedTextCount} visible text blocks overflow`);
  metric.svgStepOverflows === 0
    ? pass("svg_step_labels_fit", `${pfx}: SVG step labels fit their nodes`)
    : fail("svg_step_labels_fit", `${pfx}: ${metric.svgStepOverflows} SVG step labels overflow nodes`);
}

for (const viewport of viewports) {
  await withChrome(viewport, async (send) => {
    const expression = `(() => {
      const active = document.querySelector('.q.active');
      const rect = (node) => node ? node.getBoundingClientRect() : {height:0,width:0,right:0,bottom:0};
      const visible = (node) => {
        if (!node) return false;
        const style = getComputedStyle(node);
        const r = node.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      };
      const options = [...active.querySelectorAll('.option')].filter(visible);
      const controls = [...document.querySelectorAll('button,a,input,summary')].filter(visible);
      const textBlocks = [...active.querySelectorAll('.student-answer p, h2, .option span, .feedback.show, .option-drawer summary')].filter(visible);
      const clippedTextCount = textBlocks.filter((node) => node.scrollWidth > node.clientWidth + 1).length;
      const svgStepOverflows = [...active.querySelectorAll('svg .step')].filter((group) => {
        const label = group.querySelector('text');
        const shape = group.querySelector('rect,circle');
        if (!label || !shape || !label.getBBox) return false;
        const box = label.getBBox();
        const tag = shape.tagName.toLowerCase();
        if (tag === 'rect') {
          const width = Number(shape.getAttribute('width') || 0);
          const height = Number(shape.getAttribute('height') || 0);
          return box.width > width - 8 || box.height > height - 4;
        }
        const radius = Number(shape.getAttribute('r') || 0);
        return box.width > radius * 2 - 8 || box.height > radius * 2 - 4;
      }).length;
      const minTouch = Math.min(...controls.map((node) => Math.min(rect(node).height, rect(node).width)).filter(Boolean));
      const diagram = rect(active.querySelector('.diagram'));
      const prompt = active.querySelector('h2')?.innerText || '';
      return {
        shell: document.querySelector('.practice')?.dataset.practiceShell || '',
        horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        visualRatio: diagram.height / innerHeight,
        promptChars: prompt.trim().length,
        optionChars: options.map((node) => node.innerText.trim()).join('').length,
        fullStemVisible: visible(active.querySelector('.full-stem')),
        drawerOpen: !!active.querySelector('details[open]'),
        touchMin: Number.isFinite(minTouch) ? Math.floor(minTouch) : 0,
        nextDisabled: !!document.getElementById('nextQ')?.disabled,
        navPosition: getComputedStyle(document.querySelector('nav')).position,
        clippedTextCount,
        svgStepOverflows,
      };
    })()`;
    const metric = await send("Runtime.evaluate", { expression, returnByValue: true });
    checkMetric(viewport, metric.result.result.value);
  });
}

for (const result of results) {
  console.log(`${result.level} ${result.check}: ${result.message}`);
}

const fails = results.filter((result) => result.level === "FAIL").length;
if (fails) {
  console.error(`challenge theater practice gate: FAIL (${fails} fail)`);
  process.exit(1);
}
console.log("challenge theater practice gate: PASS");
