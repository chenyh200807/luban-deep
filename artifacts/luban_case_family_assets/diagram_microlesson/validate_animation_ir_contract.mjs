#!/usr/bin/env node
// Pre-render gate for OpenMAIC-style Luban animation IR.
// This runs before HTML or Remotion rendering: LLM/agents may design IR, but
// renderers only consume a schema-bounded scene/action/visual contract.

import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

const [, , irArg] = process.argv;
if (!irArg || process.argv.includes("--help") || process.argv.includes("-h")) {
  console.error("usage: node validate_animation_ir_contract.mjs <animation_ir.v0.json>");
  process.exit(irArg ? 0 : 2);
}

const irPath = resolve(irArg);
const root = dirname(irPath);
const results = [];
const pass = (check, message) => results.push({ level: "PASS", check, message });
const fail = (check, message) => results.push({ level: "FAIL", check, message });

const ACTION_KINDS = new Set(["camera", "highlight", "reveal", "annotate", "exit", "speech", "primitive_step"]);
const QUALITY_STATUSES = new Set([
  "coarse_draft_requires_single_card_review",
  "single_card_review_candidate",
  "workflow_candidate",
  "student_ready",
]);
const STUDENT_READY_STATUS = "student_ready";
const VISUAL_EXCELLENCE_REQUIRED_STATUSES = new Set(["workflow_candidate", "student_ready"]);
const REQUIRED_VISUAL_EXCELLENCE_FIELDS = [
  "reference_style",
  "must_show",
  "motion_standards",
  "layout_guards",
  "release_bar",
];
const PRIMITIVE_STEP_KINDS = new Set([
  "trace_path",
  "reveal_object",
  "move_object",
  "branch_eliminate",
  "scan_row",
  "explode_layer",
  "write_answer_atom",
  "cross_out",
]);
const VISUAL_KINDS = new Set([
  "pill",
  "roof_section",
  "bulge",
  "up_arrows",
  "up_arrow",
  "cut_cross",
  "dry_zone",
  "sweep_line",
  "membrane_strip",
  "coverage_bracket",
  "lap_curve",
  "water_layer",
  "check_badge",
  "answer_box",
  "dialogue_box",
  "closing_text",
  "challenge_button",
  "flow_arrow",
  "threshold_meter",
  "scaffold_frame",
  "process_flow",
  "layer_stack",
  "pit_threshold_board",
  "network_graph",
  "formula_chain",
  "power_distribution_tree",
  "decision_tree",
  "contrast_pair",
  "inspection_blueprint_board",
  "lifting_threshold_board",
  "grade_threshold_board",
  "answer_scan",
  "memory_table",
  "note",
]);
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
const ANIMATED_PRIMITIVE_KINDS = new Set([
  "roof_section",
  "scaffold_frame",
  "process_flow",
  "layer_stack",
  "pit_threshold_board",
  "network_graph",
  "formula_chain",
  "power_distribution_tree",
  "decision_tree",
  "contrast_pair",
  "inspection_blueprint_board",
  "lifting_threshold_board",
  "grade_threshold_board",
  "answer_scan",
]);
const DOMAIN_PICTORIAL_KINDS = new Set([
  "roof_section",
  "scaffold_frame",
  "bulge",
  "cut_cross",
  "dry_zone",
  "sweep_line",
  "membrane_strip",
  "coverage_bracket",
  "lap_curve",
  "water_layer",
  "check_badge",
  "layer_stack",
  "pit_threshold_board",
  "network_graph",
  "formula_chain",
  "power_distribution_tree",
  "contrast_pair",
  "inspection_blueprint_board",
  "lifting_threshold_board",
  "grade_threshold_board",
  "answer_scan",
  "memory_table",
]);
const DEFAULT_TEACHING_SCENE_IDS =["hook", "map", "rule", "trap", "score"];
const REQUIRED_BY_ARCHETYPE = {
  process_step_reveal: ["process_flow", "inspection_blueprint_board"],
  section_or_spatial_reveal: ["layer_stack", "roof_section", "power_distribution_tree", "pit_threshold_board"],
  calculation_structure: ["network_graph", "formula_chain"],
  decision_branch_reveal: ["decision_tree", "lifting_threshold_board", "grade_threshold_board"],
  contrast_reveal: ["contrast_pair"],
  scoring_diagnosis_reveal: ["answer_scan"],
  value_memory_card: ["memory_table"],
};
const INTERNAL_TOKEN_RE = /(source_ref|schema_version|candidate|official_score_allowed|\bE\d{2}\b|\bP\d{2,}\b)/i;
const REQUIRED_SCENE_STRING_FIELDS = ["id", "label", "scene", "focus", "keycard", "coach"];
const REQUIRED_SCENE_ARRAY_FIELDS = ["enter", "hold", "exit"];
const REQUIRED_SCENE_VISUAL_BRIEF_FIELDS = [
  "source_sentence",
  "visual_action",
  "state_change",
  "exit_before_next",
  "why_not_reused_template",
];
const REMOTION_COMPOSITION_ID_RE = /^[a-zA-Z0-9\u4e00-\u9fff-]+$/u;

function hasNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function charLength(value) {
  return Array.from(String(value || "").trim()).length;
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

function primitiveSteps(node) {
  return Array.isArray(node?.primitive_steps) ? node.primitive_steps : [];
}

function hasVisualExcellenceField(profile, field) {
  const value = profile[field];
  return Array.isArray(value) ? value.length > 0 : hasNonEmptyString(value);
}

function rendererHasPrimitiveBranch(sourceText, kind) {
  return (
    sourceText.includes(`node.kind === "${kind}"`) ||
    sourceText.includes(`node.kind === '${kind}'`) ||
    sourceText.includes(`kind == "${kind}"`) ||
    sourceText.includes(`kind == '${kind}'`) ||
    sourceText.includes(`case "${kind}"`) ||
    sourceText.includes(`case '${kind}'`)
  );
}

function escapedRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

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

function studentText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(studentText).join("\n");
  if (typeof value === "object") {
    return Object.entries(value)
      .filter(([key]) => ["text", "subtext", "label", "coach", "keycard"].includes(key))
      .map(([, item]) => studentText(item))
      .join("\n");
  }
  return "";
}

function isKnownTarget(target, scene, visualIds) {
  if (!target) return false;
  if (visualIds.has(target)) return true;
  if ((scene.visible_nodes || []).includes(target)) return true;
  if (scene.focus === target) return true;
  return ["scene", "whole_loop"].includes(target);
}

function isKnownPrimitiveStepTarget(target, visualNodes) {
  if (!target || typeof target !== "string") return false;
  const [nodeId, stepId, extra] = target.split(".");
  if (!nodeId || !stepId || extra) return false;
  const node = visualNodes.find((item) => item.id === nodeId);
  return primitiveSteps(node).some((step) => step.id === stepId);
}

function hasDomainObjects(node) {
  if (!node || typeof node !== "object") return false;
  if (node.domain_visual === true) return true;
  if (Array.isArray(node.domain_objects) && node.domain_objects.length) return true;
  if (Array.isArray(node.objects) && node.objects.length) return true;
  return false;
}

function positiveNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
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

function isDominantDiagramNode(node) {
  return node && !TEXT_CONTAINER_KINDS.has(node.kind) && hasDomainObjects(node);
}

function actionPattern(actions) {
  return actions
    .map((action) => {
      const targetClass = action.kind === "primitive_step" ? "primitive" : action.target ? "target" : "none";
      return `${action.kind}:${action.verb || ""}:${targetClass}:${Number(action.start ?? 0).toFixed(2)}-${Number(action.end ?? 0).toFixed(2)}`;
    })
    .join("|");
}

const ir = readJson(irPath);
if (ir) {
  ir.schema_version === "luban_animation_ir.v0"
    ? pass("schema_version", "schema_version is luban_animation_ir.v0")
    : fail("schema_version", "expected luban_animation_ir.v0");

  const scenes = Array.isArray(ir.scenes) ? ir.scenes : [];
  scenes.length >= 6 ? pass("scene_count", `${scenes.length} scenes`) : fail("scene_count", "expected at least 6 scenes");

  const contract = ir.render_contract || {};
  contract.html_preview ? pass("html_preview_contract", `html preview ${contract.html_preview}`) : fail("html_preview_contract", "missing render_contract.html_preview");
  contract.remotion_renderer ? pass("remotion_renderer_contract", `Remotion renderer ${contract.remotion_renderer}`) : fail("remotion_renderer_contract", "missing render_contract.remotion_renderer");
  contract.remotion_composition ? pass("remotion_composition_contract", `composition ${contract.remotion_composition}`) : fail("remotion_composition_contract", "missing render_contract.remotion_composition");
  if (contract.remotion_composition) {
    REMOTION_COMPOSITION_ID_RE.test(String(contract.remotion_composition))
      ? pass("remotion_composition_id_safe", "composition id is Remotion-safe")
      : fail("remotion_composition_id_safe", "composition id may only contain letters, numbers, CJK characters, and hyphen");
  }
  const qualityStatus = typeof contract.quality_status === "string" ? contract.quality_status.trim() : "";
  const claimsStudentReady = contract.student_ready === true;
  const explicitlyNotStudentReady = contract.student_ready === false;
  if (qualityStatus) {
    QUALITY_STATUSES.has(qualityStatus)
      ? pass("quality_status_declared", `quality_status=${qualityStatus}`)
      : fail("quality_status_declared", `unknown render_contract.quality_status ${qualityStatus}`);
  } else {
    fail("quality_status_declared", "missing render_contract.quality_status; must declare draft/candidate/student_ready status");
  }
  if (claimsStudentReady) {
    qualityStatus === STUDENT_READY_STATUS
      ? pass("student_ready_gate", "student_ready=true with student_ready quality_status")
      : fail("student_ready_gate", `student_ready=true requires quality_status=${STUDENT_READY_STATUS}, got ${qualityStatus || "(missing)"}`);
  } else if (explicitlyNotStudentReady) {
    pass("student_ready_gate", `student_ready=false; cannot be released as student-ready`);
  } else {
    fail("student_ready_gate", "missing render_contract.student_ready; draft/candidate cards must explicitly set false");
  }
  const allSceneIds = new Set(scenes.map((scene) => scene.id).filter(Boolean));
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(qualityStatus)) {
    const remotionReviewSceneIds = Array.isArray(contract.remotion_review_scene_ids)
      ? contract.remotion_review_scene_ids.filter(hasNonEmptyString)
      : [];
    const minRemotionReviewStills = Number(contract.min_remotion_review_stills ?? 3);
    if (remotionReviewSceneIds.length >= minRemotionReviewStills) {
      pass("remotion_review_scene_count", `${remotionReviewSceneIds.length} >= ${minRemotionReviewStills}`);
    } else {
      fail("remotion_review_scene_count", `workflow_candidate/student_ready requires at least ${minRemotionReviewStills} Remotion review scene(s)`);
    }
    const missingRemotionReviewScenes = remotionReviewSceneIds.filter((sceneId) => !allSceneIds.has(sceneId));
    missingRemotionReviewScenes.length
      ? fail("remotion_review_scene_ids", `unknown Remotion review scene(s): ${missingRemotionReviewScenes.join(",")}`)
      : pass("remotion_review_scene_ids", remotionReviewSceneIds.join(",") || "(none)");
  } else {
    pass("remotion_review_scene_scope", "Remotion still review scenes not required for this quality_status");
  }
  const visualExcellenceProfile = ir.visual_excellence_profile && typeof ir.visual_excellence_profile === "object" ? ir.visual_excellence_profile : {};
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(qualityStatus)) {
    if (Object.keys(visualExcellenceProfile).length) {
      pass("visual_excellence_profile_present", `profile=${visualExcellenceProfile.reference_style || "(unnamed)"}`);
    } else {
      fail("visual_excellence_profile_present", `${qualityStatus} requires visual_excellence_profile`);
    }
    for (const field of REQUIRED_VISUAL_EXCELLENCE_FIELDS) {
      hasVisualExcellenceField(visualExcellenceProfile, field)
        ? pass("visual_excellence_profile_field", `${field}`)
        : fail("visual_excellence_profile_field", `missing visual_excellence_profile.${field}`);
    }
  } else {
    pass("visual_excellence_profile_scope", `${qualityStatus || "(missing quality_status)"} does not claim workflow/student-ready visual quality`);
  }
  if (contract.remotion_renderer) {
    const rendererPath = join(root, contract.remotion_renderer);
    if (existsSync(rendererPath)) {
      pass("remotion_renderer_exists", `${contract.remotion_renderer} exists`);
      const rendererText = readFileSync(rendererPath, "utf8");
      const irFile = basename(irPath);
      rendererText.includes(irFile)
        ? pass("remotion_consumes_ir", `renderer imports ${irFile}`)
        : fail("remotion_consumes_ir", `renderer must import ${irFile}`);
      /AnimationIrRenderer/.test(rendererText)
        ? pass("remotion_generic_renderer", "renderer delegates to AnimationIrRenderer")
        : fail("remotion_generic_renderer", "renderer must delegate to generic AnimationIrRenderer");
    } else {
      fail("remotion_renderer_exists", `missing ${contract.remotion_renderer}`);
    }
  }
  if (contract.remotion_composition) {
    const remotionRootPath = join(root, "remotion_demo/src/Root.tsx");
    if (existsSync(remotionRootPath)) {
      const remotionRootText = readFileSync(remotionRootPath, "utf8");
      const compositionPattern = new RegExp(`id\\s*=\\s*["']${escapedRegExp(contract.remotion_composition)}["']`);
      compositionPattern.test(remotionRootText)
        ? pass("remotion_root_composition_registered", `Root.tsx registers ${contract.remotion_composition}`)
        : fail("remotion_root_composition_registered", `Root.tsx must register composition ${contract.remotion_composition}`);
    } else {
      fail("remotion_root_composition_registered", "missing remotion_demo/src/Root.tsx");
    }
  }
  Number.isFinite(Number(contract.challenge_unlock_sec))
    ? pass("challenge_unlock_contract", `challenge unlock ${Number(contract.challenge_unlock_sec).toFixed(2)}s`)
    : fail("challenge_unlock_contract", "missing render_contract.challenge_unlock_sec");

  const visualLibrary = ir.visual_library && typeof ir.visual_library === "object" ? ir.visual_library : {};
  Object.keys(visualLibrary).length ? pass("visual_library", `${Object.keys(visualLibrary).length} visual scenes`) : fail("visual_library", "missing visual_library");
  const visualDecision = ir.visual_archetype_decision && typeof ir.visual_archetype_decision === "object" ? ir.visual_archetype_decision : {};
  const pureTextAllowed = visualDecision.pure_text_allowed === true;
  const domainPlan = Array.isArray(visualDecision.domain_visual_plan) ? visualDecision.domain_visual_plan : [];
  if (Object.keys(visualDecision).length) {
    pass("visual_archetype_decision_present", "visual_archetype_decision exists");
  } else {
    fail("visual_archetype_decision_present", "missing visual_archetype_decision; must freeze archetype and domain visual plan before IR");
  }
  if (visualDecision.why_not_text || pureTextAllowed) {
    pass("why_not_text_present", pureTextAllowed ? "pure_text_allowed=true" : "why_not_text exists");
  } else {
    fail("why_not_text_present", "missing visual_archetype_decision.why_not_text");
  }
  if (pureTextAllowed) {
    pass("domain_visual_plan_scope", "pure_text_allowed=true");
  } else if (domainPlan.length) {
    pass("domain_visual_plan_present", `${domainPlan.length} domain visual plan item(s)`);
  } else {
    fail("domain_visual_plan_present", "missing domain_visual_plan; abstract boxes cannot substitute for domain objects");
  }
  const allVisualNodes = Object.values(visualLibrary).flatMap((visual) => (Array.isArray(visual.nodes) ? visual.nodes : []));
  const allVisualKinds = new Set(allVisualNodes.map((node) => node.kind).filter(Boolean));
  const allPrimitiveSteps = allVisualNodes.flatMap((node) => primitiveSteps(node).map((step) => ({ node, step })));
  for (const { node, step } of allPrimitiveSteps) {
    hasNonEmptyString(step.id)
      ? pass("primitive_step_id", `${node.id}.${step.id}`)
      : fail("primitive_step_id", `${node.id || "(missing node id)"}: primitive_steps[] item missing id`);
    PRIMITIVE_STEP_KINDS.has(step.kind)
      ? pass("primitive_step_kind", `${node.id}.${step.id}: ${step.kind}`)
      : fail("primitive_step_kind", `${node.id}.${step.id}: unsupported kind ${step.kind}`);
    hasNonEmptyString(step.domain_object) || hasNonEmptyArray(step.domain_objects)
      ? pass("primitive_step_domain_object", `${node.id}.${step.id}: domain object declared`)
      : fail("primitive_step_domain_object", `${node.id}.${step.id}: missing domain_object/domain_objects`);
    if (!Number.isFinite(Number(step.start)) || !Number.isFinite(Number(step.end)) || Number(step.start) > Number(step.end)) {
      fail("primitive_step_timing", `${node.id}.${step.id}: invalid start/end`);
    } else if (Number(step.start) < 0 || Number(step.end) > 1.05) {
      fail("primitive_step_timing", `${node.id}.${step.id}: timing must be normalized 0..1`);
    } else {
      pass("primitive_step_timing", `${node.id}.${step.id}: ${step.start}-${step.end}`);
    }
    if (!hasNonEmptyString(step.state_after) && !hasPlainObject(step.state_after) && !hasNonEmptyString(step.feedback)) {
      fail("primitive_step_feedback", `${node.id}.${step.id}: missing state_after or feedback`);
    } else {
      pass("primitive_step_feedback", `${node.id}.${step.id}: feedback/state declared`);
    }
  }
  const sharedSwitchNodes = allVisualNodes.filter((node) => node.kind === "power_distribution_tree" && node.mode === "shared_switch");
  if (sharedSwitchNodes.length) {
    const incomplete = sharedSwitchNodes.filter((node) => !hasNonEmptyString(node.second_device));
    incomplete.length
      ? fail("shared_switch_domain_objects", `${incomplete.map((node) => node.id || "(missing id)").join(",")}: shared_switch must name a second device`)
      : pass("shared_switch_domain_objects", `${sharedSwitchNodes.length} shared_switch node(s) name two devices`);
  }
  const archetype = ir.teaching_spine && typeof ir.teaching_spine === "object" ? ir.teaching_spine.archetype : "";
  REQUIRED_BY_ARCHETYPE[archetype]
    ? pass("archetype_known", `${archetype} is known`)
    : fail("archetype_known", `${archetype || "(missing archetype)"} is not a known 6+1 visual archetype`);
  const requiredKinds = Array.isArray(contract.archetype_visual_required)
    ? contract.archetype_visual_required
    : REQUIRED_BY_ARCHETYPE[archetype] || [];
  const canonicalRequiredKinds = REQUIRED_BY_ARCHETYPE[archetype] || [];
  const requiredShapeMatches =
    requiredKinds.length > 0 &&
    requiredKinds.every((kind) => canonicalRequiredKinds.includes(kind));
  requiredShapeMatches
    ? pass("archetype_visual_required_canonical", `${archetype}: ${requiredKinds.join("|")}`)
    : fail("archetype_visual_required_canonical", `${archetype}: expected ${canonicalRequiredKinds.join("|")}, got ${requiredKinds.join("|")}`);
  const hasArchetypeVisual = requiredKinds.some((kind) => allVisualKinds.has(kind));
  requiredKinds.length
    ? pass("archetype_visual_contract", `${archetype}: requires ${requiredKinds.join("|")}`)
    : fail("archetype_visual_contract", `${archetype || "(missing archetype)"}: missing required visual kind contract`);
  hasArchetypeVisual
    ? pass("archetype_visual_present", `${archetype}: found ${[...allVisualKinds].filter((kind) => requiredKinds.includes(kind)).join("|")}`)
    : fail("archetype_visual_present", `${archetype}: expected one of ${requiredKinds.join("|")}, found ${[...allVisualKinds].join(",")}`);
  const textOnlyKinds = [...allVisualKinds].filter((kind) => TEXT_CONTAINER_KINDS.has(kind));
  textOnlyKinds.length === allVisualKinds.size
    ? fail("archetype_not_text_only", `visual library is text-container-only: ${[...allVisualKinds].join(",")}`)
    : pass("archetype_not_text_only", `non-text primitives present: ${[...allVisualKinds].filter((kind) => !TEXT_CONTAINER_KINDS.has(kind)).join(",")}`);
  const teachingSceneIds = Array.isArray(contract.teaching_scene_ids) && contract.teaching_scene_ids.length
    ? contract.teaching_scene_ids
    : DEFAULT_TEACHING_SCENE_IDS;
  if (contract.layout_mode === "blueprint_poster") {
    contract.diagram_led_required === true
      ? pass("blueprint_poster_diagram_led_contract", "diagram_led_required=true")
      : fail("blueprint_poster_diagram_led_contract", "blueprint_poster requires render_contract.diagram_led_required=true");
    Number(contract.min_visual_attention_ratio ?? 0) >= 0.7
      ? pass("blueprint_poster_visual_attention_contract", `min_visual_attention_ratio=${contract.min_visual_attention_ratio}`)
      : fail("blueprint_poster_visual_attention_contract", "blueprint_poster requires min_visual_attention_ratio >= 0.7");
    Number(contract.min_domain_object_coverage_ratio ?? 0) >= 0.16
      ? pass("blueprint_poster_domain_object_coverage_contract", `min_domain_object_coverage_ratio=${contract.min_domain_object_coverage_ratio}`)
      : fail("blueprint_poster_domain_object_coverage_contract", "blueprint_poster requires min_domain_object_coverage_ratio >= 0.16");
    Number(contract.min_blueprint_surface_coverage_ratio ?? 0) >= 0.25
      ? pass("blueprint_poster_surface_coverage_contract", `min_blueprint_surface_coverage_ratio=${contract.min_blueprint_surface_coverage_ratio}`)
      : fail("blueprint_poster_surface_coverage_contract", "blueprint_poster requires min_blueprint_surface_coverage_ratio >= 0.25");
    Number(contract.max_svg_text_pressure_ratio ?? 1) <= 0.18
      ? pass("blueprint_poster_svg_text_pressure_contract", `max_svg_text_pressure_ratio=${contract.max_svg_text_pressure_ratio}`)
      : fail("blueprint_poster_svg_text_pressure_contract", "blueprint_poster requires max_svg_text_pressure_ratio <= 0.18");
    const maxCaptionChars = Number(contract.max_caption_chars ?? 18);
    const maxKeycardChars = Number(contract.max_keycard_chars ?? 14);
    const maxCoachChars = Number(contract.max_coach_chars ?? 24);
    const textBudgetIssues = [];
    for (const sceneId of teachingSceneIds) {
      const scene = scenes.find((candidate) => candidate.id === sceneId);
      if (!scene) continue;
      if (charLength(scene.caption) > maxCaptionChars) textBudgetIssues.push(`${sceneId}.caption ${charLength(scene.caption)}>${maxCaptionChars}`);
      if (charLength(scene.keycard) > maxKeycardChars) textBudgetIssues.push(`${sceneId}.keycard ${charLength(scene.keycard)}>${maxKeycardChars}`);
      if (charLength(scene.coach) > maxCoachChars) textBudgetIssues.push(`${sceneId}.coach ${charLength(scene.coach)}>${maxCoachChars}`);
      const visual = visualLibrary[sceneId];
      for (const node of Array.isArray(visual?.nodes) ? visual.nodes : []) {
        if (charLength(node.rule_main) > 18) textBudgetIssues.push(`${sceneId}.${node.id}.rule_main ${charLength(node.rule_main)}>18`);
        if (charLength(node.rule_sub) > 24) textBudgetIssues.push(`${sceneId}.${node.id}.rule_sub ${charLength(node.rule_sub)}>24`);
        if (charLength(node.text) > 18) textBudgetIssues.push(`${sceneId}.${node.id}.text ${charLength(node.text)}>18`);
      }
    }
    textBudgetIssues.length
      ? fail("blueprint_poster_text_budget", textBudgetIssues.slice(0, 12).join("; "))
      : pass("blueprint_poster_text_budget", `scene text fits caption/keycard/coach <= ${maxCaptionChars}/${maxKeycardChars}/${maxCoachChars}`);
  }
  const sceneVisualBriefs = Array.isArray(ir.scene_visual_brief) ? ir.scene_visual_brief : [];
  const sceneVisualBriefById = new Map();
  for (const brief of sceneVisualBriefs) {
    if (hasPlainObject(brief) && hasNonEmptyString(brief.scene_id)) {
      if (sceneVisualBriefById.has(brief.scene_id)) {
        fail("scene_visual_brief_unique", `${brief.scene_id}: duplicate scene_visual_brief entry`);
      } else {
        sceneVisualBriefById.set(brief.scene_id, brief);
      }
    }
  }
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(qualityStatus) && !pureTextAllowed) {
    sceneVisualBriefs.length
      ? pass("scene_visual_brief_present", `${sceneVisualBriefs.length} scene visual brief(s)`)
      : fail("scene_visual_brief_present", `${qualityStatus} requires scene_visual_brief[] before IR can be workflow_candidate/student_ready`);
    const unknownBriefScenes = [...sceneVisualBriefById.keys()].filter((sceneId) => !allSceneIds.has(sceneId));
    unknownBriefScenes.length
      ? fail("scene_visual_brief_scene_ids", `unknown scene_visual_brief scene(s): ${unknownBriefScenes.join(",")}`)
      : pass("scene_visual_brief_scene_ids", "all brief scene ids exist");
    for (const sceneId of teachingSceneIds) {
      const brief = sceneVisualBriefById.get(sceneId);
      if (!brief) {
        fail("scene_visual_brief_teaching_scene", `${sceneId}: missing visual brief`);
        continue;
      }
      const missingFields = REQUIRED_SCENE_VISUAL_BRIEF_FIELDS.filter((field) => !hasBriefValue(brief[field]));
      if (!hasNonEmptyArray(brief.domain_objects)) {
        missingFields.push("domain_objects");
      }
      missingFields.length
        ? fail("scene_visual_brief_teaching_scene", `${sceneId}: missing ${missingFields.join(",")}`)
        : pass("scene_visual_brief_teaching_scene", `${sceneId}: object/action/exit brief declared`);
    }
  } else {
    pass("scene_visual_brief_scope", `${qualityStatus || "(missing quality_status)"} does not require scene_visual_brief[]`);
  }
  const minDiagrammaticTeachingScenes = Number(contract.min_diagrammatic_teaching_scenes ?? teachingSceneIds.length);
  let diagrammaticTeachingSceneCount = 0;
  for (const sceneId of teachingSceneIds) {
    const visual = visualLibrary[sceneId];
    const kinds = visual && Array.isArray(visual.nodes) ? visual.nodes.map((node) => node.kind).filter(Boolean) : [];
    const diagramKinds = kinds.filter((kind) => !TEXT_CONTAINER_KINDS.has(kind));
    if (!visual) {
      fail("diagrammatic_teaching_scene", `${sceneId}: missing visual_library entry`);
    } else if (diagramKinds.length) {
      diagrammaticTeachingSceneCount += 1;
      pass("diagrammatic_teaching_scene", `${sceneId}: ${diagramKinds.join(",")}`);
    } else {
      fail("diagrammatic_teaching_scene", `${sceneId}: text-container-only teaching scene (${kinds.join(",") || "none"})`);
    }
  }
  diagrammaticTeachingSceneCount >= minDiagrammaticTeachingScenes
    ? pass("diagrammatic_teaching_scene_count", `${diagrammaticTeachingSceneCount}/${teachingSceneIds.length} >= ${minDiagrammaticTeachingScenes}`)
    : fail("diagrammatic_teaching_scene_count", `${diagrammaticTeachingSceneCount}/${teachingSceneIds.length} < ${minDiagrammaticTeachingScenes}`);
  const minDomainVisualTeachingScenes = pureTextAllowed
    ? 0
    : Number(contract.min_domain_visual_teaching_scenes ?? Math.min(4, teachingSceneIds.length));
  let domainVisualTeachingSceneCount = 0;
  for (const sceneId of teachingSceneIds) {
    const visual = visualLibrary[sceneId];
    const nodes = visual && Array.isArray(visual.nodes) ? visual.nodes : [];
    const domainNodes = nodes.filter(hasDomainObjects);
    if (pureTextAllowed) {
      continue;
    } else if (domainNodes.length) {
      domainVisualTeachingSceneCount += 1;
      pass(
        "domain_visual_teaching_scene",
        `${sceneId}: ${domainNodes
          .map((node) => `${node.kind}${Array.isArray(node.domain_objects) ? `(${node.domain_objects.join("/")})` : ""}`)
          .join(",")}`
      );
    } else {
      fail("domain_visual_teaching_scene", `${sceneId}: no domain objects; abstract text/box primitives are not enough`);
    }
  }
  domainVisualTeachingSceneCount >= minDomainVisualTeachingScenes
    ? pass("domain_visual_teaching_scene_count", `${domainVisualTeachingSceneCount}/${teachingSceneIds.length} >= ${minDomainVisualTeachingScenes}`)
    : fail("domain_visual_teaching_scene_count", `${domainVisualTeachingSceneCount}/${teachingSceneIds.length} < ${minDomainVisualTeachingScenes}`);
  if (VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(qualityStatus) && !pureTextAllowed) {
    const minVisualDominanceRatio = visualDominanceThreshold(contract);
    const minDominantVisualTeachingScenes = Number(contract.min_dominant_visual_teaching_scenes ?? teachingSceneIds.length);
    let dominantVisualTeachingSceneCount = 0;
    for (const sceneId of teachingSceneIds) {
      const visual = visualLibrary[sceneId];
      const nodes = visual && Array.isArray(visual.nodes) ? visual.nodes : [];
      const candidates = nodes
        .filter(isDominantDiagramNode)
        .map((node) => ({ node, ratio: visualNodeDominanceRatio(node, contract) }))
        .sort((left, right) => right.ratio - left.ratio);
      const best = candidates[0];
      if (best && best.ratio >= minVisualDominanceRatio) {
        dominantVisualTeachingSceneCount += 1;
        pass("dominant_visual_teaching_scene", `${sceneId}: ${best.node.kind}/${best.node.id} ${(best.ratio * 100).toFixed(1)}% >= ${(minVisualDominanceRatio * 100).toFixed(1)}%`);
      } else if (best) {
        fail("dominant_visual_teaching_scene", `${sceneId}: largest domain diagram ${best.node.kind}/${best.node.id} ${(best.ratio * 100).toFixed(1)}% < ${(minVisualDominanceRatio * 100).toFixed(1)}%`);
      } else {
        fail("dominant_visual_teaching_scene", `${sceneId}: no non-text domain diagram node with measured area`);
      }
    }
    dominantVisualTeachingSceneCount >= minDominantVisualTeachingScenes
      ? pass("dominant_visual_teaching_scene_count", `${dominantVisualTeachingSceneCount}/${teachingSceneIds.length} >= ${minDominantVisualTeachingScenes}`)
      : fail("dominant_visual_teaching_scene_count", `${dominantVisualTeachingSceneCount}/${teachingSceneIds.length} < ${minDominantVisualTeachingScenes}`);
  } else {
    pass("dominant_visual_teaching_scene_scope", `${qualityStatus || "(missing quality_status)"} does not require visual dominance gate`);
  }
  const primaryVisualPrimitiveRequired = contract.primary_visual_primitive_required;
  const primaryVisualKindsRequired = Array.isArray(primaryVisualPrimitiveRequired)
    ? primaryVisualPrimitiveRequired
    : hasNonEmptyString(primaryVisualPrimitiveRequired)
      ? [primaryVisualPrimitiveRequired]
      : [];
  if (primaryVisualKindsRequired.length) {
    const unknownPrimaryKinds = primaryVisualKindsRequired.filter((kind) => !VISUAL_KINDS.has(kind));
    if (unknownPrimaryKinds.length) {
      fail("primary_visual_primitive_known", `unknown primary visual primitive(s): ${unknownPrimaryKinds.join(",")}`);
    } else {
      pass("primary_visual_primitive_known", primaryVisualKindsRequired.join("|"));
    }
    const minPrimaryVisualScenes = Number(contract.min_primary_visual_teaching_scenes ?? teachingSceneIds.length);
    const primaryVisualTeachingScenes = teachingSceneIds.filter((sceneId) => {
      const visual = visualLibrary[sceneId];
      const kinds = visual && Array.isArray(visual.nodes) ? visual.nodes.map((node) => node.kind).filter(Boolean) : [];
      return kinds.some((kind) => primaryVisualKindsRequired.includes(kind));
    });
    primaryVisualTeachingScenes.length >= minPrimaryVisualScenes
      ? pass("primary_visual_primitive_scene_count", `${primaryVisualTeachingScenes.length}/${teachingSceneIds.length} >= ${minPrimaryVisualScenes}: ${primaryVisualKindsRequired.join("|")}`)
      : fail("primary_visual_primitive_scene_count", `${primaryVisualTeachingScenes.length}/${teachingSceneIds.length} < ${minPrimaryVisualScenes}: expected ${primaryVisualKindsRequired.join("|")}`);
  } else {
    pass("primary_visual_primitive_scope", "no primary visual primitive required by render_contract");
  }
  const scoreKinds = visualLibrary.score && Array.isArray(visualLibrary.score.nodes) ? visualLibrary.score.nodes.map((node) => node.kind).filter(Boolean) : [];
  const scoreDiagramKinds = scoreKinds.filter((kind) => !TEXT_CONTAINER_KINDS.has(kind));
  scoreDiagramKinds.length
    ? pass("score_scene_diagrammatic", `score uses ${scoreDiagramKinds.join(",")}`)
    : fail("score_scene_diagrammatic", `score scene must use answer-paper/diagnosis primitive, got ${scoreKinds.join(",") || "none"}`);
  const genericRendererPath = join(root, "remotion_demo/src/AnimationIrRenderer.tsx");
  let genericRendererText = "";
  if (existsSync(genericRendererPath)) {
    genericRendererText = readFileSync(genericRendererPath, "utf8");
    for (const kind of allVisualKinds) {
      const hasBranch = rendererHasPrimitiveBranch(genericRendererText, kind);
      hasBranch
        ? pass("remotion_primitive_coverage", `AnimationIrRenderer handles ${kind}`)
        : fail("remotion_primitive_coverage", `AnimationIrRenderer missing primitive ${kind}`);
    }
  } else {
    fail("remotion_primitive_coverage", `missing generic renderer ${genericRendererPath}`);
  }
  const htmlRendererPath = join(root, "render_animation_ir_preview.py");
  let htmlRendererText = "";
  if (existsSync(htmlRendererPath)) {
    htmlRendererText = readFileSync(htmlRendererPath, "utf8");
    for (const kind of allVisualKinds) {
      const hasBranch = rendererHasPrimitiveBranch(htmlRendererText, kind);
      hasBranch
        ? pass("html_primitive_coverage", `render_animation_ir_preview.py handles ${kind}`)
        : fail("html_primitive_coverage", `render_animation_ir_preview.py missing primitive ${kind}`);
    }
  } else {
    fail("html_primitive_coverage", `missing HTML preview renderer ${htmlRendererPath}`);
  }
  const requiresVisualSignatureHooks = VISUAL_EXCELLENCE_REQUIRED_STATUSES.has(contract.quality_status);
  if (requiresVisualSignatureHooks) {
    if (htmlRendererText.includes("data-visual-signature") && htmlRendererText.includes("data-visual-mode")) {
      pass("html_visual_signature_hooks", "HTML renderer exposes visual signature/mode hooks");
    } else {
      fail("html_visual_signature_hooks", "workflow_candidate/student_ready requires HTML visual signature/mode hooks");
    }
    if (htmlRendererText.includes("data-visual-signature-part")) {
      pass("html_visual_signature_parts", "HTML renderer exposes visual signature-part hooks");
    } else {
      fail("html_visual_signature_parts", "workflow_candidate/student_ready requires HTML signature-part hooks");
    }
    if (genericRendererText.includes("data-visual-signature") && genericRendererText.includes("data-visual-mode")) {
      pass("remotion_visual_signature_hooks", "Remotion renderer exposes visual signature/mode hooks");
    } else {
      fail("remotion_visual_signature_hooks", "workflow_candidate/student_ready requires Remotion visual signature/mode hooks");
    }
    if (genericRendererText.includes("data-visual-signature-part")) {
      pass("remotion_visual_signature_parts", "Remotion renderer exposes visual signature-part hooks");
    } else {
      fail("remotion_visual_signature_parts", "workflow_candidate/student_ready requires Remotion signature-part hooks");
    }
  } else {
    pass("visual_signature_hooks_scope", "visual signature hooks not required for this quality_status");
  }
  const animatedKindsUsed = [...allVisualKinds].filter((kind) => ANIMATED_PRIMITIVE_KINDS.has(kind));
  if (animatedKindsUsed.length) {
    allPrimitiveSteps.length
      ? pass("primitive_motion_plan_present", `${allPrimitiveSteps.length} IR-authored primitive step(s)`)
      : fail("primitive_motion_plan_present", `animated primitives require IR-authored primitive_steps[], used ${animatedKindsUsed.join(",")}`);
    htmlRendererText.includes("data-primitive-step")
      ? pass("html_internal_animation", `HTML renderer has primitive-internal steps for ${animatedKindsUsed.join(",")}`)
      : fail("html_internal_animation", `animated primitives require internal steps, used ${animatedKindsUsed.join(",")}`);
    /PrimitiveStep/.test(genericRendererText)
      ? pass("remotion_internal_animation", `Remotion renderer has PrimitiveStep for ${animatedKindsUsed.join(",")}`)
      : fail("remotion_internal_animation", `animated primitives require Remotion PrimitiveStep, used ${animatedKindsUsed.join(",")}`);
    if (allPrimitiveSteps.length) {
      genericRendererText.includes("data-primitive-step-id") &&
      genericRendererText.includes("data-step-target") &&
      genericRendererText.includes("data-domain-object") &&
      genericRendererText.includes("primitive_step")
        ? pass("remotion_primitive_step_authority", "Remotion renderer consumes IR primitive step metadata/action targets")
        : fail("remotion_primitive_step_authority", "Remotion renderer must expose primitive step id/kind/domain object and consume primitive_step action targets");
    }
  } else {
    pass("primitive_internal_animation", "no animated primitive kinds in IR");
  }

  const sceneIds = new Set();
  const maxNodes = Number(contract.max_visible_nodes ?? 4);
  let prevEnd = -Infinity;
  const teachingActionPatterns = new Map();
  let semanticActionCount = 0;
  for (const scene of scenes) {
    const label = scene.id || "(missing id)";
    if (sceneIds.has(scene.id)) fail("scene_unique_id", `duplicate scene id ${scene.id}`);
    sceneIds.add(scene.id);
    Number(scene.start_sec) < Number(scene.end_sec) ? pass("scene_timing", `${label}: ${scene.start_sec}-${scene.end_sec}`) : fail("scene_timing", `${label}: invalid start/end`);
    if (Number(scene.start_sec) < prevEnd - 0.001) fail("scene_overlap", `${label}: overlaps previous scene`);
    prevEnd = Number(scene.end_sec);
    for (const field of REQUIRED_SCENE_STRING_FIELDS) {
      hasNonEmptyString(scene[field])
        ? pass("scene_required_field", `${label}: ${field}`)
        : fail("scene_required_field", `${label}: missing non-empty ${field}`);
    }
    for (const field of REQUIRED_SCENE_ARRAY_FIELDS) {
      hasNonEmptyArray(scene[field])
        ? pass("scene_required_field", `${label}: ${field}[]`)
        : fail("scene_required_field", `${label}: missing non-empty ${field}[]`);
    }
    hasPlainObject(scene.layout)
      ? pass("scene_required_field", `${label}: layout`)
      : fail("scene_required_field", `${label}: missing layout object`);
    hasPlainObject(scene.camera) && hasNonEmptyString(scene.camera.verb)
      ? pass("scene_required_field", `${label}: camera.verb`)
      : fail("scene_required_field", `${label}: missing camera.verb`);

    const visibleNodes = Array.isArray(scene.visible_nodes) ? scene.visible_nodes : [];
    visibleNodes.length <= maxNodes ? pass("visible_budget", `${label}: ${visibleNodes.length}/${maxNodes}`) : fail("visible_budget", `${label}: ${visibleNodes.length} > ${maxNodes}`);
    visibleNodes.length > 0 ? pass("visible_nodes_present", `${label}: visible nodes present`) : fail("visible_nodes_present", `${label}: no visible_nodes`);

    const visual = visualLibrary[scene.id];
    if (!visual) {
      fail("visual_scene_exists", `${label}: missing visual_library entry`);
      continue;
    }
    const visualNodes = Array.isArray(visual.nodes) ? visual.nodes : [];
    const visualIds = new Set(visualNodes.map((node) => node.id).filter(Boolean));
    visualNodes.length ? pass("visual_nodes_present", `${label}: ${visualNodes.length} visual nodes`) : fail("visual_nodes_present", `${label}: no visual nodes`);
    for (const node of visualNodes) {
      node.id ? pass("visual_node_id", `${label}: ${node.id}`) : fail("visual_node_id", `${label}: visual node missing id`);
      VISUAL_KINDS.has(node.kind) ? pass("visual_node_kind", `${label}/${node.id}: ${node.kind}`) : fail("visual_node_kind", `${label}/${node.id}: unsupported kind ${node.kind}`);
      const text = studentText(node);
      if (INTERNAL_TOKEN_RE.test(text)) fail("student_safe_visual_text", `${label}/${node.id}: internal token in visible text`);
    }
    for (const nodeId of visibleNodes) {
      visualIds.has(nodeId) ? pass("visible_node_backed", `${label}: ${nodeId} backed by visual_library`) : fail("visible_node_backed", `${label}: ${nodeId} missing in visual_library`);
    }

    const actions = Array.isArray(scene.actions) ? scene.actions : [];
    actions.length ? pass("actions_present", `${label}: ${actions.length} actions`) : fail("actions_present", `${label}: missing actions[]`);
    if (teachingSceneIds.includes(scene.id)) {
      const pattern = actionPattern(actions);
      teachingActionPatterns.set(pattern, [...(teachingActionPatterns.get(pattern) || []), label]);
    }
    actions.some((action) => action.kind === "reveal") ? pass("reveal_action_present", `${label}: reveal action exists`) : fail("reveal_action_present", `${label}: no reveal action`);
    actions.some((action) => action.kind === "camera") ? pass("camera_action_present", `${label}: camera action exists`) : fail("camera_action_present", `${label}: no camera action`);
    for (const action of actions) {
      if (["primitive_step", "annotate", "speech"].includes(action.kind)) semanticActionCount += 1;
      ACTION_KINDS.has(action.kind) ? pass("action_kind", `${label}: ${action.kind}`) : fail("action_kind", `${label}: unsupported action ${action.kind}`);
      if (!Number.isFinite(Number(action.start)) || !Number.isFinite(Number(action.end)) || Number(action.start) > Number(action.end)) {
        fail("action_timing", `${label}: invalid action timing ${JSON.stringify(action)}`);
      } else if (Number(action.start) < 0 || Number(action.end) > 1.05) {
        fail("action_timing", `${label}: action timing must be normalized 0..1`);
      } else {
        pass("action_timing", `${label}: ${action.kind} ${action.start}-${action.end}`);
      }
      if (action.kind === "primitive_step") {
        isKnownPrimitiveStepTarget(action.target, visualNodes)
          ? pass("action_target", `${label}: primitive_step target ok`)
          : fail("action_target", `${label}: primitive_step target must be nodeId.stepId backed by visual_library primitive_steps[]`);
      } else if (action.kind === "reveal" && !visibleNodes.includes(action.target)) {
        fail("action_target", `${label}: reveal target ${action.target} must be in visible_nodes`);
      } else if (action.target && !isKnownTarget(action.target, scene, visualIds)) {
        fail("action_target", `${label}: unknown target ${action.target}`);
      } else {
        pass("action_target", `${label}: ${action.kind} target ok`);
      }
    }
  }
  semanticActionCount || allPrimitiveSteps.length
    ? pass("semantic_action_authority", `${semanticActionCount} semantic action(s), ${allPrimitiveSteps.length} primitive step(s)`)
    : fail("semantic_action_authority", "actions only prove playback scaffolding; need primitive_step/annotate/speech or IR-authored primitive_steps");
  const repeatedTeachingPatterns = [...teachingActionPatterns.values()].filter((labels) => labels.length > 2);
  repeatedTeachingPatterns.length
    ? fail("reused_action_template_limit", `teaching scenes reuse action templates: ${repeatedTeachingPatterns.map((labels) => labels.join("/")).join("; ")}`)
    : pass("reused_action_template_limit", "teaching action patterns are not repeated more than twice");

  const chapterIds = new Set((ir.chapters || []).map((chapter) => chapter.id));
  scenes.every((scene) => chapterIds.has(scene.id) || scene.id === "add" || scene.id === "seal" || scene.id === "qa_closure" || scene.id === "closing_challenge")
    ? pass("chapter_mapping", "scene ids have matching or grouped chapter labels")
    : fail("chapter_mapping", "some scenes are unreachable from chapter navigation");
}

for (const result of results) {
  console.log(`${result.level} ${basename(irPath)} ${result.check}: ${result.message}`);
}

const failCount = results.filter((result) => result.level === "FAIL").length;
if (failCount) {
  console.error(`animation IR contract gate: FAIL (${failCount} fail)`);
  process.exit(1);
}
console.log("animation IR contract gate: PASS");
