#!/usr/bin/env node
// Validate that lesson animation_action data-id targets resolve in rendered HTML.
// This is a deterministic presentation gate only. It does not judge exam facts.

import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, resolve, join } from "node:path";

const args = process.argv.slice(2);
if (args.length < 1 || args.includes("--help") || args.includes("-h")) {
  console.error("usage: node validate_data_id_targets.mjs <lesson.json|master.json> [rendered.html]");
  process.exit(args.length < 1 ? 2 : 0);
}

const inputPath = resolve(args[0]);
let renderedPath = args[1] ? resolve(args[1]) : "";

function fail(message) {
  console.error(`FAIL ${message}`);
}

function readJson(path) {
  if (!existsSync(path)) throw new Error(`missing JSON: ${path}`);
  return JSON.parse(readFileSync(path, "utf8"));
}

function lessonFromInput(path) {
  const data = readJson(path);
  if (data.teach?.beats) {
    if (!renderedPath) renderedPath = path.replace(/\.lesson\.json$/, ".lesson.view.html");
    return { lesson: data, sourcePath: path };
  }
  if (data.teaching_lesson_ref) {
    const lessonPath = resolve(dirname(path), data.teaching_lesson_ref);
    if (!renderedPath) {
      renderedPath = path.replace(/\.master\.json$/, ".journey.html");
    }
    return { lesson: readJson(lessonPath), sourcePath: lessonPath };
  }
  throw new Error("input is neither a lesson JSON nor a master JSON with teaching_lesson_ref");
}

function collectActionTargets(lesson) {
  const targets = [];
  for (const beat of lesson.teach?.beats || []) {
    for (const [idx, action] of (beat.animation_action || []).entries()) {
      const target = action?.target;
      targets.push({
        beat: beat.id,
        action: action?.type,
        index: idx,
        target,
        targetId: typeof target === "string" && target.startsWith("data-id:")
          ? target.slice("data-id:".length)
          : "",
      });
    }
  }
  return targets;
}

function collectDomIds(html) {
  const ids = new Set();
  const attrRe = /\sdata-(?:visual-node|action|beat|practice)-id=["']([^"']+)["']/gi;
  let match;
  while ((match = attrRe.exec(html))) {
    const raw = match[1].trim();
    if (!raw) continue;
    for (const part of raw.split(/\s+/)) {
      if (part) ids.add(part);
    }
  }
  return ids;
}

let errors = [];
try {
  const { lesson, sourcePath } = lessonFromInput(inputPath);
  if (!existsSync(renderedPath)) {
    errors.push(`rendered HTML missing: ${renderedPath}`);
  }
  const html = existsSync(renderedPath) ? readFileSync(renderedPath, "utf8") : "";
  const targets = collectActionTargets(lesson);
  if (!targets.length) {
    errors.push(`${basename(sourcePath)} has no animation_action[] targets`);
  }
  const domIds = collectDomIds(html);
  for (const hook of ["data-card-id", "data-stage-shell", "data-beat-id", "data-action-id", "data-visual-node-id", "data-practice-id"]) {
    if (!html.includes(hook)) errors.push(`${basename(renderedPath)} missing [${hook}] hook`);
  }
  if (!html.includes("window.__LUBAN_LESSON_MANIFEST__")) {
    errors.push(`${basename(renderedPath)} missing window.__LUBAN_LESSON_MANIFEST__`);
  }
  for (const target of targets) {
    if (typeof target.target !== "string" || !target.target.startsWith("data-id:") || !target.targetId.trim()) {
      errors.push(`teach:${target.beat} action[${target.index}] has invalid target ${JSON.stringify(target.target)}`);
    } else if (!domIds.has(target.targetId)) {
      errors.push(`teach:${target.beat} ${target.action} target not found in DOM: ${target.target}`);
    }
  }
} catch (err) {
  errors.push(err.message);
}

if (errors.length) {
  for (const error of errors) fail(error);
  console.error(`data-id target gate: FAIL (${errors.length} fail)`);
  process.exit(1);
}

console.log(`PASS ${basename(args[0])} -> ${basename(renderedPath)} data-id targets resolved`);
console.log("data-id target gate: PASS");
