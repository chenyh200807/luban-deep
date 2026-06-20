#!/usr/bin/env node
// Build a non-authoritative review packet for the Luban OpenMAIC-style workflow.
// It records machine gate results, screenshot evidence, judge/human findings, and
// root-cause triage so visual feedback loops back into IR/renderer/gate/skill.

import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { basename, dirname, resolve } from "node:path";

const args = process.argv.slice(2);
const usage = `usage:
  node build_workflow_review_packet.mjs --card-id <id> --out <packet.json>
    [--gate name=PASS[:warns]]...
    [--screenshot viewport=path[:issue text]]...
    [--issue axis|anti_pattern|target|severity|fix_layer|fix]...
    [--triage symptom|shape|authority|contract|fix_layer|new_gate_or_antipattern]...

example:
  node build_workflow_review_packet.mjs \\
    --card-id F16_qigu \\
    --gate validate_challenge_theater_practice=PASS:0 \\
    --screenshot 390x844=F16.challenge.practice.390.png \\
    --out F16_qigu.workflow_review_packet.json`;

function takeFlag(name) {
  const index = args.indexOf(name);
  if (index < 0) return null;
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${name} requires a value\n${usage}`);
  }
  args.splice(index, 2);
  return value;
}

function takeRepeat(name) {
  const values = [];
  while (args.includes(name)) {
    values.push(takeFlag(name));
  }
  return values;
}

function sha256(path) {
  if (!existsSync(path)) return null;
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function parseGate(raw) {
  const [name, statusText] = raw.split("=");
  if (!name || !statusText) throw new Error(`invalid --gate ${raw}`);
  const [status, warn = "0"] = statusText.split(":");
  return {
    name,
    status,
    warn: Number(warn) || 0,
  };
}

function parseScreenshot(raw, outDir) {
  const [viewport, rest] = raw.split("=");
  if (!viewport || !rest) throw new Error(`invalid --screenshot ${raw}`);
  const [pathText, ...issueParts] = rest.split(":");
  const path = resolve(pathText);
  const exists = existsSync(path);
  return {
    viewport,
    path: path.startsWith(outDir) ? path.slice(outDir.length + 1) : path,
    exists,
    looked: true,
    issue: issueParts.join(":"),
    bytes: exists ? statSync(path).size : 0,
    sha256: sha256(path),
  };
}

function splitPipe(raw, expected, flag) {
  const parts = raw.split("|");
  if (parts.length !== expected) throw new Error(`invalid ${flag} ${raw}`);
  return parts;
}

function parseIssue(raw) {
  const [axis, antiPattern, target, severity, fixLayer, fix] = splitPipe(raw, 6, "--issue");
  return {
    axis,
    anti_pattern: antiPattern,
    beat_or_question: target,
    severity,
    fix_layer: fixLayer,
    fix,
  };
}

function parseTriage(raw) {
  const [symptom, sharedFailureShape, oneAuthority, brokenContract, fixLayer, newGateOrAntipattern] = splitPipe(raw, 6, "--triage");
  return {
    symptom,
    shared_failure_shape: sharedFailureShape,
    one_authority: oneAuthority,
    broken_contract: brokenContract,
    fix_layer: fixLayer,
    new_gate_or_antipattern: newGateOrAntipattern,
  };
}

function main() {
  const cardId = takeFlag("--card-id");
  const outArg = takeFlag("--out");
  if (!cardId || !outArg || args.includes("--help") || args.includes("-h")) {
    console.error(usage);
    return cardId || outArg ? 0 : 2;
  }
  const outPath = resolve(outArg);
  const outDir = dirname(outPath);
  const gates = takeRepeat("--gate").map(parseGate);
  const screenshots = takeRepeat("--screenshot").map((raw) => parseScreenshot(raw, outDir));
  const issues = takeRepeat("--issue").map(parseIssue);
  const triage = takeRepeat("--triage").map(parseTriage);

  if (args.length) throw new Error(`unknown args: ${args.join(" ")}`);

  const missingScreenshots = screenshots.filter((shot) => !shot.exists).map((shot) => shot.viewport);
  const failedGates = gates.filter((gate) => gate.status !== "PASS").map((gate) => gate.name);
  const missingTriageForIssues = issues.length > 0 && triage.length === 0;
  const verdict = failedGates.length || missingScreenshots.length || missingTriageForIssues || issues.some((issue) => ["CRITICAL", "HIGH"].includes(issue.severity))
    ? "FAIL"
    : "PASS";

  const packet = {
    schema_version: "luban_workflow_review_packet.v0",
    card_id: cardId,
    generated_at: new Date().toISOString(),
    official_score_allowed: false,
    grading_authority: false,
    learner_state_write_allowed: false,
    verdict,
    machine_gates: gates,
    screenshots,
    judge: {
      verdict,
      issues,
    },
    root_cause_triage: triage,
    revision_scope: {
      allowed: ["animation_ir.v0表现字段", "renderer primitive", "gate", "skill anti-pattern", "learning-stage shell"],
      forbidden: ["改母题事实", "改采分点", "改答案", "只调单卡 CSS 后宣布治本"],
    },
    blocking_failures: [
      ...failedGates.map((name) => `gate:${name}`),
      ...missingScreenshots.map((viewport) => `screenshot:${viewport}`),
      ...(missingTriageForIssues ? ["review:issue_without_root_cause_triage"] : []),
    ],
  };

  writeFileSync(outPath, JSON.stringify(packet, null, 2) + "\n", "utf8");
  console.log(`${basename(outPath)}: ${verdict}${packet.blocking_failures.length ? ` ${packet.blocking_failures.join(",")}` : ""}`);
  return packet.blocking_failures.length ? 1 : 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
