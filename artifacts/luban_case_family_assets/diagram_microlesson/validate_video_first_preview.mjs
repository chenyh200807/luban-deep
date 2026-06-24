#!/usr/bin/env node
// Static preview gate for video-first learning cards.
// This checks presentation/contract invariants only. It does not rejudge exam facts.

import { readFileSync, existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

const args = process.argv.slice(2);
if (args.length < 1 || args.includes("--help") || args.includes("-h")) {
  console.error("usage: node validate_video_first_preview.mjs <rendered.html> [practice.html]");
  process.exit(args.length < 1 ? 2 : 0);
}

const renderedPath = resolve(args[0]);
const practicePath = args[1] ? resolve(args[1]) : null;

const results = [];
const add = (level, file, check, message) => {
  results.push({ level, file: basename(file), check, message });
};
const fail = (...xs) => add("FAIL", ...xs);
const warn = (...xs) => add("WARN", ...xs);
const pass = (...xs) => add("PASS", ...xs);

function read(file) {
  if (!existsSync(file)) {
    fail(file, "file_exists", `missing file: ${file}`);
    return "";
  }
  return readFileSync(file, "utf8");
}

const rendered = read(renderedPath);
let practice = practicePath ? read(practicePath) : "";

function checkNoInternalTokens(file, html) {
  const internal = [
    /source_ref/i,
    /schema_version/i,
    /candidate/i,
    /candidate_teaching_prototype/i,
    /official_score_allowed/i,
    /judging_artifact_id/i,
    /error_code/i,
    /\bE\d{2}\b/,
    /\bP\d{2,}\b/,
    /\bSP[_-][A-Za-z0-9_-]+/i,
  ];
  const hit = internal.find((re) => re.test(html));
  if (hit) fail(file, "student_safe_tokens", `student artifact contains internal token matching ${hit}`);
  else pass(file, "student_safe_tokens", "no obvious internal authority tokens");
}

function jsonScript(html, id) {
  const re = new RegExp(`<script[^>]+id=["']${id}["'][^>]*>([\\s\\S]*?)<\\/script>`, "i");
  const m = html.match(re);
  if (!m) return null;
  try {
    return JSON.parse(m[1]);
  } catch (err) {
    fail(renderedPath, `${id}_json`, `could not parse #${id}: ${err.message}`);
    return null;
  }
}

function checkLessonContract(file, html) {
  const data = jsonScript(html, "lessonData");
  const irPreview = jsonScript(html, "irPreviewData");
  const hasInlineChapters = /const\s+chapters\s*=\s*\[/.test(html);

  if (irPreview) {
    const scenes = Array.isArray(irPreview.scenes) ? irPreview.scenes : [];
    const chapters = Array.isArray(irPreview.chapters) ? irPreview.chapters : [];
    scenes.length >= 6 ? pass(file, "ir_preview_scenes", `${scenes.length} IR preview scenes`) : fail(file, "ir_preview_scenes", "expected at least 6 IR preview scenes");
    chapters.length >= 4 ? pass(file, "ir_preview_chapters", `${chapters.length} semantic chapters`) : fail(file, "ir_preview_chapters", "expected semantic chapters in IR preview data");
    return;
  }

  if (!data) {
    if (hasInlineChapters) warn(file, "lesson_contract", "no lessonData JSON; falling back to inline chapters shell check");
    else warn(file, "lesson_contract", "no lessonData JSON or inline chapters found");
    return;
  }

  const beats = Array.isArray(data.video_beats) ? data.video_beats : [];
  const stages = new Set(beats.map((b) => b.stage || b.id).filter(Boolean));
  beats.length >= 5 ? pass(file, "video_beats", `${beats.length} video beats`) : fail(file, "video_beats", "expected at least 5 video beats");
  stages.has("hook") ? pass(file, "hook_stage", "has opening hook stage") : fail(file, "hook_stage", "missing hook stage");
  stages.has("trap") ? pass(file, "trap_stage", "has trap/wrong-idea stage") : fail(file, "trap_stage", "missing trap/wrong-idea stage");
  stages.has("score") ? pass(file, "score_stage", "has answer-paper/score stage") : fail(file, "score_stage", "missing answer-paper/score stage");

  const segments = Array.isArray(data.timing?.segments) ? data.timing.segments : [];
  if (!segments.length) {
    warn(file, "timing_segments", "could not confirm timing segments");
    return;
  }
  pass(file, "timing_segments", `${segments.length} timing segments`);
  const missingAnchor = segments.filter((s) => s.claim === true && !s.anchor);
  missingAnchor.length
    ? fail(file, "claim_anchors", `${missingAnchor.length} claim segments are missing anchor`)
    : pass(file, "claim_anchors", "all claim segments have anchors");
  const hasClosing = segments.some((s) => s.kind === "closing" || s.state === "closing" || /收个尾|闯关/.test(String(s.text || "")));
  hasClosing ? pass(file, "closing_segment", "has natural closing segment") : fail(file, "closing_segment", "missing closing segment");
}

function checkRendered(file, html) {
  if (!html) return;
  const isJourneyShell = /data-stage-shell=["'][^"']*archetype-journey|data-animation-ir-preview=["']v0["']|window\.__LUBAN_LESSON_MANIFEST__/.test(html);
  if (isJourneyShell) {
    pass(file, "stage_shell_mode", "decision-first/IR learning shell");
  } else {
    /<video\b/i.test(html) ? pass(file, "video", "has video element") : fail(file, "video", "missing video element");
    /playsinline/i.test(html) ? pass(file, "playsinline", "mobile inline playback enabled") : fail(file, "playsinline", "missing playsinline");
    /poster\s*=/i.test(html) ? pass(file, "poster", "has poster") : fail(file, "poster", "missing poster");
  }
  /center-play|播放视频/.test(html) ? pass(file, "center_play", "has central play affordance") : fail(file, "center_play", "missing central play affordance");
  /orientation-adaptive|responsive-stage|responsive learning stage/i.test(html)
    ? pass(file, "responsive_stage", "declares orientation-adaptive learning stage")
    : fail(file, "responsive_stage", "normal stage must declare orientation-adaptive/responsive learning stage");
  /@media[^{]+orientation\s*:\s*landscape|@media[^{]+min-width\s*:\s*760px/i.test(html)
    ? pass(file, "orientation_rules", "has landscape or wide-screen layout rules")
    : fail(file, "orientation_rules", "missing landscape/wide responsive layout rules");
  /\.theater|:fullscreen/i.test(html) ? pass(file, "theater", "has theater/fullscreen mode") : fail(file, "theater", "missing theater/fullscreen mode");
  /data-theater-toggle|id=["']theaterToggle["']/i.test(html) ? pass(file, "theater_toggle", "has real theater/fullscreen toggle") : fail(file, "theater_toggle", "missing real theater/fullscreen toggle");
  /controls-visible|class=["'][^"']*\bcontrols\b|\.controls\b/i.test(html) ? pass(file, "overlay_controls", "has overlay control state") : fail(file, "overlay_controls", "missing overlay control state");
  /type=["']range["']/i.test(html) ? pass(file, "scrubber", "has draggable range scrubber") : fail(file, "scrubber", "missing range scrubber");
  /\.practice\.html/i.test(html) ? pass(file, "practice_link", "links independent practice page") : fail(file, "practice_link", "missing independent practice link");
  /开始闯关/.test(html) ? pass(file, "ended_cta", "has post-play challenge CTA") : fail(file, "ended_cta", "missing post-play challenge CTA");

  const labels = [...html.matchAll(/(?:label\s*:\s*["']|class=["'][^"']*(?:beat-dot|chapter)[^"']*["'][^>]*>)([^"'<>{}]{1,8})/g)]
    .map((m) => m[1].trim())
    .filter(Boolean);
  if (labels.length >= 3) {
    const numeric = labels.filter((x) => /^\d+$/.test(x)).length;
    numeric === labels.length
      ? fail(file, "semantic_chapters", "chapter controls are numeric only")
      : pass(file, "semantic_chapters", `semantic chapter labels: ${labels.slice(0, 8).join("/")}`);
  } else {
    warn(file, "semantic_chapters", "could not statically confirm semantic chapter labels");
  }
  checkLessonContract(file, html);
}

function checkPractice(file, html) {
  if (!file || !html) {
    warn(renderedPath, "practice", "practice file not provided");
    return;
  }
  const qCount = (html.match(/<section\b[^>]*class=["'][^"']*\bq\b/gi) || []).length;
  qCount >= 3 ? pass(file, "question_count", `${qCount} question sections`) : fail(file, "question_count", `expected at least 3 question sections, found ${qCount}`);
  const svgCount = (html.match(/<svg\b/gi) || []).length;
  svgCount >= qCount ? pass(file, "question_visuals", `${svgCount} SVG visuals for ${qCount} questions`) : fail(file, "question_visuals", `each question needs a visual; found ${svgCount} SVG for ${qCount} questions`);
  /input|textarea|采分句|score-write|write/.test(html) ? pass(file, "score_sentence", "has score sentence/output task") : fail(file, "score_sentence", "missing score sentence/output task");
  /先作答|先独立作答|未答|if\(!answered|qIsDone/.test(html) ? pass(file, "answer_gate", "blocks next before answer") : warn(file, "answer_gate", "could not statically confirm answer-before-next gate");
}

checkRendered(renderedPath, rendered);
checkNoInternalTokens(renderedPath, rendered);

let inferredPractice = practicePath;
if (!inferredPractice && rendered) {
  const m = rendered.match(/href=["']([^"']+\.practice\.html)["']/i) || rendered.match(/"practice"\s*:\s*"([^"]+\.practice\.html)"/i);
  if (m) inferredPractice = join(dirname(renderedPath), m[1]);
}
if (!practice && inferredPractice) practice = read(inferredPractice);
if (inferredPractice) {
  checkPractice(inferredPractice, practice);
  checkNoInternalTokens(inferredPractice, practice);
} else {
  warn(renderedPath, "practice", "no practice file inferred or provided");
}

for (const r of results) {
  console.log(`${r.level} ${r.file} ${r.check}: ${r.message}`);
}

const failCount = results.filter((r) => r.level === "FAIL").length;
const warnCount = results.filter((r) => r.level === "WARN").length;
if (failCount) {
  console.error(`video-first preview gate: FAIL (${failCount} fail, ${warnCount} warn)`);
  process.exit(1);
}
console.log(`video-first preview gate: PASS (${warnCount} warn)`);
