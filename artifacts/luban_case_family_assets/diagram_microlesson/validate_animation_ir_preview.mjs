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
  if (!/--player-h/.test(html) || !/ResizeObserver/.test(html)) {
    fail("dynamic_player_height", "renderer must derive shell spacing from measured player height, not fixed magic numbers");
  } else {
    pass("dynamic_player_height", "player height drives layout through CSS variable");
  }
  if (!/requestFullscreen/.test(html)) {
    fail("fullscreen_api_fallback", "theater toggle must attempt Fullscreen API with CSS fallback");
  } else {
    pass("fullscreen_api_fallback", "theater toggle attempts Fullscreen API");
  }
  if (!/aria-live=["']polite["']/.test(html) || !/aria-pressed=/.test(html)) {
    fail("player_a11y", "caption live region and button pressed state are required");
  } else {
    pass("player_a11y", "caption and controls expose basic accessibility state");
  }

  const dataMatch = html.match(/<script[^>]+id=["']irPreviewData["'][^>]*>([\s\S]*?)<\/script>/);
  if (!dataMatch) {
    fail("ir_html_equivalence", "missing #irPreviewData");
  } else {
    try {
      const preview = JSON.parse(dataMatch[1]);
      const htmlScenes = Array.isArray(preview.scenes) ? preview.scenes : [];
      const irSceneIds = scenes.map((scene) => scene.id);
      const htmlSceneIds = htmlScenes.map((scene) => scene.id);
      if (JSON.stringify(irSceneIds) !== JSON.stringify(htmlSceneIds)) {
        fail("ir_html_equivalence", `scene order drift: IR=${irSceneIds.join(",")} HTML=${htmlSceneIds.join(",")}`);
      } else {
        pass("ir_html_equivalence", "HTML preview data preserves IR scene order");
      }
      for (const scene of htmlScenes) {
        const irScene = scenes.find((candidate) => candidate.id === scene.id);
        if (!irScene) continue;
        const irNodes = JSON.stringify(irScene.visible_nodes || []);
        const htmlNodes = JSON.stringify(scene.visibleNodes || []);
        if (irNodes !== htmlNodes) fail("ir_html_visible_nodes", `${scene.id}: visibleNodes drift from IR`);
        const irVisualIds = (ir.visual_library?.[scene.id]?.nodes || []).map((node) => node.id);
        const htmlVisualIds = (scene.visual?.nodes || []).map((node) => node.id);
        if (JSON.stringify(irVisualIds) !== JSON.stringify(htmlVisualIds)) {
          fail("ir_html_visual_library", `${scene.id}: visual_library drift from IR`);
        }
        const actions = Array.isArray(scene.actions) ? scene.actions : [];
        const revealActions = actions.filter((action) => action.kind === "reveal");
        if (!revealActions.length) fail("ir_html_actions", `${scene.id}: no reveal actions`);
        for (const action of actions) {
          if (!(Number(action.start) <= Number(action.end))) fail("ir_html_actions", `${scene.id}: action ${action.kind}:${action.target} has invalid timing`);
          if (action.kind === "reveal" && !(scene.visibleNodes || []).includes(action.target)) {
            fail("ir_html_actions", `${scene.id}: reveal target ${action.target} is not in visibleNodes`);
          }
        }
      }
      if (!Number.isFinite(Number(preview.challengeUnlockSec))) {
        fail("challenge_unlock_static", "preview data must expose challengeUnlockSec");
      } else {
        pass("challenge_unlock_static", `challenge unlock at ${Number(preview.challengeUnlockSec).toFixed(2)}s`);
      }
    } catch (error) {
      fail("ir_html_equivalence", `#irPreviewData parse failed: ${error.message}`);
    }
  }

  const internalTokens = [/source_ref/i, /schema_version/i, /candidate/i, /official_score_allowed/i, /\bE\d{2}\b/, /\bP\d{2,}\b/];
  const hit = internalTokens.find((re) => re.test(html));
  if (hit) fail("student_safe_tokens", `student preview contains possible internal token ${hit}`);
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

    const maxNodes = Number(ir.render_contract?.max_visible_nodes ?? 4);
    const viewports = [
      { name: "portrait_360", width: 360, height: 740, mobile: true },
      { name: "portrait_390", width: 390, height: 844, mobile: true },
      { name: "portrait_430", width: 430, height: 932, mobile: true },
      { name: "landscape_844", width: 844, height: 390, mobile: true },
      { name: "landscape_932", width: 932, height: 430, mobile: true },
    ];
    const samples = [
      ir.scenes[0],
      ir.scenes[Math.min(1, ir.scenes.length - 1)],
      ir.scenes.find((scene) => scene.id === "score"),
      ir.scenes.find((scene) => scene.id === "qa_closure"),
      ir.scenes.find((scene) => scene.id === "closing_challenge"),
    ].filter(Boolean);
    const scoreScene = ir.scenes.find((scene) => scene.id === "score") || ir.scenes.at(-2) || ir.scenes.at(-1);
    const challengeUnlockSec = Number(ir.render_contract?.challenge_unlock_sec ?? scoreScene.start_sec);

    const loadViewport = async (viewport) => {
      await client.send("Emulation.setDeviceMetricsOverride", {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: 2,
        mobile: viewport.mobile,
      });
      await client.send("Page.navigate", { url: `file://${htmlPath}` });
      for (let i = 0; i < 80; i += 1) {
        const ready = await client.send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
        if (ready.result?.result?.value === "complete") break;
        await sleep(100);
      }
      await sleep(120);
    };

    const evalValue = async (expression) => {
      const response = await client.send("Runtime.evaluate", { expression, returnByValue: true });
      return response.result.result.value;
    };

    for (const viewport of viewports) {
      await loadViewport(viewport);
      const layoutValue = await evalValue(`
        (() => {
          const rect = (el) => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
          };
          const visible = (el) => {
            if (!el) return false;
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return cs.display !== "none" && cs.visibility !== "hidden" && Number(cs.opacity || 1) > 0.05 && r.width > 1 && r.height > 1;
          };
          const stage = document.querySelector(".stage");
          const player = document.querySelector(".player");
          const buttons = [...document.querySelectorAll("button,a,input[type=range]")].filter(visible);
          const smallTargets = buttons
            .map((el) => ({name: (el.textContent || el.getAttribute("aria-label") || el.className || el.tagName).trim().slice(0, 28), rect: rect(el)}))
            .filter((item) => item.rect.width < 44 || item.rect.height < 44);
          const missingNames = buttons
            .filter((el) => !(el.getAttribute("aria-label") || el.textContent || "").trim())
            .map((el) => el.tagName.toLowerCase());
          return {
            overflowX: document.documentElement.scrollWidth - innerWidth,
            stage: rect(stage),
            player: rect(player),
            smallTargets,
            missingNames,
            captionLive: document.querySelector("[data-caption]")?.getAttribute("aria-live") || "",
            playPressed: document.querySelector("#play")?.hasAttribute("aria-pressed") || false,
            theaterPressed: document.querySelector("[data-theater-toggle]")?.hasAttribute("aria-pressed") || false,
          };
        })()
      `);
      if (layoutValue.overflowX > 2) fail("runtime_horizontal_overflow", `${viewport.name}: overflowX ${Math.round(layoutValue.overflowX)}px`);
      else pass("runtime_horizontal_overflow", `${viewport.name}: no horizontal overflow`);
      if (!layoutValue.stage || layoutValue.stage.width < Math.min(320, viewport.width * 0.72)) {
        fail("runtime_stage_width", `${viewport.name}: stage too narrow`);
      } else {
        pass("runtime_stage_width", `${viewport.name}: stage width ${Math.round(layoutValue.stage.width)}px`);
      }
      if (viewport.width > viewport.height && layoutValue.player?.top < 0) {
        fail("runtime_player_layout", `${viewport.name}: player starts above viewport`);
      } else {
        pass("runtime_player_layout", `${viewport.name}: player is in viewport flow`);
      }
      if (layoutValue.smallTargets.length) {
        fail("runtime_touch_targets", `${viewport.name}: small targets ${layoutValue.smallTargets.map((item) => `${item.name}:${Math.round(item.rect.width)}x${Math.round(item.rect.height)}`).join(", ")}`);
      } else {
        pass("runtime_touch_targets", `${viewport.name}: visible controls meet 44px touch target`);
      }
      if (layoutValue.missingNames.length) fail("runtime_accessible_names", `${viewport.name}: controls missing names ${layoutValue.missingNames.join(",")}`);
      else pass("runtime_accessible_names", `${viewport.name}: visible controls have names`);
      layoutValue.captionLive === "polite" ? pass("runtime_caption_live", `${viewport.name}: caption is live`) : fail("runtime_caption_live", `${viewport.name}: caption missing aria-live`);
      layoutValue.playPressed && layoutValue.theaterPressed ? pass("runtime_pressed_state", `${viewport.name}: player buttons expose pressed state`) : fail("runtime_pressed_state", `${viewport.name}: missing aria-pressed`);

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
          const rect = (el) => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
          };
          const intersects = (a,b) => !!a && !!b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;
          const activeScenes = [...document.querySelectorAll(".scene.active")];
          const active = activeScenes[0];
          const player = document.querySelector(".player");
          const playerRect = rect(player);
          const protectedEls = [
            ...document.querySelectorAll(".scene.active .visual, .caption-line, .scene.active .coach-card, .challenge-inline")
          ].filter(visible);
          const playerBlocks = protectedEls
            .map((el) => ({name: el.className || el.tagName, rect: rect(el)}))
            .filter((item) => intersects(playerRect, item.rect))
            .map((item) => item.name);
          const captionCoachOverlap = intersects(rect(document.querySelector(".caption-line")), rect(document.querySelector(".scene.active .coach-card")));
          const offSceneVisible = [...document.querySelectorAll(".scene:not(.active) [data-visible-node]")].filter(visible).length;
        return {
          state: window.__IR_PLAYER__.state(),
          activeScenes: activeScenes.length,
          visibleNodes: active ? [...active.querySelectorAll("[data-visible-node]")].filter(visible).map((el) => el.dataset.visibleNode) : [],
          keycards: active ? [...active.querySelectorAll(".coach-card")].filter(visible).length : 0,
          caption: document.querySelector("[data-caption]")?.textContent?.trim() || "",
          challengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter(visible).length,
          enabledChallengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter((el) => visible(el) && el.getAttribute("aria-disabled") !== "true").length,
          playerBlocks,
          captionCoachOverlap,
          offSceneVisible
        };
        })()
      `;
        const value = await evalValue(expression);
        const label = `${viewport.name}/${scene.id}`;
        if (value.activeScenes !== 1) fail("runtime_one_active_scene", `${label}: ${value.activeScenes} active scenes`);
        else pass("runtime_one_active_scene", `${label}: one active scene`);
        if (value.visibleNodes.length > maxNodes) fail("runtime_visible_budget", `${label}: ${value.visibleNodes.length} visible nodes > ${maxNodes}`);
        else pass("runtime_visible_budget", `${label}: ${value.visibleNodes.length}/${maxNodes}`);
        if (value.visibleNodes.length < 1) fail("runtime_visible_progress", `${label}: no visible node after scene midpoint`);
        else pass("runtime_visible_progress", `${label}: progressive reveal produced visible nodes`);
        if (value.keycards !== 1) fail("runtime_keycard_budget", `${label}: ${value.keycards} visible keycards`);
        else pass("runtime_keycard_budget", `${label}: one keycard`);
        if (!value.caption) fail("runtime_caption", `${label}: caption is empty`);
        else pass("runtime_caption", `${label}: caption visible`);
        if (value.playerBlocks.length) fail("runtime_player_occlusion", `${label}: player overlaps ${value.playerBlocks.join(", ")}`);
        else pass("runtime_player_occlusion", `${label}: player does not cover protected content`);
        if (value.captionCoachOverlap) fail("runtime_caption_coach_overlap", `${label}: caption overlaps coach card`);
        else pass("runtime_caption_coach_overlap", `${label}: caption avoids coach card`);
        if (value.offSceneVisible) fail("runtime_non_cumulative_seek", `${label}: ${value.offSceneVisible} off-scene visible nodes`);
        else pass("runtime_non_cumulative_seek", `${label}: off-scene nodes are not visible`);
        if (scene.id === "closing_challenge" && value.challengeCtas < 1) {
          fail("runtime_challenge_cta", `${label}: closing scene has no visible challenge CTA`);
        }
      }

      const ctaValue = await evalValue(`
        (() => {
          const visible = (el) => {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return cs.display !== "none" && cs.visibility !== "hidden" && Number(cs.opacity || 1) > 0.05 && r.width > 1 && r.height > 1;
          };
          const enabled = () => [...document.querySelectorAll("[data-challenge-cta]")].filter((el) => visible(el) && el.getAttribute("aria-disabled") !== "true").length;
          window.__IR_PLAYER__.seek(${Math.max(0, challengeUnlockSec - 1).toFixed(3)});
          const before = enabled();
          window.__IR_PLAYER__.seek(${Math.min(Number(ir.scenes.at(-1).end_sec), challengeUnlockSec + 1).toFixed(3)});
          const after = enabled();
          return { before, after };
        })()
      `);
      if (ctaValue.before > 0) fail("runtime_challenge_unlock", `${viewport.name}: CTA enabled before unlock`);
      else pass("runtime_challenge_unlock", `${viewport.name}: CTA locked before score scene`);
      if (ctaValue.after < 1) fail("runtime_challenge_unlock", `${viewport.name}: CTA not enabled after unlock`);
      else pass("runtime_challenge_unlock", `${viewport.name}: CTA enabled after score scene`);
    }

    for (const viewport of viewports.filter((item) => item.name === "portrait_390" || item.name === "landscape_844")) {
      await loadViewport(viewport);
      const theaterExpression = `
      (() => {
        document.querySelector("[data-theater-toggle]")?.click();
        window.__IR_PLAYER__.seek(${JSON.stringify(ir.scenes.at(-1).start_sec + 0.2)});
        const visible = (el) => {
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 1 && r.height > 1;
        };
        const rect = (el) => {
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
        };
        const intersects = (a,b) => !!a && !!b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;
        const player = document.querySelector(".player");
        const stage = document.querySelector(".stage");
        const caption = document.querySelector(".caption-line");
        const coach = document.querySelector(".scene.active .coach-card");
        const playerRect = rect(player);
        return {
          theater: document.querySelector(".lesson")?.classList.contains("theater"),
          controlsVisible: document.querySelector(".lesson")?.classList.contains("controls-visible"),
          challengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter(visible).length,
          stageRect: rect(stage),
          playerRect,
          playerEvents: getComputedStyle(player).pointerEvents,
          playerCaptionOverlap: intersects(playerRect, rect(caption)),
          playerCoachOverlap: intersects(playerRect, rect(coach)),
          viewport: { width: innerWidth, height: innerHeight }
        };
      })()
    `;
      const theater = await evalValue(theaterExpression);
      theater.theater ? pass("runtime_theater", `${viewport.name}: theater class toggled`) : fail("runtime_theater", `${viewport.name}: theater class did not toggle`);
      theater.controlsVisible ? pass("runtime_theater_controls_visible", `${viewport.name}: theater controls show after tap/toggle`) : fail("runtime_theater_controls_visible", `${viewport.name}: theater controls did not show after tap/toggle`);
      theater.challengeCtas >= 1 ? pass("runtime_theater_challenge_cta", `${viewport.name}: theater keeps challenge CTA`) : fail("runtime_theater_challenge_cta", `${viewport.name}: theater hides all challenge CTAs`);
      if (theater.stageRect && theater.stageRect.width < theater.viewport.width - 4) {
        fail("runtime_theater_stage", `${viewport.name}: stage width ${Math.round(theater.stageRect.width)} < viewport`);
      } else {
        pass("runtime_theater_stage", `${viewport.name}: theater stage spans viewport width`);
      }
      if (theater.playerCaptionOverlap || theater.playerCoachOverlap) {
        fail("runtime_theater_occlusion", `${viewport.name}: controls overlap caption or coach card`);
      } else {
        pass("runtime_theater_occlusion", `${viewport.name}: controls avoid caption and coach card`);
      }
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
