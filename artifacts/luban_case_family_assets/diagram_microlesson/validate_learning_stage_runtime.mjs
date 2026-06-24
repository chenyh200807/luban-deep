#!/usr/bin/env node
// Runtime layout gate for Luban learning-stage HTML previews.
// It opens the rendered page in headless Chrome and checks real viewport geometry
// for portrait, landscape, wide, and theater states.

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [, , input] = process.argv;
if (!input || process.argv.includes("--help") || process.argv.includes("-h")) {
  console.error("usage: node validate_learning_stage_runtime.mjs <rendered.html>");
  process.exit(input ? 0 : 2);
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const renderedPath = resolve(input);
const userDir = mkdtempSync(join(tmpdir(), "learning-stage-gate-"));
const PORT = 9900 + Math.floor(Math.random() * 500);

const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${userDir}`,
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-extensions",
  "--hide-scrollbars",
  "--force-device-scale-factor=2",
], { stdio: "ignore" });

const cleanup = () => {
  try { chrome.kill("SIGKILL"); } catch {}
  try { rmSync(userDir, { recursive: true, force: true }); } catch {}
};
process.on("exit", cleanup);

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

async function wsEndpoint() {
  for (let i = 0; i < 60; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json`);
      const targets = await response.json();
      const page = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(100);
  }
  throw new Error("chrome page target not ready");
}

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
  const send = (method, params = {}) => new Promise((resolveSend, rejectSend) => {
    const currentId = ++id;
    pending.set(currentId, (message) => {
      if (message.error) rejectSend(new Error(`${method}: ${JSON.stringify(message.error)}`));
      else resolveSend(message);
    });
    ws.send(JSON.stringify({ id: currentId, method, params }));
  });
  return { send };
}

const setupPlayingTrial = `
(() => {
  const lesson = document.querySelector(".lesson");
  const audio = document.querySelector("audio");
  if (lesson) lesson.classList.add("started");
  if (audio) audio.currentTime = 45;
  if (typeof paint === "function") paint();
})();
`;

const setupTheater = `
(() => {
  const lesson = document.querySelector(".lesson");
  const audio = document.querySelector("audio");
  const toggle = document.querySelector("[data-theater-toggle]");
  if (lesson) lesson.classList.add("started");
  if (audio) audio.currentTime = 45;
  if (typeof paint === "function") paint();
  if (toggle) toggle.click();
})();
`;

const scenarios = [
  {
    name: "portrait_initial_decision",
    viewport: { width: 390, height: 844, mobile: true },
    setup: "",
    minStageRatio: 0.28,
    expectDecision: true,
    expectControls: false,
    expectCenterPlay: true,
  },
  {
    name: "portrait_playing_trial",
    viewport: { width: 390, height: 844, mobile: true },
    setup: setupPlayingTrial,
    minStageRatio: 0.25,
    expectControls: true,
    expectSemanticChapters: true,
  },
  {
    name: "landscape_playing_trial",
    viewport: { width: 844, height: 390, mobile: true },
    setup: setupPlayingTrial,
    minStageRatio: 0.42,
    expectControls: true,
    expectLandscapeStage: true,
    expectSemanticChapters: true,
  },
  {
    name: "wide_playing_trial",
    viewport: { width: 1024, height: 720, mobile: false },
    setup: setupPlayingTrial,
    minStageRatio: 0.34,
    expectControls: true,
    expectLandscapeStage: true,
    expectSemanticChapters: true,
  },
  {
    name: "portrait_theater_controls",
    viewport: { width: 390, height: 844, mobile: true },
    setup: setupTheater,
    minStageRatio: 0.62,
    expectControls: true,
    expectTheater: true,
  },
];

function assertionMessage(scenario, check, message) {
  return `${scenario.name} ${check}: ${message}`;
}

function assertScenario(scenario, snapshot) {
  const failures = [];
  const warnings = [];
  const fail = (check, message) => failures.push(assertionMessage(scenario, check, message));
  const warn = (check, message) => warnings.push(assertionMessage(scenario, check, message));

  const { viewport, boxes, overflow, lessonClasses, chapterLabels, textOverflows, theaterToggleExists } = snapshot;
  const stage = boxes.stage;
  const controls = boxes.controls;
  const quickOptions = boxes.quickOptions;
  const centerPlay = boxes.centerPlay;
  const caption = boxes.caption;

  if (!lessonClasses.includes("orientation-adaptive")) {
    fail("orientation_adaptive", "lesson shell must declare orientation-adaptive");
  }
  if (overflow.x > 2) {
    fail("horizontal_overflow", `scrollWidth exceeds viewport by ${overflow.x}px`);
  }
  if (!stage?.visible) {
    fail("stage_visible", "stage is missing or not visible");
  } else {
    if (stage.rect.width < Math.min(320, viewport.width * 0.72)) {
      fail("stage_width", `stage too narrow: ${Math.round(stage.rect.width)}px`);
    }
    if (stage.rect.height < Math.min(260, viewport.height * 0.34)) {
      fail("stage_height", `stage too short: ${Math.round(stage.rect.height)}px`);
    }
    if (stage.visibleRatio < scenario.minStageRatio) {
      fail("stage_viewport_ratio", `stage visible ratio ${stage.visibleRatio.toFixed(2)} < ${scenario.minStageRatio}`);
    }
  }

  if (caption && !caption.visible && !scenario.expectTheater) {
    fail("caption_visible", "caption/coach card should be visible outside theater");
  }
  if (scenario.expectDecision && !quickOptions?.visible) {
    fail("decision_first", "initial decision options must be visible before playback");
  }
  if (scenario.expectCenterPlay && !centerPlay?.visible) {
    fail("center_play", "central play affordance must be visible before playback");
  }
  if (scenario.expectControls && !controls?.visible) {
    fail("controls_visible", "controls should be visible in this playback state");
  }
  if (scenario.expectControls && controls?.visible && controls.rect.height > viewport.height * 0.32) {
    fail("controls_height", `controls consume too much height: ${Math.round(controls.rect.height)}px`);
  }
  if (scenario.expectSemanticChapters) {
    if (chapterLabels.length < 3) {
      fail("chapter_labels", "semantic chapter buttons not found");
    } else if (chapterLabels.every((label) => /^\\d+$/.test(label))) {
      fail("chapter_labels", `chapter labels are numeric only: ${chapterLabels.join("/")}`);
    }
  }
  if (scenario.expectLandscapeStage && stage?.visible) {
    const ratio = stage.rect.width / Math.max(1, stage.rect.height);
    if (ratio < 1.12) {
      fail("landscape_stage", `wide/landscape stage still looks like a narrow vertical strip: ${ratio.toFixed(2)}`);
    }
  }
  if (scenario.expectTheater) {
    if (!theaterToggleExists) {
      fail("theater_toggle", "real theater/fullscreen toggle is missing; gate must not add theater class directly");
    }
    if (!lessonClasses.includes("theater")) {
      fail("theater_class", "theater class did not stick after setup");
    }
    if (!stage?.visible || stage.rect.top > 2 || stage.rect.left > 2) {
      fail("theater_stage_origin", "theater stage must start at viewport origin");
    }
    if (stage?.visible && stage.rect.width < viewport.width - 2) {
      fail("theater_stage_width", `theater stage width ${Math.round(stage.rect.width)}px < viewport width`);
    }
    if (stage?.visible && stage.rect.height < viewport.height * 0.58) {
      fail("theater_stage_height", `theater stage height ${Math.round(stage.rect.height)}px is too small`);
    }
    if (controls?.visible && controls.rect.bottom > viewport.height + 2) {
      fail("theater_controls_bottom", "theater controls overflow below viewport");
    }
    if (stage?.visible && controls?.visible && stage.rect.bottom > controls.rect.top + 16) {
      fail("theater_overlap", "controls overlap the active learning stage");
    }
    if (boxes.rail?.visible || boxes.topline?.visible || boxes.nav?.visible) {
      fail("theater_chrome", "theater mode must hide page chrome");
    }
  }

  if (textOverflows.length) {
    warn("button_text_overflow", `${textOverflows.length} visible button-like elements overflow: ${textOverflows.slice(0, 4).join(", ")}`);
  }
  return { failures, warnings };
}

const collectSnapshotExpression = `
(() => {
  const selectors = {
    lesson: ".lesson",
    stage: ".stage",
    visual: ".visual",
    scene: ".scene",
    caption: ".caption",
    quickOptions: ".quick-options",
    controls: ".controls",
    nav: ".nav",
	    centerPlay: ".center-play",
	    theaterToggle: "[data-theater-toggle]",
    chapters: ".chapters",
    scrubber: ".scrubber",
    rail: ".rail",
    topline: ".topline"
  };
  const viewport = { width: innerWidth, height: innerHeight };
  const visibleBox = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const visibleWidth = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0));
    const visibleHeight = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
    const visibleArea = visibleWidth * visibleHeight;
    const visible = style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.02 && rect.width > 0 && rect.height > 0 && visibleArea > 1;
    return {
      selector,
      visible,
      display: style.display,
      opacity: Number(style.opacity || 1),
      rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
      visibleArea,
      visibleRatio: visibleArea / Math.max(1, innerWidth * innerHeight)
    };
  };
  const boxes = Object.fromEntries(Object.entries(selectors).map(([key, selector]) => [key, visibleBox(selector)]));
  const chapterLabels = [...document.querySelectorAll(".beat-dot")]
    .filter((element) => visibleBox("#" + (element.id || "missing"))?.visible || getComputedStyle(element).display !== "none")
    .map((element) => element.textContent.trim())
    .filter(Boolean);
  const buttonLike = [...document.querySelectorAll("button, .nav a")];
  const textOverflows = buttonLike
    .filter((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      if (style.display === "none" || style.visibility === "hidden" || rect.width <= 0 || rect.height <= 0) return false;
      return element.scrollWidth > element.clientWidth + 2;
    })
    .map((element) => element.textContent.trim().slice(0, 24))
    .filter(Boolean);
  const lesson = document.querySelector(".lesson");
  return {
    viewport,
    overflow: {
      x: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      y: Math.max(0, document.documentElement.scrollHeight - innerHeight)
    },
	    lessonClasses: lesson ? [...lesson.classList] : [],
	    theaterToggleExists: !!document.querySelector("[data-theater-toggle]"),
	    boxes,
    chapterLabels,
    textOverflows
  };
})();
`;

async function runScenario(send, scenario) {
  const { width, height, mobile } = scenario.viewport;
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 2,
    mobile,
  });
  await send("Page.navigate", { url: "file://" + renderedPath });
  for (let i = 0; i < 60; i += 1) {
    const ready = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
    if (ready.result?.result?.value === "complete") break;
    await sleep(100);
  }
  await sleep(300);
  if (scenario.setup) {
    await send("Runtime.evaluate", { expression: scenario.setup, awaitPromise: false });
    await sleep(150);
  }
  const snapshotResult = await send("Runtime.evaluate", {
    expression: collectSnapshotExpression,
    returnByValue: true,
  });
  const snapshot = snapshotResult.result?.result?.value;
  return assertScenario(scenario, snapshot);
}

(async () => {
  const wsUrl = await wsEndpoint();
  const ws = new WebSocket(wsUrl);
  await new Promise((resolveOpen) => ws.addEventListener("open", resolveOpen, { once: true }));
  const { send } = cdp(ws);
  await send("Page.enable");
  await send("Runtime.enable");

  const allFailures = [];
  const allWarnings = [];
  for (const scenario of scenarios) {
    const { failures, warnings } = await runScenario(send, scenario);
    allFailures.push(...failures);
    allWarnings.push(...warnings);
    if (failures.length) {
      console.log(`FAIL ${scenario.name}: ${failures.length} fail, ${warnings.length} warn`);
    } else {
      console.log(`PASS ${scenario.name}: ${warnings.length} warn`);
    }
  }

  allWarnings.forEach((warning) => console.log(`WARN ${warning}`));
  allFailures.forEach((failure) => console.error(`FAIL ${failure}`));

  ws.close();
  cleanup();
  if (allFailures.length) {
    console.error(`learning-stage runtime gate: FAIL (${allFailures.length} fail, ${allWarnings.length} warn)`);
    process.exit(1);
  }
  console.log(`learning-stage runtime gate: PASS (${allWarnings.length} warn)`);
  process.exit(0);
})().catch((error) => {
  console.error(error);
  cleanup();
  process.exit(1);
});
