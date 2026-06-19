#!/usr/bin/env node
// Gate for OpenMAIC-style luban_animation_ir.v0 previews.
// It validates the IR as the single animation authority, then opens the HTML
// preview and checks real DOM state: one scene, bounded visible nodes, one
// keycard, theater challenge CTA, and no reached-* accumulation.

import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";

const [, , irArg, htmlArg] = process.argv;
if (!irArg || !htmlArg || process.argv.includes("--help") || process.argv.includes("-h")) {
  console.error("usage: node validate_animation_ir_preview.mjs <animation_ir.v0.json> <preview.html>");
  process.exit(irArg || htmlArg ? 0 : 2);
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const irPath = resolve(irArg);
const htmlPath = resolve(htmlArg);
const results = [];
const pass = (check, message) => results.push({ level: "PASS", check, message });
const warn = (check, message) => results.push({ level: "WARN", check, message });
const fail = (check, message) => results.push({ level: "FAIL", check, message });

function readJson(path) {
  if (!existsSync(path)) {
    fail("file_exists", `missing ${path}`);
    return null;
  }
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    fail("json_parse", `${basename(path)}: ${error.message}`);
    return null;
  }
}

function readText(path) {
  if (!existsSync(path)) {
    fail("file_exists", `missing ${path}`);
    return "";
  }
  return readFileSync(path, "utf8");
}

function checkStatic(ir, html) {
  if (!ir) return;
  ir.schema_version === "luban_animation_ir.v0"
    ? pass("schema_version", "schema_version is luban_animation_ir.v0")
    : fail("schema_version", "expected schema_version=luban_animation_ir.v0");

  const scenes = Array.isArray(ir.scenes) ? ir.scenes : [];
  scenes.length >= 6 ? pass("scene_count", `${scenes.length} scenes`) : fail("scene_count", "expected at least 6 scenes");

  const required = ["id", "label", "start_sec", "end_sec", "scene", "focus", "enter", "exit", "layout", "camera", "visible_nodes", "keycard", "coach"];
  const ids = new Set();
  let prevEnd = -Infinity;
  for (const scene of scenes) {
    for (const key of required) {
      if (!(key in scene)) fail("scene_required_fields", `${scene.id || "(missing id)"} missing ${key}`);
    }
    if (ids.has(scene.id)) fail("scene_unique_id", `duplicate scene id ${scene.id}`);
    ids.add(scene.id);
    if (!(Number(scene.start_sec) < Number(scene.end_sec))) {
      fail("scene_timing", `${scene.id} start_sec must be < end_sec`);
    }
    if (Number(scene.start_sec) < prevEnd - 0.001) {
      fail("scene_overlap", `${scene.id} starts before previous scene ends`);
    }
    prevEnd = Number(scene.end_sec);
    const maxNodes = Number(ir.render_contract?.max_visible_nodes ?? 4);
    const visibleNodes = Array.isArray(scene.visible_nodes) ? scene.visible_nodes : [];
    visibleNodes.length <= maxNodes
      ? pass("scene_visible_budget", `${scene.id}: ${visibleNodes.length}/${maxNodes}`)
      : fail("scene_visible_budget", `${scene.id}: ${visibleNodes.length} visible nodes > ${maxNodes}`);
  }

  if (/reached-/i.test(html)) {
    fail("no_reached_accumulation", "preview must not use reached-* cumulative state");
  } else {
    pass("no_reached_accumulation", "no reached-* classes or logic found");
  }
  if (!/data-animation-ir-preview=["']v0["']/.test(html)) {
    fail("ir_preview_marker", "missing data-animation-ir-preview=v0 marker");
  } else {
    pass("ir_preview_marker", "HTML declares animation IR preview v0");
  }
  if (!/window\.__IR_PLAYER__/.test(html)) {
    fail("ir_player_api", "missing window.__IR_PLAYER__ test API");
  } else {
    pass("ir_player_api", "has window.__IR_PLAYER__ test API");
  }
  if (!/data-challenge-cta/.test(html) || !/\.practice\.html/.test(html)) {
    fail("challenge_cta", "preview must expose a challenge CTA to independent practice");
  } else {
    pass("challenge_cta", "has challenge CTA and practice link");
  }
  if (!/type=["']range["']/.test(html)) {
    fail("scrubber", "missing draggable range scrubber");
  } else {
    pass("scrubber", "has draggable range scrubber");
  }
  if (!/data-caption=["']1["']/.test(html) || !/"segments"\s*:/.test(html)) {
    fail("captions", "preview must expose timing-derived captions");
  } else {
    pass("captions", "has timing-derived captions");
  }
  if (!/"actions"\s*:/.test(html) || !/\.kind===['"]reveal/.test(html) || !/\.kind===['"]camera/.test(html)) {
    fail("action_playback", "preview must expose and consume an action queue");
  } else {
    pass("action_playback", "has deterministic action queue playback");
  }
  if (!/controls-visible/.test(html)) {
    fail("theater_controls_autohide", "theater controls must use show/hide state");
  } else {
    pass("theater_controls_autohide", "has controls-visible show/hide state");
  }

  const internalTokens = [/source_ref/i, /schema_version/i, /candidate/i, /official_score_allowed/i, /\bE\d{2}\b/, /\bP\d{2,}\b/];
  const hit = internalTokens.find((re) => re.test(html));
  if (hit) warn("student_safe_tokens", `student preview contains possible internal token ${hit}`);
  else pass("student_safe_tokens", "no obvious internal authority tokens in preview HTML");
}

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

async function wsEndpoint(port) {
  for (let i = 0; i < 80; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json`);
      const targets = await response.json();
      const page = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(100);
  }
  throw new Error("Chrome CDP target not ready");
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

async function checkRuntime(ir) {
  if (!ir || !existsSync(CHROME)) {
    warn("runtime", "Chrome unavailable or IR invalid; skipped DOM runtime gate");
    return;
  }
  const port = 10300 + Math.floor(Math.random() * 500);
  const userDir = mkdtempSync(join(tmpdir(), "animation-ir-gate-"));
  const chrome = spawn(CHROME, [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--force-device-scale-factor=2",
  ], { stdio: "ignore" });

  const cleanup = () => {
    try { chrome.kill("SIGKILL"); } catch {}
    try { rmSync(userDir, { recursive: true, force: true }); } catch {}
  };

  try {
    const endpoint = await wsEndpoint(port);
    const ws = new WebSocket(endpoint);
    await new Promise((resolveOpen, rejectOpen) => {
      ws.addEventListener("open", resolveOpen, { once: true });
      ws.addEventListener("error", rejectOpen, { once: true });
    });
    const client = cdp(ws);
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await client.send("Page.navigate", { url: `file://${htmlPath}` });
    await new Promise((resolveLoad) => {
      const handler = (event) => {
        const message = JSON.parse(event.data);
        if (message.method === "Page.loadEventFired") {
          ws.removeEventListener("message", handler);
          resolveLoad();
        }
      };
      ws.addEventListener("message", handler);
    });

    const maxNodes = Number(ir.render_contract?.max_visible_nodes ?? 4);
    const samples = [
      ir.scenes[0],
      ir.scenes[Math.min(1, ir.scenes.length - 1)],
      ir.scenes.find((scene) => scene.id === "score"),
      ir.scenes.find((scene) => scene.id === "qa_closure"),
      ir.scenes.find((scene) => scene.id === "closing_challenge"),
    ].filter(Boolean);

    for (const scene of samples) {
      const sceneStart = Number(scene.start_sec);
      const sceneEnd = Number(scene.end_sec);
      const sceneDur = Math.max(0.8, sceneEnd - sceneStart);
      const t = sceneStart + Math.min(2.5, Math.max(0.8, sceneDur * 0.45));
      const expression = `
        (() => {
          window.__IR_PLAYER__.seek(${JSON.stringify(t)});
          const visible = (el) => {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return cs.display !== "none" && cs.visibility !== "hidden" && Number(cs.opacity || 1) > 0.05 && r.width > 1 && r.height > 1;
          };
          const activeScenes = [...document.querySelectorAll(".scene.active")];
          const active = activeScenes[0];
        return {
          state: window.__IR_PLAYER__.state(),
          activeScenes: activeScenes.length,
          visibleNodes: active ? [...active.querySelectorAll("[data-visible-node]")].filter(visible).map((el) => el.dataset.visibleNode) : [],
          keycards: active ? [...active.querySelectorAll(".coach-card")].filter(visible).length : 0,
          caption: document.querySelector("[data-caption]")?.textContent?.trim() || "",
          challengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter(visible).length
        };
        })()
      `;
      const response = await client.send("Runtime.evaluate", { expression, returnByValue: true });
      const value = response.result.result.value;
      if (value.activeScenes !== 1) fail("runtime_one_active_scene", `${scene.id}: ${value.activeScenes} active scenes`);
      else pass("runtime_one_active_scene", `${scene.id}: one active scene`);
      if (value.visibleNodes.length > maxNodes) fail("runtime_visible_budget", `${scene.id}: ${value.visibleNodes.length} visible nodes > ${maxNodes}`);
      else pass("runtime_visible_budget", `${scene.id}: ${value.visibleNodes.length}/${maxNodes}`);
      if (value.visibleNodes.length < 1) fail("runtime_visible_progress", `${scene.id}: no visible node after scene midpoint`);
      else pass("runtime_visible_progress", `${scene.id}: progressive reveal produced visible nodes`);
      if (value.keycards !== 1) fail("runtime_keycard_budget", `${scene.id}: ${value.keycards} visible keycards`);
      else pass("runtime_keycard_budget", `${scene.id}: one keycard`);
      if (!value.caption) fail("runtime_caption", `${scene.id}: caption is empty`);
      else pass("runtime_caption", `${scene.id}: caption visible`);
      if (scene.id === "closing_challenge" && value.challengeCtas < 1) {
        fail("runtime_challenge_cta", "closing scene has no visible challenge CTA");
      }
    }

    const theaterExpression = `
      (() => {
        document.querySelector("[data-theater-toggle]")?.click();
        window.__IR_PLAYER__.seek(${JSON.stringify(ir.scenes.at(-1).start_sec + 0.2)});
        const visible = (el) => {
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 1 && r.height > 1;
        };
        return {
          theater: document.querySelector(".lesson")?.classList.contains("theater"),
          controlsVisible: document.querySelector(".lesson")?.classList.contains("controls-visible"),
          challengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter(visible).length,
          stageRect: document.querySelector(".stage")?.getBoundingClientRect().toJSON(),
          viewport: { width: innerWidth, height: innerHeight }
        };
      })()
    `;
    const theaterResponse = await client.send("Runtime.evaluate", { expression: theaterExpression, returnByValue: true });
    const theater = theaterResponse.result.result.value;
    theater.theater ? pass("runtime_theater", "theater class toggled") : fail("runtime_theater", "theater class did not toggle");
    theater.controlsVisible ? pass("runtime_theater_controls_visible", "theater controls show after tap/toggle") : fail("runtime_theater_controls_visible", "theater controls did not show after tap/toggle");
    theater.challengeCtas >= 1 ? pass("runtime_theater_challenge_cta", "theater keeps challenge CTA") : fail("runtime_theater_challenge_cta", "theater hides all challenge CTAs");
    if (theater.stageRect && theater.stageRect.width < theater.viewport.width - 4) {
      fail("runtime_theater_stage", `stage width ${Math.round(theater.stageRect.width)} < viewport`);
    } else {
      pass("runtime_theater_stage", "theater stage spans viewport width");
    }
    ws.close();
  } catch (error) {
    fail("runtime", error.message);
  } finally {
    cleanup();
  }
}

const ir = readJson(irPath);
const html = readText(htmlPath);
checkStatic(ir, html);
await checkRuntime(ir);

for (const result of results) {
  console.log(`${result.level} ${basename(irPath)} ${result.check}: ${result.message}`);
}

const failCount = results.filter((result) => result.level === "FAIL").length;
const warnCount = results.filter((result) => result.level === "WARN").length;
if (failCount) {
  console.error(`animation IR preview gate: FAIL (${failCount} fail, ${warnCount} warn)`);
  process.exit(1);
}
console.log(`animation IR preview gate: PASS (${warnCount} warn)`);
