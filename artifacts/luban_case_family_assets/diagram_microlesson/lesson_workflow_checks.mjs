import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";

const PACK_ROOT_SUFFIX = "docs/原始数据/考点原料/成品";

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function findRepoRoot(startPath) {
  let current = resolve(startPath);
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(current, PACK_ROOT_SUFFIX))) return current;
    const next = dirname(current);
    if (next === current) break;
    current = next;
  }
  return resolve(startPath, "../../..");
}

function resolveLessonPath(lessonPath) {
  return resolve(lessonPath);
}

function resolveCardPath(lessonDoc, lessonPath) {
  if (!lessonDoc.derived_from) return null;
  const lessonDir = dirname(resolveLessonPath(lessonPath));
  return resolve(lessonDir, lessonDoc.derived_from);
}

function resolvePackPath(card, lessonPath) {
  const refs = card.source_refs;
  let packRef = "";
  if (refs && !Array.isArray(refs) && typeof refs === "object") {
    packRef = refs.pack_markdown || refs.pack_md || refs.pack_path || "";
  }
  if (!packRef && Array.isArray(refs)) {
    const hit = refs.find((ref) => String(ref.source_path || "").includes(PACK_ROOT_SUFFIX));
    packRef = hit?.source_path || "";
  }
  if (!packRef) return { packRef: "", packPath: "" };
  if (isAbsolute(packRef)) return { packRef, packPath: resolve(packRef) };
  const repoRoot = findRepoRoot(dirname(resolveLessonPath(lessonPath)));
  return { packRef, packPath: resolve(repoRoot, packRef) };
}

function resolveAnchor(card, path) {
  let cur = card;
  for (const raw of String(path || "").split(".")) {
    if (!raw) return undefined;
    const match = raw.match(/^([^[]+)(?:\[([^\]]+)\])?$/);
    if (!match) return undefined;
    const [, key, idx] = match;
    cur = cur?.[key];
    if (idx !== undefined) {
      if (cur === undefined) return undefined;
      if (/^\d+$/.test(idx)) cur = cur[Number(idx)];
      else cur = Array.isArray(cur) ? cur.find((item) => item && item.id === idx) : undefined;
    }
    if (cur === undefined || cur === null) return undefined;
  }
  return cur;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value && Array.isArray(value.steps)) return value.steps;
  if (value && Array.isArray(value.beats)) return value.beats;
  return [];
}

function textLen(value) {
  return String(value || "").trim().length;
}

function hasBridgeConnector(value) {
  return /(所以|接着|因为|有了|这时|最后|先|再|才|不是|而是|但|因此|然后)/.test(String(value || ""));
}

export function validateLessonWorkflow({ lessonDoc, lessonPath, cardDoc = null, strict = false }) {
  const problems = [];
  const warnings = [];
  const contract = lessonDoc.workflow_contract || {};
  const active = strict || contract.strict_source || contract.requires_bridge || contract.name === "luban_openmaic_animation_ir_workflow";
  if (!active) return { active: false, problems, warnings, cardPath: null, packPath: null };

  const cardPath = resolveCardPath(lessonDoc, lessonPath);
  if (!cardPath || !existsSync(cardPath)) {
    problems.push(`derived_from source card missing: ${lessonDoc.derived_from || "(empty)"}`);
    return { active: true, problems, warnings, cardPath, packPath: null };
  }
  const card = cardDoc || readJson(cardPath);
  const { packRef, packPath } = resolvePackPath(card, lessonPath);
  if (!packRef) {
    problems.push("source card must declare source_refs.pack_markdown under docs/原始数据/考点原料/成品");
  } else if (!packPath.includes(PACK_ROOT_SUFFIX)) {
    problems.push(`source_refs.pack_markdown must point to ${PACK_ROOT_SUFFIX}, got ${packRef}`);
  } else if (!existsSync(packPath)) {
    problems.push(`source_refs.pack_markdown file does not exist: ${packRef}`);
  }

  if (!card.main_exam_action || !card.wrong_idea) {
    problems.push("source card must contain main_exam_action and wrong_idea before authoring lesson");
  }

  const spine = asArray(card.teaching_spine || card.logic_chain);
  if (spine.length < 5) {
    problems.push(`source card teaching_spine must have at least 5 steps, got ${spine.length}`);
  }
  const spineStates = new Set();
  spine.forEach((step, i) => {
    const prefix = `teaching_spine[${i}]`;
    if (!step.state) problems.push(`${prefix} missing state`);
    else spineStates.add(step.state);
    if (!step.visual_fact && !step.visual_action) problems.push(`${prefix} missing visual_fact/visual_action`);
    if (!step.answer_move) problems.push(`${prefix} missing answer_move`);
    if (!step.anchor_md && !step.anchor && !step.source_anchor) problems.push(`${prefix} missing anchor_md/source_anchor`);
    if (i > 0 && !step.bridge_from_previous) problems.push(`${prefix} missing bridge_from_previous`);
  });

  const opening = lessonDoc.opening || {};
  ["exam_scene", "why_learn", "promise"].forEach((field) => {
    if (!opening[field]) problems.push(`lesson.opening.${field} is required for clarity-first workflow`);
  });

  const beats = lessonDoc.teach?.beats || lessonDoc.teach?.scenes || [];
  if (beats.length < 5) problems.push(`lesson teach beats should be 5-8 clear beats, got ${beats.length}`);
  if (beats.length > 10) warnings.push(`lesson has ${beats.length} teach beats; ok only if each beat has a distinct visual action`);

  let shortBeatCount = 0;
  beats.forEach((beat, i) => {
    const prefix = `teach.beats[${i}]`;
    const state = beat.state || beat.stage;
    if (state && spineStates.size && !spineStates.has(state)) {
      problems.push(`${prefix} state=${state} has no matching source_card.teaching_spine step`);
    }
    if (i > 0 && !beat.bridge) problems.push(`${prefix} missing bridge`);
    if (i > 0 && beat.bridge && !hasBridgeConnector(beat.bridge)) warnings.push(`${prefix} bridge may be too abrupt: ${beat.bridge}`);
    if (!beat.exam_task) problems.push(`${prefix} missing exam_task`);
    if (!beat.visual_explanation) problems.push(`${prefix} missing visual_explanation`);
    if (!beat.answer_move) problems.push(`${prefix} missing answer_move`);
    if (beat.claim && !beat.anchor) problems.push(`${prefix} claim=true but anchor missing`);
    if (beat.claim && beat.anchor && resolveAnchor(card, beat.anchor) === undefined) {
      problems.push(`${prefix} anchor not found in source card: ${beat.anchor}`);
    }
    if (textLen(beat.narration) < 32) shortBeatCount += 1;
  });
  if (shortBeatCount > 1) {
    warnings.push(`${shortBeatCount} teach beats are very short; do not compress clarity just to shorten total runtime`);
  }

  const maxSec = Number(contract.target_total_sec_max ?? 300);
  if (!Number.isFinite(maxSec) || maxSec > 300) {
    problems.push("workflow_contract.target_total_sec_max must be <= 300 seconds");
  }

  return { active: true, problems, warnings, cardPath, packPath };
}

export function formatWorkflowResults(result) {
  const lines = [];
  if (!result.active) {
    lines.push("lesson workflow contract inactive: skipped");
    return lines.join("\n");
  }
  if (result.cardPath) lines.push(`source card: ${result.cardPath}`);
  if (result.packPath) lines.push(`pack md: ${result.packPath}`);
  if (result.warnings.length) {
    lines.push("warnings:");
    result.warnings.forEach((warning) => lines.push(`  - ${warning}`));
  }
  if (result.problems.length) {
    lines.push("problems:");
    result.problems.forEach((problem) => lines.push(`  - ${problem}`));
  } else {
    lines.push("lesson workflow contract ok");
  }
  return lines.join("\n");
}
