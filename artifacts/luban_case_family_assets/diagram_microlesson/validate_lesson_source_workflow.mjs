#!/usr/bin/env node
// Gate the clarity-first source -> source_card -> lesson contract before TTS/IR work.
// This is intentionally separate from renderer gates: it catches jumpy narration
// and unanchored teaching spines before visual polishing can hide them.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { formatWorkflowResults, validateLessonWorkflow } from "./lesson_workflow_checks.mjs";

const [, , lessonArg] = process.argv;
if (!lessonArg || process.argv.includes("--help") || process.argv.includes("-h")) {
  console.error("usage: node validate_lesson_source_workflow.mjs <card.lesson.json> [--strict]");
  process.exit(lessonArg ? 0 : 2);
}

const lessonPath = resolve(lessonArg);
const lessonDoc = JSON.parse(readFileSync(lessonPath, "utf8"));
const result = validateLessonWorkflow({
  lessonDoc,
  lessonPath,
  strict: process.argv.includes("--strict"),
});

console.log(formatWorkflowResults(result));
if (result.problems.length) process.exit(1);
