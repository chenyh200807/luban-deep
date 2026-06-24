#!/usr/bin/env node
// Build a non-authoritative review packet for the Luban OpenMAIC-style workflow.
// It records machine gate results, screenshot evidence, judge/human findings, and
// root-cause triage so visual feedback loops back into IR/renderer/gate/skill.

import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { basename, dirname, resolve } from "node:path";

const args = process.argv.slice(2);
const ANIMATED_PRIMITIVE_KINDS = new Set([
  "roof_section",
  "scaffold_frame",
  "process_flow",
  "layer_stack",
  "pit_threshold_board",
  "network_graph",
  "formula_chain",
  "power_distribution_tree",
  "inspection_blueprint_board",
  "lifting_threshold_board",
  "decision_tree",
  "contrast_pair",
  "answer_scan",
]);
const VISUAL_EXCELLENCE_REQUIRED_STATUSES = new Set(["workflow_candidate", "student_ready"]);
const TEXT_CONTAINER_KINDS = new Set([
  "pill",
  "answer_box",
  "dialogue_box",
  "closing_text",
  "challenge_button",
  "note",
  "flow_arrow",
  "threshold_meter",
]);
const DEFAULT_VISUAL_CANVAS = { width: 420, height: 640 };
const DEFAULT_MIN_VISUAL_DOMINANCE_RATIO = 0.46;
const BLUEPRINT_POSTER_MIN_VISUAL_DOMINANCE_RATIO = 0.62;
const REQUIRED_VISUAL_EXCELLENCE_FIELDS = [
  "reference_style",
  "must_show",
  "motion_standards",
  "layout_guards",
  "release_bar",
];
const REQUIRED_SCENE_VISUAL_BRIEF_FIELDS = [
  "source_sentence",
  "visual_action",
  "state_change",
  "exit_before_next",
  "why_not_reused_template",
];
const REQUIRED_PROMOTION_GATE_NAMES = [
  "validate_animation_ir_contract",
  "validate_action_authority",
  "validate_animation_ir_preview",
];
const usage = `usage:
  node build_workflow_review_packet.mjs --card-id <id> --out <packet.json>
    [--ir path/to/animation_ir.v0.json]
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

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function countBy(items, keyFn) {
  return items.reduce((counts, item) => {
    const key = keyFn(item) || "(missing)";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function primitiveSteps(node) {
  return Array.isArray(node?.primitive_steps) ? node.primitive_steps : [];
}

function hasVisualExcellenceField(profile, field) {
  const value = profile?.[field];
  return Array.isArray(value) ? value.length > 0 : typeof value === "string" && value.trim().length > 0;
}

function actionPattern(actions) {
  return actions
    .map((action) => {
      const targetClass = action.kind === "primitive_step" ? "primitive" : action.target ? "target" : "none";
      return `${action.kind}:${action.verb || ""}:${targetClass}:${Number(action.start ?? 0).toFixed(2)}-${Number(action.end ?? 0).toFixed(2)}`;
    })
    .join("|");
}

function visualSignature(node) {
  return String(node?.visual_signature || `${node?.kind || "node"}:${node?.mode || "default"}`);
}

function positiveNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function hasNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function hasNonEmptyArray(value) {
  return Array.isArray(value) && value.length > 0;
}

function hasPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function hasBriefValue(value) {
  return hasNonEmptyString(value) || hasNonEmptyArray(value) || hasPlainObject(value);
}

function visualCanvasArea(contract) {
  const width = positiveNumber(contract.visual_canvas_width) || DEFAULT_VISUAL_CANVAS.width;
  const height = positiveNumber(contract.visual_canvas_height) || DEFAULT_VISUAL_CANVAS.height;
  return width * height;
}

function visualDominanceThreshold(contract) {
  return (
    positiveNumber(contract.min_visual_dominance_ratio) ||
    (contract.layout_mode === "blueprint_poster" ? BLUEPRINT_POSTER_MIN_VISUAL_DOMINANCE_RATIO : DEFAULT_MIN_VISUAL_DOMINANCE_RATIO)
  );
}

function visualNodeArea(node) {
  const width = positiveNumber(node?.w);
  const height = positiveNumber(node?.h);
  return width && height ? width * height : 0;
}

function visualNodeDominanceRatio(node, contract) {
  const canvasArea = visualCanvasArea(contract);
  return canvasArea ? visualNodeArea(node) / canvasArea : 0;
}

function hasDomainObjects(node) {
  if (!node || typeof node !== "object") return false;
  if (node.domain_visual === true) return true;
  if (Array.isArray(node.domain_objects) && node.domain_objects.length) return true;
  if (Array.isArray(node.objects) && node.objects.length) return true;
  return false;
}

function isDominantDiagramNode(node) {
  return node && !TEXT_CONTAINER_KINDS.has(node.kind) && hasDomainObjects(node);
}

function visualDominanceSummary(contract, teachingSceneIds, visualLibrary) {
  const minRatio = visualDominanceThreshold(contract);
  const minScenes = Number(contract.min_dominant_visual_teaching_scenes ?? teachingSceneIds.length);
  const scenes = teachingSceneIds.map((sceneId) => {
    const nodes = Array.isArray(visualLibrary?.[sceneId]?.nodes) ? visualLibrary[sceneId].nodes : [];
    const candidates = nodes
      .filter(isDominantDiagramNode)
      .map((node) => ({
        node_id: node.id || null,
        kind: node.kind || null,
        ratio: Number(visualNodeDominanceRatio(node, contract).toFixed(4)),
      }))
      .sort((left, right) => right.ratio - left.ratio);
    const best = candidates[0] || null;
    return {
      scene_id: sceneId,
      best_node_id: best?.node_id || null,
      best_kind: best?.kind || null,
      best_ratio: best?.ratio || 0,
      pass: Boolean(best && best.ratio >= minRatio),
    };
  });
  return {
    min_ratio: Number(minRatio.toFixed(4)),
    min_scenes: minScenes,
    pass_count: scenes.filter((scene) => scene.pass).length,
    scenes,
  };
}

function analyzeIr(rawPath, outDir) {
  const irPath = resolve(rawPath);
  if (!existsSync(irPath)) {
    return {
      path: irPath,
      exists: false,
      blocking_failures: ["ir:missing_file"],
    };
  }

  let ir;
  try {
    ir = readJson(irPath);
  } catch (error) {
    return {
      path: irPath,
      exists: true,
      blocking_failures: [`ir:json_parse:${error.message}`],
    };
  }

  const contract = ir.render_contract || {};
  const visualDecision = ir.visual_archetype_decision && typeof ir.visual_archetype_decision === "object" ? ir.visual_archetype_decision : {};
  const visualExcellenceProfile = ir.visual_excellence_profile && typeof ir.visual_excellence_profile === "object" ? ir.visual_excellence_profile : {};
  const domainPlan = Array.isArray(visualDecision.domain_visual_plan) ? visualDecision.domain_visual_plan : [];
  const practiceBlueprint = ir.practice_blueprint && typeof ir.practice_blueprint === "object" ? ir.practice_blueprint : null;
  const visualLibrary = ir.visual_library && typeof ir.visual_library === "object" ? ir.visual_library : {};
  const scenes = Array.isArray(ir.scenes) ? ir.scenes : [];
  const actions = scenes.flatMap((scene) => (Array.isArray(scene.actions) ? scene.actions : []));
  const nodes = Object.values(visualLibrary).flatMap((visual) => (Array.isArray(visual.nodes) ? visual.nodes : []));
  const primitiveStepList = nodes.flatMap((node) => primitiveSteps(node).map((step) => ({ node_id: node.id, ...step })));
  const animatedNodes = nodes.filter((node) => ANIMATED_PRIMITIVE_KINDS.has(node.kind));
  const teachingSceneIds = Array.isArray(contract.teaching_scene_ids) && contract.teaching_scene_ids.length
    ? contract.teaching_scene_ids
    : ["hook", "map", "rule", "trap", "score"];
  const primaryRequired = Array.isArray(contract.primary_visual_primitive_required)
    ? contract.primary_visual_primitive_required
    : contract.primary_visual_primitive_required
      ? [contract.primary_visual_primitive_required]
      : [];
  const teachingVisualNodes = teachingSceneIds.flatMap((sceneId) => {
    const sceneNodes = Array.isArray(visualLibrary?.[sceneId]?.nodes) ? visualLibrary[sceneId].nodes : [];
    return sceneNodes.filter((node) => {
      if (!primaryRequired.length) return ANIMATED_PRIMITIVE_KINDS.has(node.kind);
      return primaryRequired.includes(node.kind);
    });
  });
  const teachingVisualSignatures = teachingVisualNodes.map(visualSignature);
  const visualSignatureCounts = countBy(teachingVisualSignatures, (signature) => signature);
  const uniqueTeachingVisualSignatureCount = Object.keys(visualSignatureCounts).length;
  const minTeachingVisualSignatures = Math.min(4, teachingSceneIds.length);
  const sceneIds = new Set(scenes.map((scene) => scene.id).filter(Boolean));
  const remotionReviewSceneIds = Array.isArray(contract.remotion_review_scene_ids)
    ? contract.remotion_review_scene_ids.filter((sceneId) => typeof sceneId === "string" && sceneId.trim())
    : [];
  const minRemotionReviewStills = Number(contract.min_remotion_review_stills ?? 3);
  const teachingPatterns = new Map();
  for (const scene of scenes.filter((item) => teachingSceneIds.includes(item.id))) {
    const pattern = actionPattern(Array.isArray(scene.actions) ? scene.actions : []);
    teachingPatterns.set(pattern, [...(teachingPatterns.get(pattern) || []), scene.id || "(missing)"]);
  }
  const repeatedActionPatterns = [...teachingPatterns.values()].filter((ids) => ids.length > 2);
  const semanticActionCount = actions.filter((action) => ["primitive_step", "annotate", "speech"].includes(action.kind)).length;
  const visualDominance = visualDominanceSummary(contract, teachingSceneIds, visualLibrary);
  const sceneVisualBriefs = Array.isArray(ir.scene_visual_brief) ? ir.scene_visual_brief : [];
  const sceneVisualBriefById = new Map();
  const duplicateSceneVisualBriefIds = [];
  for (const brief of sceneVisualBriefs) {
    if (hasPlainObject(brief) && hasNonEmptyString(brief.scene_id)) {
      if (sceneVisualBriefById.has(brief.scene_id)) {
        duplicateSceneVisualBriefIds.push(brief.scene_id);
      } else {
        sceneVisualBriefById.set(brief.scene_id, brief);
      }
    }
  }
  const sceneVisualBriefSceneIds = [...sceneVisualBriefById.keys()];
  const missingSceneVisualBriefs = [];
  const incompleteSceneVisualBriefs = [];
  for (const sceneId of teachingSceneIds) {
    const brief = sceneVisualBriefById.get(sceneId);
    if (!brief) {
      missingSceneVisualBriefs.push(sceneId);
      continue;
    }
    const missingFields = REQUIRED_SCENE_VISUAL_BRIEF_FIELDS.filter((field) => !hasBriefValue(brief[field]));
    if (!hasNonEmptyArray(brief.domain_objects)) missingFields.push("domain_objects");
    if (missingFields.length) incompleteSceneVisualBriefs.push({ scene_id: sceneId, missing_fields: missingFields });
  }
  const unknownSceneVisualBriefs = sceneVisualBriefSceneIds.filter((sceneId) => !sceneIds.has(sceneId));

  const blockingFailures = [];
  if (!contract.quality_status) blockingFailures.push("ir:missing_quality_status");
  if (contract.student_ready !== true && contract.student_ready !== false) blockingFailures.push("ir:missing_student_ready_flag");
  if (contract.student_ready === true && contract.quality_status !== "student_ready") blockingFailures.push("ir:student_ready_status_mismatch");
  if (!Object.keys(visualDecision).length) blockingFailures.push("ir:missing_visual_archetype_decision");
  if (!visualDecision.pure_text_allowed && !domainPlan.length) blockingFailures.push("ir:missing_domain_visual_plan");
  if (!practiceBlueprint || Object.keys(practiceBlueprint).length === 0) blockingFailures.push("ir:missing_practice_blueprint");
  if (animatedNodes.length && primitiveStepList.length === 0) blockingFailures.push("ir:missing_primitive_steps");
  if (!semanticActionCount && primitiveStepList.length === 0) blockingFailures.push("ir:scaffold_only_actions");
  if (repeatedActionPatterns.length) blockingFailures.push("ir:reused_action_template");
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(contract.quality_status) && uniqueTeachingVisualSignatureCount < minTeachingVisualSignatures) {
    blockingFailures.push("ir:insufficient_teaching_visual_signature_variety");
  }
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(contract.quality_status)) {
    if (remotionReviewSceneIds.length < minRemotionReviewStills) blockingFailures.push("ir:insufficient_remotion_review_scene_ids");
    for (const sceneId of remotionReviewSceneIds) {
      if (!sceneIds.has(sceneId)) blockingFailures.push(`ir:unknown_remotion_review_scene:${sceneId}`);
    }
  }
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(contract.quality_status)) {
    if (!Object.keys(visualExcellenceProfile).length) blockingFailures.push("ir:missing_visual_excellence_profile");
    for (const field of REQUIRED_VISUAL_EXCELLENCE_FIELDS) {
      if (!hasVisualExcellenceField(visualExcellenceProfile, field)) blockingFailures.push(`ir:missing_visual_excellence_${field}`);
    }
    if (visualDominance.pass_count < visualDominance.min_scenes) blockingFailures.push("ir:insufficient_dominant_visual_teaching_scenes");
    if (!sceneVisualBriefs.length) blockingFailures.push("ir:missing_scene_visual_brief");
    for (const sceneId of missingSceneVisualBriefs) blockingFailures.push(`ir:missing_scene_visual_brief:${sceneId}`);
    for (const item of incompleteSceneVisualBriefs) blockingFailures.push(`ir:incomplete_scene_visual_brief:${item.scene_id}`);
    for (const sceneId of unknownSceneVisualBriefs) blockingFailures.push(`ir:unknown_scene_visual_brief:${sceneId}`);
    for (const sceneId of duplicateSceneVisualBriefIds) blockingFailures.push(`ir:duplicate_scene_visual_brief:${sceneId}`);
  }

  return {
    path: irPath.startsWith(outDir) ? irPath.slice(outDir.length + 1) : irPath,
    exists: true,
    bytes: statSync(irPath).size,
    sha256: sha256(irPath),
    schema_version: ir.schema_version,
    quality_status: contract.quality_status || null,
    student_ready: contract.student_ready ?? null,
    visual_excellence_profile: Object.keys(visualExcellenceProfile).length
      ? {
          reference_style: visualExcellenceProfile.reference_style || null,
          must_show_count: Array.isArray(visualExcellenceProfile.must_show) ? visualExcellenceProfile.must_show.length : 0,
          motion_standards_count: Array.isArray(visualExcellenceProfile.motion_standards) ? visualExcellenceProfile.motion_standards.length : 0,
          layout_guards_count: Array.isArray(visualExcellenceProfile.layout_guards) ? visualExcellenceProfile.layout_guards.length : 0,
          release_bar: visualExcellenceProfile.release_bar || null,
        }
      : null,
    visual_archetype_decision_present: Object.keys(visualDecision).length > 0,
    domain_visual_plan_count: domainPlan.length,
    practice_blueprint_present: Boolean(practiceBlueprint && Object.keys(practiceBlueprint).length),
    scene_count: scenes.length,
    visual_node_count: nodes.length,
    animated_node_count: animatedNodes.length,
    action_count: actions.length,
    action_kind_counts: countBy(actions, (action) => action.kind),
    semantic_action_count: semanticActionCount,
    primitive_step_count: primitiveStepList.length,
    primitive_step_kind_counts: countBy(primitiveStepList, (step) => step.kind),
    teaching_visual_signature_count: uniqueTeachingVisualSignatureCount,
    teaching_visual_signature_counts: visualSignatureCounts,
    min_teaching_visual_signatures: minTeachingVisualSignatures,
    scene_visual_brief: {
      count: sceneVisualBriefs.length,
      teaching_scene_count: teachingSceneIds.length,
      covered_teaching_scene_count: teachingSceneIds.length - missingSceneVisualBriefs.length,
      missing_teaching_scene_ids: missingSceneVisualBriefs,
      incomplete: incompleteSceneVisualBriefs,
      unknown_scene_ids: unknownSceneVisualBriefs,
      duplicate_scene_ids: duplicateSceneVisualBriefIds,
    },
    visual_dominance: visualDominance,
    remotion_review_scene_ids: remotionReviewSceneIds,
    min_remotion_review_stills: minRemotionReviewStills,
    repeated_action_patterns: repeatedActionPatterns,
    blocking_failures: blockingFailures,
  };
}

function parseGate(raw, outDir) {
  const [name, statusText] = raw.split("=");
  if (!name || !statusText) throw new Error(`invalid --gate ${raw}`);
  const [status, warn = "0", ...reportParts] = statusText.split(":");
  const reportRaw = reportParts.join(":");
  const reportPath = reportRaw ? resolve(reportRaw) : null;
  const reportExists = reportPath ? existsSync(reportPath) : false;
  const reportText = reportExists ? readFileSync(reportPath, "utf8") : "";
  const reportHasFail = reportExists ? /^FAIL\b/m.test(reportText) : false;
  const reportFinalPass = reportExists ? /(?:animation IR contract gate|action authority gate|animation IR preview gate): PASS(?:\s|\(|$)/m.test(reportText) : false;
  const visualGateSummary = reportExists && name === "validate_animation_ir_preview"
    ? parsePreviewVisualGateSummary(reportText)
    : null;
  return {
    name,
    status,
    warn: Number(warn) || 0,
    report_path: reportPath ? (reportPath.startsWith(outDir) ? reportPath.slice(outDir.length + 1) : reportPath) : null,
    report_exists: reportExists,
    report_bytes: reportExists ? statSync(reportPath).size : 0,
    report_sha256: reportExists ? sha256(reportPath) : null,
    report_has_fail: reportHasFail,
    report_final_pass: reportFinalPass,
    visual_gate_summary: visualGateSummary,
  };
}

function parsePreviewVisualGateSummary(reportText) {
  const summary = {
    primary_object_coverage_min: null,
    primary_object_coverage_samples: 0,
    rule_card_area_max: null,
    rule_card_text_max: null,
    rule_card_top_min: null,
    label_clearance_min_px: null,
    scene_visual_similarity_max: null,
    blocking_checks: [],
  };
  const primaryMatches = [...reportText.matchAll(/runtime_blueprint_primary_object_coverage: [^\n]*primary object coverage ([0-9.]+) /g)]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite);
  if (primaryMatches.length) {
    summary.primary_object_coverage_min = Number(Math.min(...primaryMatches).toFixed(4));
    summary.primary_object_coverage_samples = primaryMatches.length;
  }
  const ruleMatches = [...reportText.matchAll(/runtime_blueprint_rule_card_budget: [^\n]*area=([0-9.]+)[^\n]*text=([0-9.]+)[^\n]*top=([0-9.]+)/g)]
    .map((match) => ({ area: Number(match[1]), text: Number(match[2]), top: Number(match[3]) }))
    .filter((item) => Number.isFinite(item.area) && Number.isFinite(item.text) && Number.isFinite(item.top));
  if (ruleMatches.length) {
    summary.rule_card_area_max = Number(Math.max(...ruleMatches.map((item) => item.area)).toFixed(4));
    summary.rule_card_text_max = Number(Math.max(...ruleMatches.map((item) => item.text)).toFixed(4));
    summary.rule_card_top_min = Number(Math.min(...ruleMatches.map((item) => item.top)).toFixed(4));
  }
  const clearanceMatches = [...reportText.matchAll(/runtime_blueprint_label_clearance: [^\n]*nearest label clearance ([0-9.]+)px/g)]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite);
  if (clearanceMatches.length) {
    summary.label_clearance_min_px = Number(Math.min(...clearanceMatches).toFixed(2));
  }
  const similarityMatch = reportText.match(/blueprint_scene_visual_similarity: [^\n]* similarity ([0-9.]+) <=/);
  if (similarityMatch) {
    summary.scene_visual_similarity_max = Number(Number(similarityMatch[1]).toFixed(4));
  }
  summary.blocking_checks = [...new Set([...reportText.matchAll(/^FAIL\s+\S+\s+(runtime_blueprint_primary_object_coverage|runtime_blueprint_rule_card_budget|runtime_blueprint_label_clearance|blueprint_scene_visual_similarity):/gm)].map((match) => match[1]))];
  return summary;
}

function parseScreenshot(raw, outDir) {
  const [viewport, rest] = raw.split("=");
  if (!viewport || !rest) throw new Error(`invalid --screenshot ${raw}`);
  const [pathText, ...issueParts] = rest.split(":");
  const path = resolve(pathText);
  const exists = existsSync(path);
  let reviewManifest = null;
  if (exists && path.endsWith(".json")) {
    try {
      const parsed = readJson(path);
      if (parsed?.schema_version === "luban_visual_review_wall.v0") {
        reviewManifest = {
          kind: "visual_review_wall",
          schema_version: parsed.schema_version,
          card_id: parsed.card_id || null,
          viewport_count: Number(parsed.viewport_count || 0),
          scene_count: Number(parsed.scene_count || 0),
          mode_count: Number(parsed.mode_count || 0),
          modes: Array.isArray(parsed.modes) ? parsed.modes : [],
          screenshot_count: Number(parsed.screenshot_count || 0),
          has_theater_clean: Array.isArray(parsed.modes) && parsed.modes.includes("theater_clean"),
        };
      } else if (parsed?.schema_version === "luban_remotion_still_review.v0") {
        const stills = Array.isArray(parsed.stills) ? parsed.stills : [];
        const stillChecks = stills.map((still) => {
          const stillPath = typeof still.path === "string" ? still.path : "";
          const candidates = [
            resolve(outDir, stillPath),
            resolve(dirname(path), stillPath),
          ];
          const actualPath = candidates.find((candidate) => existsSync(candidate)) || candidates[0];
          const actualExists = existsSync(actualPath);
          const actualSha = actualExists ? sha256(actualPath) : null;
          return {
            scene_id: still.scene_id || null,
            path: actualPath.startsWith(outDir) ? actualPath.slice(outDir.length + 1) : actualPath,
            exists: actualExists,
            hash_matches: actualExists && (!still.sha256 || still.sha256 === actualSha),
          };
        });
        reviewManifest = {
          kind: "remotion_still_review",
          schema_version: parsed.schema_version,
          card_id: parsed.card_id || null,
          composition_id: parsed.composition_id || null,
          still_count: stillChecks.length,
          scene_ids: stillChecks.map((still) => still.scene_id).filter(Boolean),
          scene_count: new Set(stillChecks.map((still) => still.scene_id).filter(Boolean)).size,
          files_exist: stillChecks.every((still) => still.exists),
          hashes_match: stillChecks.every((still) => still.hash_matches),
          has_quality_metrics: stills.length > 0 && stills.every((still) => still.quality_metrics && !still.quality_error),
          quality_summary: parsed.quality_summary || null,
          quality_gate: parsed.quality_gate || null,
          has_remotion_stills: stillChecks.length > 0 && stillChecks.every((still) => still.exists && still.hash_matches),
        };
      }
    } catch {}
  }
  return {
    viewport,
    path: path.startsWith(outDir) ? path.slice(outDir.length + 1) : path,
    exists,
    looked: true,
    issue: issueParts.join(":"),
    bytes: exists ? statSync(path).size : 0,
    sha256: sha256(path),
    review_manifest: reviewManifest,
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
  const irArg = takeFlag("--ir");
  if (!cardId || !outArg || args.includes("--help") || args.includes("-h")) {
    console.error(usage);
    return cardId || outArg ? 0 : 2;
  }
  const outPath = resolve(outArg);
  const outDir = dirname(outPath);
  const irSummary = irArg ? analyzeIr(irArg, outDir) : null;
  const gates = takeRepeat("--gate").map((raw) => parseGate(raw, outDir));
  const screenshots = takeRepeat("--screenshot").map((raw) => parseScreenshot(raw, outDir));
  const issues = takeRepeat("--issue").map(parseIssue);
  const triage = takeRepeat("--triage").map(parseTriage);

  if (args.length) throw new Error(`unknown args: ${args.join(" ")}`);

  const missingScreenshots = screenshots.filter((shot) => !shot.exists).map((shot) => shot.viewport);
  const failedGates = gates.filter((gate) => gate.status !== "PASS").map((gate) => gate.name);
  const irBlockingFailures = irSummary ? irSummary.blocking_failures || [] : [];
  const requiresVisualReviewEvidence = irSummary && VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(irSummary.quality_status);
  const missingMachineGates = requiresVisualReviewEvidence && gates.length === 0;
  const missingGateReports = requiresVisualReviewEvidence
    ? gates.filter((gate) => !gate.report_path || !gate.report_exists).map((gate) => gate.name)
    : [];
  const failedGateReports = requiresVisualReviewEvidence
    ? gates.filter((gate) => gate.report_exists && gate.report_has_fail).map((gate) => gate.name)
    : [];
  const missingGateFinalPass = requiresVisualReviewEvidence
    ? gates.filter((gate) => gate.report_exists && gate.status === "PASS" && !gate.report_final_pass).map((gate) => gate.name)
    : [];
  const gateNames = new Set(gates.map((gate) => gate.name));
  const missingRequiredPromotionGates = requiresVisualReviewEvidence
    ? REQUIRED_PROMOTION_GATE_NAMES.filter((name) => !gateNames.has(name))
    : [];
  const missingVisualReviewEvidence = requiresVisualReviewEvidence && screenshots.length === 0;
  const reviewManifests = screenshots.map((shot) => shot.review_manifest).filter(Boolean);
  const missingCleanTheaterReview = requiresVisualReviewEvidence && !reviewManifests.some((manifest) => manifest.has_theater_clean);
  const remotionStillManifests = reviewManifests.filter((manifest) => manifest.kind === "remotion_still_review");
  const missingRemotionStillReview = requiresVisualReviewEvidence && !remotionStillManifests.some((manifest) => manifest.has_remotion_stills);
  const missingRemotionStillQualityMetrics = requiresVisualReviewEvidence && !remotionStillManifests.some((manifest) => manifest.has_quality_metrics);
  const remotionQualityFlags = [
    ...new Set(
      remotionStillManifests.flatMap((manifest) => [
        ...((manifest.quality_summary && Array.isArray(manifest.quality_summary.flags)) ? manifest.quality_summary.flags : []),
        ...((manifest.quality_gate && Array.isArray(manifest.quality_gate.flags)) ? manifest.quality_gate.flags : []),
      ]),
    ),
  ];
  const failingRemotionQuality = requiresVisualReviewEvidence && remotionQualityFlags.length > 0;
  const remotionStillSceneIds = new Set(remotionStillManifests.flatMap((manifest) => manifest.scene_ids || []));
  const missingRemotionStillScenes = requiresVisualReviewEvidence && irSummary
    ? (irSummary.remotion_review_scene_ids || []).filter((sceneId) => !remotionStillSceneIds.has(sceneId))
    : [];
  const missingTriageForIssues = issues.length > 0 && triage.length === 0;
  const previewVisualGateSummary = gates.find((gate) => gate.name === "validate_animation_ir_preview" && gate.visual_gate_summary)?.visual_gate_summary || null;
  const verdict = failedGates.length || missingScreenshots.length || irBlockingFailures.length || missingMachineGates || missingGateReports.length || failedGateReports.length || missingGateFinalPass.length || missingRequiredPromotionGates.length || missingVisualReviewEvidence || missingCleanTheaterReview || missingRemotionStillReview || missingRemotionStillQualityMetrics || failingRemotionQuality || missingRemotionStillScenes.length || missingTriageForIssues || issues.some((issue) => ["CRITICAL", "HIGH"].includes(issue.severity))
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
    visual_gate_summary: previewVisualGateSummary,
    ir_summary: irSummary,
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
      ...irBlockingFailures,
      ...(missingMachineGates ? ["gate:missing_machine_gates"] : []),
      ...missingGateReports.map((name) => `gate:missing_report:${name}`),
      ...failedGateReports.map((name) => `gate:report_contains_fail:${name}`),
      ...missingGateFinalPass.map((name) => `gate:missing_final_pass:${name}`),
      ...missingRequiredPromotionGates.map((name) => `gate:missing_required:${name}`),
      ...(missingVisualReviewEvidence ? ["review:missing_visual_review_screenshot"] : []),
      ...(missingCleanTheaterReview ? ["review:missing_clean_theater_manifest"] : []),
      ...(missingRemotionStillReview ? ["review:missing_remotion_still_manifest"] : []),
      ...(missingRemotionStillQualityMetrics ? ["review:missing_remotion_quality_metrics"] : []),
      ...remotionQualityFlags.map((flag) => `review:remotion_quality_flag:${flag}`),
      ...missingRemotionStillScenes.map((sceneId) => `review:missing_remotion_still_scene:${sceneId}`),
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
