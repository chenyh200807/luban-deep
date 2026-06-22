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

const ACTION_KINDS = new Set(["camera", "highlight", "reveal", "annotate", "exit", "speech"]);
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
  "process_flow",
  "layer_stack",
  "network_graph",
  "formula_chain",
  "decision_tree",
  "contrast_pair",
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
const REQUIRED_BY_ARCHETYPE = {
  process_step_reveal: ["process_flow"],
  section_or_spatial_reveal: ["layer_stack", "roof_section"],
  calculation_structure: ["network_graph", "formula_chain"],
  decision_branch_reveal: ["decision_tree"],
  contrast_reveal: ["contrast_pair"],
  scoring_diagnosis_reveal: ["answer_scan"],
  value_memory_card: ["memory_table"],
};
const INTERNAL_TOKEN_RE = /(source_ref|schema_version|candidate|official_score_allowed|\bE\d{2}\b|\bP\d{2,}\b)/i;

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
  Number.isFinite(Number(contract.challenge_unlock_sec))
    ? pass("challenge_unlock_contract", `challenge unlock ${Number(contract.challenge_unlock_sec).toFixed(2)}s`)
    : fail("challenge_unlock_contract", "missing render_contract.challenge_unlock_sec");

  const visualLibrary = ir.visual_library && typeof ir.visual_library === "object" ? ir.visual_library : {};
  Object.keys(visualLibrary).length ? pass("visual_library", `${Object.keys(visualLibrary).length} visual scenes`) : fail("visual_library", "missing visual_library");
  const allVisualKinds = new Set(
    Object.values(visualLibrary)
      .flatMap((visual) => (Array.isArray(visual.nodes) ? visual.nodes : []))
      .map((node) => node.kind)
      .filter(Boolean)
  );
  const archetype = ir.teaching_spine && typeof ir.teaching_spine === "object" ? ir.teaching_spine.archetype : "";
  REQUIRED_BY_ARCHETYPE[archetype]
    ? pass("archetype_known", `${archetype} is known`)
    : fail("archetype_known", `${archetype || "(missing archetype)"} is not a known 6+1 visual archetype`);
  const requiredKinds = Array.isArray(contract.archetype_visual_required)
    ? contract.archetype_visual_required
    : REQUIRED_BY_ARCHETYPE[archetype] || [];
  const canonicalRequiredKinds = REQUIRED_BY_ARCHETYPE[archetype] || [];
  const requiredShapeMatches =
    requiredKinds.length === canonicalRequiredKinds.length &&
    canonicalRequiredKinds.every((kind) => requiredKinds.includes(kind));
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
  const genericRendererPath = join(root, "remotion_demo/src/AnimationIrRenderer.tsx");
  if (existsSync(genericRendererPath)) {
    const genericRendererText = readFileSync(genericRendererPath, "utf8");
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
  if (existsSync(htmlRendererPath)) {
    const htmlRendererText = readFileSync(htmlRendererPath, "utf8");
    for (const kind of allVisualKinds) {
      const hasBranch = rendererHasPrimitiveBranch(htmlRendererText, kind);
      hasBranch
        ? pass("html_primitive_coverage", `render_animation_ir_preview.py handles ${kind}`)
        : fail("html_primitive_coverage", `render_animation_ir_preview.py missing primitive ${kind}`);
    }
  } else {
    fail("html_primitive_coverage", `missing HTML preview renderer ${htmlRendererPath}`);
  }

  const sceneIds = new Set();
  const maxNodes = Number(contract.max_visible_nodes ?? 4);
  let prevEnd = -Infinity;
  for (const scene of scenes) {
    const label = scene.id || "(missing id)";
    if (sceneIds.has(scene.id)) fail("scene_unique_id", `duplicate scene id ${scene.id}`);
    sceneIds.add(scene.id);
    Number(scene.start_sec) < Number(scene.end_sec) ? pass("scene_timing", `${label}: ${scene.start_sec}-${scene.end_sec}`) : fail("scene_timing", `${label}: invalid start/end`);
    if (Number(scene.start_sec) < prevEnd - 0.001) fail("scene_overlap", `${label}: overlaps previous scene`);
    prevEnd = Number(scene.end_sec);

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
    actions.some((action) => action.kind === "reveal") ? pass("reveal_action_present", `${label}: reveal action exists`) : fail("reveal_action_present", `${label}: no reveal action`);
    actions.some((action) => action.kind === "camera") ? pass("camera_action_present", `${label}: camera action exists`) : fail("camera_action_present", `${label}: no camera action`);
    for (const action of actions) {
      ACTION_KINDS.has(action.kind) ? pass("action_kind", `${label}: ${action.kind}`) : fail("action_kind", `${label}: unsupported action ${action.kind}`);
      if (!Number.isFinite(Number(action.start)) || !Number.isFinite(Number(action.end)) || Number(action.start) > Number(action.end)) {
        fail("action_timing", `${label}: invalid action timing ${JSON.stringify(action)}`);
      } else if (Number(action.start) < 0 || Number(action.end) > 1.05) {
        fail("action_timing", `${label}: action timing must be normalized 0..1`);
      } else {
        pass("action_timing", `${label}: ${action.kind} ${action.start}-${action.end}`);
      }
      if (action.kind === "reveal" && !visibleNodes.includes(action.target)) {
        fail("action_target", `${label}: reveal target ${action.target} must be in visible_nodes`);
      } else if (action.target && !isKnownTarget(action.target, scene, visualIds)) {
        fail("action_target", `${label}: unknown target ${action.target}`);
      } else {
        pass("action_target", `${label}: ${action.kind} target ok`);
      }
    }
  }

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
