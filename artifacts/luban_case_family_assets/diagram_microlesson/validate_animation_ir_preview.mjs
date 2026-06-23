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

function charLength(value) {
  return Array.from(String(value || "").trim()).length;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function sceneVisualSimilaritySummary(ir, teachingSceneIds, primaryRequired) {
  const visualBriefs = new Map((Array.isArray(ir?.scene_visual_brief) ? ir.scene_visual_brief : [])
    .filter((brief) => brief && typeof brief === "object" && brief.scene_id)
    .map((brief) => [brief.scene_id, brief]));
  const tokenSet = (sceneId) => {
    const tokens = new Set([`scene:${sceneId}`]);
    const nodes = Array.isArray(ir?.visual_library?.[sceneId]?.nodes) ? ir.visual_library[sceneId].nodes : [];
    for (const node of nodes) {
      if (primaryRequired.length && !primaryRequired.includes(node.kind)) continue;
      tokens.add(`kind:${node.kind || "node"}`);
      tokens.add(`mode:${node.mode || "default"}`);
      tokens.add(`signature:${node.visual_signature || `${node.kind || "node"}:${node.mode || "default"}`}`);
      for (const item of asArray(node.domain_objects)) tokens.add(`object:${item}`);
      for (const step of asArray(node.primitive_steps)) {
        tokens.add(`step:${step.kind || "step"}:${step.domain_object || ""}:${step.target || ""}`);
      }
    }
    const scene = (ir?.scenes || []).find((item) => item.id === sceneId) || {};
    for (const action of asArray(scene.actions)) {
      if (action.kind === "primitive_step") {
        tokens.add(`action:${action.kind}:${action.verb || ""}:${action.step || action.target || ""}`);
      }
    }
    const brief = visualBriefs.get(sceneId) || {};
    for (const field of ["visual_action", "state_change", "exit_before_next", "why_not_reused_template"]) {
      const text = String(brief[field] || "");
      for (const token of text.split(/[，。；、,\s/|:：]+/).filter((item) => item.length >= 2)) {
        tokens.add(`${field}:${token}`);
      }
    }
    return tokens;
  };
  const sets = new Map(teachingSceneIds.map((sceneId) => [sceneId, tokenSet(sceneId)]));
  const pairs = [];
  for (let i = 0; i < teachingSceneIds.length; i += 1) {
    for (let j = i + 1; j < teachingSceneIds.length; j += 1) {
      const leftId = teachingSceneIds[i];
      const rightId = teachingSceneIds[j];
      const left = sets.get(leftId) || new Set();
      const right = sets.get(rightId) || new Set();
      const intersection = [...left].filter((token) => right.has(token)).length;
      const union = new Set([...left, ...right]).size || 1;
      pairs.push({
        left: leftId,
        right: rightId,
        ratio: Number((intersection / union).toFixed(4)),
      });
    }
  }
  pairs.sort((left, right) => right.ratio - left.ratio);
  return {
    max_pair: pairs[0] || null,
    pairs,
  };
}

function blueprintReferenceRequired(ir) {
  const profileText = [
    ir?.visual_excellence_profile?.reference_style,
    ir?.visual_excellence_profile?.reference_image_note,
    ir?.render_contract?.primary_visual_primitive_required,
  ].filter(Boolean).join(" ");
  return /blueprint|threshold|inspection_blueprint_board|lifting_threshold_board/i.test(profileText);
}

function getTeachingSceneIds(ir, scenes) {
  return Array.isArray(ir?.render_contract?.teaching_scene_ids) && ir.render_contract.teaching_scene_ids.length
    ? ir.render_contract.teaching_scene_ids
    : scenes.slice(0, Math.max(1, scenes.length - 2)).map((scene) => scene.id);
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
  if (ir.source_refs?.audio) {
    if (!/URL\.createObjectURL/.test(html) || !/fetch\(DATA\.audio\)/.test(html)) {
      fail("audio_seekable_preview", "audio previews must blob-load mp3 on HTTP so scrubber/chapter seek works with simple static servers");
    } else {
      pass("audio_seekable_preview", "audio preview uses Blob fallback for seekable local HTTP playback");
    }
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
  const primitiveActionCount = scenes
    .flatMap((scene) => (Array.isArray(scene.actions) ? scene.actions : []))
    .filter((action) => action.kind === "primitive_step").length;
  if (primitiveActionCount) {
    if (!/annotatePrimitiveSteps/.test(html) || !/primitiveStepTrace/.test(html) || !/stepTarget/.test(html)) {
      fail("primitive_step_playback_hooks", "primitive_step actions must annotate DOM steps and expose a runtime consumption trace");
    } else {
      pass("primitive_step_playback_hooks", `preview exposes runtime primitive step hooks for ${primitiveActionCount} action(s)`);
    }
  }
  if (!/controls-visible/.test(html)) {
    fail("theater_controls_autohide", "theater controls must use show/hide state");
  } else {
    pass("theater_controls_autohide", "has controls-visible show/hide state");
  }
  const sharedSwitchNodes = Object.values(ir.visual_library || {})
    .flatMap((visual) => (Array.isArray(visual.nodes) ? visual.nodes : []))
    .filter((node) => node.kind === "power_distribution_tree" && node.mode === "shared_switch");
  if (sharedSwitchNodes.length) {
    if (!/data-shared-switch-branch/.test(html) || !/data-shared-switch-device/.test(html)) {
      fail("shared_switch_renderer_hooks", "shared_switch must render countable branch and device hooks");
    } else {
      pass("shared_switch_renderer_hooks", "shared_switch exposes branch/device hooks for runtime audit");
    }
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
  if (ir.render_contract?.ai_ask_required) {
    if (!/data-ai-ask-entry/.test(html) || !/data-ai-ask-panel/.test(html) || !/luban_ai_ask/.test(html)) {
      fail("ai_ask_entry", "AI ask handoff requires an entry button, panel, and structured context event");
    } else {
      pass("ai_ask_entry", "AI ask entry exposes structured current-scene context");
    }
  }
  const requiresBlueprintReference = blueprintReferenceRequired(ir);
  if (requiresBlueprintReference) {
    const teachingSceneIds = getTeachingSceneIds(ir, scenes);
    const primaryRequired = Array.isArray(ir.render_contract?.primary_visual_primitive_required)
      ? ir.render_contract.primary_visual_primitive_required
      : ir.render_contract?.primary_visual_primitive_required
        ? [ir.render_contract.primary_visual_primitive_required]
        : [];
    const maxCaptionChars = Number(ir.render_contract?.max_caption_chars ?? 42);
    const isBlueprintPoster = ir.render_contract?.layout_mode === "blueprint_poster";
    const maxKeycardChars = Number(ir.render_contract?.max_keycard_chars ?? (isBlueprintPoster ? 14 : 28));
    const maxCoachChars = Number(ir.render_contract?.max_coach_chars ?? (isBlueprintPoster ? 24 : 72));
    const minVisualAttentionRatio = Number(ir.render_contract?.min_visual_attention_ratio ?? (isBlueprintPoster ? 0.7 : 0.55));
    const minDomainObjectCoverageRatio = Number(ir.render_contract?.min_domain_object_coverage_ratio ?? (isBlueprintPoster ? 0.16 : 0.12));
    const minBlueprintSurfaceCoverageRatio = Number(ir.render_contract?.min_blueprint_surface_coverage_ratio ?? (isBlueprintPoster ? 0.25 : 0.2));
    const maxSvgTextPressureRatio = Number(ir.render_contract?.max_svg_text_pressure_ratio ?? (isBlueprintPoster ? 0.16 : 0.24));
    const minPrimaryObjectCoverageRatio = Number(ir.render_contract?.min_primary_object_coverage_ratio ?? (isBlueprintPoster ? 0.22 : 0.14));
    const maxRuleCardAreaRatio = Number(ir.render_contract?.max_rule_card_area_ratio ?? (isBlueprintPoster ? 0.16 : 0.22));
    const maxRuleCardTextPressureRatio = Number(ir.render_contract?.max_rule_card_text_pressure_ratio ?? (isBlueprintPoster ? 0.06 : 0.1));
    const minRuleCardTopRatio = Number(ir.render_contract?.min_rule_card_top_ratio ?? (isBlueprintPoster ? 0.68 : 0.58));
    const minLabelClearancePx = Number(ir.render_contract?.min_label_clearance_px ?? (isBlueprintPoster ? 4 : 2));
    const maxSceneVisualSimilarityRatio = Number(ir.render_contract?.max_scene_visual_similarity_ratio ?? (isBlueprintPoster ? 0.82 : 0.9));
    const blueprintScenes = teachingSceneIds.filter((sceneId) => {
      const board = ir.visual_library?.[sceneId]?.board;
      return board === "blueprint" || board === "blueprint_poster";
    });
    const primaryScenes = teachingSceneIds.filter((sceneId) => {
      const kinds = (ir.visual_library?.[sceneId]?.nodes || []).map((node) => node.kind);
      return primaryRequired.length ? kinds.some((kind) => primaryRequired.includes(kind)) : kinds.some((kind) => /blueprint|threshold/.test(kind));
    });
    blueprintScenes.length === teachingSceneIds.length
      ? pass("blueprint_reference_board", `${blueprintScenes.length}/${teachingSceneIds.length} teaching scenes use blueprint board`)
      : fail("blueprint_reference_board", `${blueprintScenes.length}/${teachingSceneIds.length} teaching scenes use blueprint board`);
    primaryScenes.length === teachingSceneIds.length
      ? pass("blueprint_reference_primary_primitive", `${primaryScenes.length}/${teachingSceneIds.length} teaching scenes use ${primaryRequired.join("|") || "blueprint primitive"}`)
      : fail("blueprint_reference_primary_primitive", `${primaryScenes.length}/${teachingSceneIds.length} teaching scenes use ${primaryRequired.join("|") || "blueprint primitive"}`);
    const teachingSignatures = teachingSceneIds.flatMap((sceneId) => {
      const nodes = ir.visual_library?.[sceneId]?.nodes || [];
      return nodes
        .filter((node) => {
          if (!primaryRequired.length) return /blueprint|threshold/.test(String(node.kind || ""));
          return primaryRequired.includes(node.kind);
        })
        .map((node) => String(node.visual_signature || `${node.kind || "node"}:${node.mode || "default"}`));
    });
    const uniqueTeachingSignatures = new Set(teachingSignatures);
    const minSignatureCount = Math.min(4, teachingSceneIds.length);
    if (uniqueTeachingSignatures.size < minSignatureCount) {
      fail("blueprint_reference_visual_signature_variety", `${uniqueTeachingSignatures.size} visual signature(s), expected at least ${minSignatureCount}`);
    } else {
      pass("blueprint_reference_visual_signature_variety", `${uniqueTeachingSignatures.size} distinct teaching visual signature(s)`);
    }
    if (!/data-visual-signature=/.test(html) || !/data-visual-mode=/.test(html)) {
      fail("blueprint_reference_visual_signature_hooks", "blueprint HTML must expose visual signature/mode hooks");
    } else {
      pass("blueprint_reference_visual_signature_hooks", "blueprint HTML exposes visual signature/mode hooks");
    }
    if (!/data-visual-signature-part=/.test(html)) {
      fail("blueprint_reference_visual_signature_parts", "blueprint renderer must expose visible signature-part hooks");
    } else {
      pass("blueprint_reference_visual_signature_parts", "blueprint renderer exposes signature-part hooks");
    }
    if (!/data-engineering-object=/.test(html)) {
      fail("blueprint_reference_engineering_hooks", "blueprint HTML must expose data-engineering-object hooks");
    } else {
      pass("blueprint_reference_engineering_hooks", "blueprint HTML exposes engineering object hooks");
    }
    if (!/data-rule-card=/.test(html)) {
      fail("blueprint_reference_rule_card", "blueprint HTML must expose bottom rule-card hooks");
    } else {
      pass("blueprint_reference_rule_card", "blueprint HTML exposes rule-card hooks");
    }
    if (!/data-threshold-line=/.test(html)) {
      fail("blueprint_reference_threshold_hooks", "blueprint HTML must expose threshold/boundary line hooks");
    } else {
      pass("blueprint_reference_threshold_hooks", "blueprint HTML exposes threshold/boundary line hooks");
    }
    ir.render_contract?.caption_mode === "visual_brief"
      ? pass("blueprint_reference_caption_mode", "blueprint preview uses visual_brief captions")
      : fail("blueprint_reference_caption_mode", "blueprint previews must use render_contract.caption_mode=visual_brief, not full timing narration");
    const captionIssues = teachingSceneIds.flatMap((sceneId) => {
      const scene = scenes.find((candidate) => candidate.id === sceneId);
      const caption = scene?.caption;
      const issues = [];
      if (!caption) issues.push(`${sceneId}: missing caption`);
      if (charLength(caption) > maxCaptionChars) issues.push(`${sceneId}: ${charLength(caption)} chars > ${maxCaptionChars}`);
      if (/source_ref|schema_version|candidate|official_score_allowed|\bP\d{2,}\b|\bE\d{2}\b/i.test(String(caption || ""))) {
        issues.push(`${sceneId}: internal token in caption`);
      }
      return issues;
    });
    if (captionIssues.length) fail("blueprint_reference_caption_budget", captionIssues.join("; "));
    else pass("blueprint_reference_caption_budget", `${teachingSceneIds.length} teaching captions fit <= ${maxCaptionChars} chars`);
    if (isBlueprintPoster) {
      ir.render_contract?.diagram_led_required
        ? pass("blueprint_poster_diagram_led_contract", "layout declares diagram_led_required=true")
        : fail("blueprint_poster_diagram_led_contract", "blueprint_poster must declare render_contract.diagram_led_required=true");
      minVisualAttentionRatio >= 0.7
        ? pass("blueprint_poster_visual_attention_contract", `min visual attention ratio=${minVisualAttentionRatio}`)
        : fail("blueprint_poster_visual_attention_contract", `min visual attention ratio ${minVisualAttentionRatio} < 0.7`);
      minDomainObjectCoverageRatio >= 0.16
        ? pass("blueprint_poster_domain_object_coverage_contract", `min domain object coverage ratio=${minDomainObjectCoverageRatio}`)
        : fail("blueprint_poster_domain_object_coverage_contract", `min domain object coverage ratio ${minDomainObjectCoverageRatio} < 0.16`);
      minBlueprintSurfaceCoverageRatio >= 0.25
        ? pass("blueprint_poster_surface_coverage_contract", `min blueprint surface coverage ratio=${minBlueprintSurfaceCoverageRatio}`)
        : fail("blueprint_poster_surface_coverage_contract", `min blueprint surface coverage ratio ${minBlueprintSurfaceCoverageRatio} < 0.25`);
      maxSvgTextPressureRatio <= 0.18
        ? pass("blueprint_poster_svg_text_pressure_contract", `max SVG text pressure ratio=${maxSvgTextPressureRatio}`)
        : fail("blueprint_poster_svg_text_pressure_contract", `max SVG text pressure ratio ${maxSvgTextPressureRatio} > 0.18`);
      minPrimaryObjectCoverageRatio >= 0.22
        ? pass("blueprint_poster_primary_object_contract", `min primary object coverage ratio=${minPrimaryObjectCoverageRatio}`)
        : fail("blueprint_poster_primary_object_contract", `min primary object coverage ratio ${minPrimaryObjectCoverageRatio} < 0.22`);
      maxRuleCardAreaRatio <= 0.16 && maxRuleCardTextPressureRatio <= 0.06 && minRuleCardTopRatio >= 0.68
        ? pass("blueprint_poster_rule_card_contract", `rule card area<=${maxRuleCardAreaRatio}, text<=${maxRuleCardTextPressureRatio}, top>=${minRuleCardTopRatio}`)
        : fail("blueprint_poster_rule_card_contract", `rule card contract must keep area<=0.16, text<=0.06, top>=0.68; got area<=${maxRuleCardAreaRatio}, text<=${maxRuleCardTextPressureRatio}, top>=${minRuleCardTopRatio}`);
      minLabelClearancePx >= 4
        ? pass("blueprint_poster_label_clearance_contract", `min label clearance=${minLabelClearancePx}px`)
        : fail("blueprint_poster_label_clearance_contract", `min label clearance ${minLabelClearancePx}px < 4px`);
      maxSceneVisualSimilarityRatio <= 0.82
        ? pass("blueprint_scene_visual_similarity_contract", `max scene visual similarity=${maxSceneVisualSimilarityRatio}`)
        : fail("blueprint_scene_visual_similarity_contract", `max scene visual similarity ${maxSceneVisualSimilarityRatio} > 0.82`);
      const similarity = sceneVisualSimilaritySummary(ir, teachingSceneIds, primaryRequired);
      if (similarity.max_pair && similarity.max_pair.ratio > maxSceneVisualSimilarityRatio) {
        fail("blueprint_scene_visual_similarity", `${similarity.max_pair.left}<->${similarity.max_pair.right} similarity ${similarity.max_pair.ratio} > ${maxSceneVisualSimilarityRatio}`);
      } else if (similarity.max_pair) {
        pass("blueprint_scene_visual_similarity", `max ${similarity.max_pair.left}<->${similarity.max_pair.right} similarity ${similarity.max_pair.ratio} <= ${maxSceneVisualSimilarityRatio}`);
      } else {
        pass("blueprint_scene_visual_similarity", "single teaching scene has no reusable-scene pair");
      }
      const textIssues = teachingSceneIds.flatMap((sceneId) => {
        const scene = scenes.find((candidate) => candidate.id === sceneId) || {};
        const issues = [];
        if (charLength(scene.keycard) > maxKeycardChars) issues.push(`${sceneId}: keycard ${charLength(scene.keycard)} > ${maxKeycardChars}`);
        if (charLength(scene.coach) > maxCoachChars) issues.push(`${sceneId}: coach ${charLength(scene.coach)} > ${maxCoachChars}`);
        return issues;
      });
      if (textIssues.length) fail("blueprint_poster_text_budget", textIssues.join("; "));
      else pass("blueprint_poster_text_budget", `keycard/coach fit <= ${maxKeycardChars}/${maxCoachChars} chars`);
      if (/grid-template-columns:minmax\(0,1fr\)\s+160px/.test(html)) {
        fail("blueprint_poster_no_text_sidebar", "blueprint_poster must not reserve a right-side text rail");
      } else {
        pass("blueprint_poster_no_text_sidebar", "blueprint_poster does not reserve a text sidebar");
      }
    }
  } else {
    pass("blueprint_reference_scope", "IR does not claim blueprint/threshold reference style");
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
      if (requiresBlueprintReference && preview.captionMode !== "visual_brief") {
        fail("ir_html_caption_mode", `preview captionMode drift: ${preview.captionMode || "(missing)"}`);
      } else {
        pass("ir_html_caption_mode", `preview captionMode=${preview.captionMode || "timing"}`);
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

  const internalTokens = [/source_ref/i, /schema_version/i, /candidate/i, /official_score_allowed/i, /\bA\d{2}\b/, /\bE\d{2}\b/, /\bF\d{2}\b/, /\bJ\d{2}\b/, /\bN\d{2}\b/, /\bP\d{2,}\b/, /\bS\d{2}\b/];
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
    const requiresBlueprintReference = blueprintReferenceRequired(ir);
    const blueprintTeachingSceneIds = new Set(requiresBlueprintReference ? getTeachingSceneIds(ir, ir.scenes || []) : []);
    const maxCaptionChars = Number(ir.render_contract?.max_caption_chars ?? 42);
    const isBlueprintPoster = ir.render_contract?.layout_mode === "blueprint_poster";
    const minVisualAttentionRatio = Number(ir.render_contract?.min_visual_attention_ratio ?? (isBlueprintPoster ? 0.7 : 0.55));
    const maxTextOverlayRatio = Number(ir.render_contract?.max_text_overlay_ratio ?? (isBlueprintPoster ? 0.16 : 0.28));
    const minDomainObjectCoverageRatio = Number(ir.render_contract?.min_domain_object_coverage_ratio ?? (isBlueprintPoster ? 0.16 : 0.12));
    const minBlueprintSurfaceCoverageRatio = Number(ir.render_contract?.min_blueprint_surface_coverage_ratio ?? (isBlueprintPoster ? 0.25 : 0.2));
    const maxSvgTextPressureRatio = Number(ir.render_contract?.max_svg_text_pressure_ratio ?? (isBlueprintPoster ? 0.16 : 0.24));
    const minPrimaryObjectCoverageRatio = Number(ir.render_contract?.min_primary_object_coverage_ratio ?? (isBlueprintPoster ? 0.22 : 0.14));
    const maxRuleCardAreaRatio = Number(ir.render_contract?.max_rule_card_area_ratio ?? (isBlueprintPoster ? 0.16 : 0.22));
    const maxRuleCardTextPressureRatio = Number(ir.render_contract?.max_rule_card_text_pressure_ratio ?? (isBlueprintPoster ? 0.06 : 0.1));
    const minRuleCardTopRatio = Number(ir.render_contract?.min_rule_card_top_ratio ?? (isBlueprintPoster ? 0.68 : 0.58));
    const minLabelClearancePx = Number(ir.render_contract?.min_label_clearance_px ?? (isBlueprintPoster ? 4 : 2));
    const viewports = [
      { name: "portrait_360", width: 360, height: 740, mobile: true },
      { name: "portrait_390", width: 390, height: 844, mobile: true },
      { name: "portrait_430", width: 430, height: 932, mobile: true },
      { name: "landscape_844", width: 844, height: 390, mobile: true },
      { name: "landscape_932", width: 932, height: 430, mobile: true },
      { name: "embed_980", width: 980, height: 820, mobile: false },
      { name: "embed_1082", width: 1082, height: 950, mobile: false },
      { name: "wide_1302", width: 1302, height: 950, mobile: false },
    ];
    const samples = ir.scenes.filter(Boolean);
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
      const response = await client.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
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
          const active = document.querySelector(".scene.active");
          const aiAskButtons = [...document.querySelectorAll("[data-ai-ask-entry]")].filter(visible).length;
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
            activeGrid: active ? getComputedStyle(active).gridTemplateColumns : "",
            aiAskButtons,
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
      const gridColumns = String(layoutValue.activeGrid || "").trim().split(/\s+/).filter(Boolean).length;
      const mediumDesktopEmbed = viewport.mobile === false && viewport.width < 1120 && viewport.height > 520;
      if (mediumDesktopEmbed && gridColumns > 1) {
        fail("runtime_medium_embed_single_column", `${viewport.name}: medium embedded viewport must stay single-column, got ${layoutValue.activeGrid}`);
      } else if (mediumDesktopEmbed) {
        pass("runtime_medium_embed_single_column", `${viewport.name}: medium embedded viewport uses single-column stage`);
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
      if (ir.render_contract?.ai_ask_required) {
        layoutValue.aiAskButtons >= 1 ? pass("runtime_ai_ask_entry", `${viewport.name}: AI ask entry visible`) : fail("runtime_ai_ask_entry", `${viewport.name}: AI ask entry missing`);
      }

      for (const scene of samples) {
        const sceneStart = Number(scene.start_sec);
        const sceneEnd = Number(scene.end_sec);
        const sceneDur = Math.max(0.8, sceneEnd - sceneStart);
        const sceneVisualNodes = ir.visual_library?.[scene.id]?.nodes || [];
        const sceneHasSharedSwitch = sceneVisualNodes.some((node) => node.kind === "power_distribution_tree" && node.mode === "shared_switch");
        const expectedPrimitiveActions = (Array.isArray(scene.actions) ? scene.actions : []).filter((action) => action.kind === "primitive_step");
        const t = sceneStart + Math.max(0.25, Math.min(sceneDur - 0.15, Math.max(0.8, sceneDur * 0.86)));
        const expression = `
        (() => {
          window.__IR_PLAYER__.seek(${JSON.stringify(t)});
          const visible = (el) => {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return cs.display !== "none" && cs.visibility !== "hidden" && Number(cs.opacity || 1) > 0.05 && r.width > 1 && r.height > 1;
          };
          const visibleSvg = (el) => {
            if (!el) return false;
            let cur = el;
            while (cur && cur.nodeType === 1) {
              const cs = getComputedStyle(cur);
              if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity || 1) <= 0.05) return false;
              cur = cur.parentElement;
            }
            const r = el.getBoundingClientRect();
            if (r.width > 1 && r.height > 1) return true;
            if (typeof el.getBBox === "function") {
              const b = el.getBBox();
              return b.width > 1 || b.height > 1;
            }
            return false;
          };
          const rect = (el) => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
          };
          const intersects = (a,b,pad=1) => !!a && !!b && a.left < b.right - pad && a.right > b.left + pad && a.top < b.bottom - pad && a.bottom > b.top + pad;
          const activeScenes = [...document.querySelectorAll(".scene.active")];
          const active = activeScenes[0];
          const stageRect = rect(document.querySelector(".stage"));
          const visualRect = rect(active?.querySelector(".visual"));
          const diagramRect = active ? [...active.querySelectorAll(".visual svg")]
            .filter(visible)
            .map(rect)
            .filter(Boolean)
            .sort((left, right) => (right.width * right.height) - (left.width * left.height))[0] || visualRect
            : visualRect;
          const playerState = window.__IR_PLAYER__.state();
          const primitiveTrace = Array.isArray(playerState.primitiveTrace) ? playerState.primitiveTrace : [];
          const primitiveMissing = primitiveTrace
            .filter((item) => item.status !== "consumed")
            .map((item) => item.target + ":" + item.status);
          const primitiveMetadataIssues = active ? [...active.querySelectorAll("[data-primitive-step-id]")]
            .filter((el) => !(el.dataset.stepKind && el.dataset.domainObject && el.dataset.stepTarget))
            .map((el) => el.dataset.primitiveStepId || el.dataset.primitiveStep || "step")
            .slice(0, 12) : [];
          const player = document.querySelector(".player");
          const playerRect = rect(player);
          const coachRect = rect(active?.querySelector(".coach-card"));
          const captionRect = rect(document.querySelector(".caption-line"));
          const ratio = (part, whole) => {
            if (!part || !whole || whole.width <= 0 || whole.height <= 0) return 0;
            return Math.max(0, Math.min(1, (part.width * part.height) / (whole.width * whole.height)));
          };
          const gap = (a, b) => {
            if (!a || !b) return Infinity;
            if (intersects(a, b, 0)) return 0;
            const dx = Math.max(0, a.left > b.right ? a.left - b.right : b.left - a.right);
            const dy = Math.max(0, a.top > b.bottom ? a.top - b.bottom : b.top - a.bottom);
            return Math.sqrt(dx * dx + dy * dy);
          };
          const unionRect = (rects) => {
            const usable = rects.filter((item) => item && item.width > 1 && item.height > 1);
            if (!usable.length) return null;
            const left = Math.min(...usable.map((item) => item.left));
            const top = Math.min(...usable.map((item) => item.top));
            const right = Math.max(...usable.map((item) => item.right));
            const bottom = Math.max(...usable.map((item) => item.bottom));
            return { left, top, right, bottom, width: right - left, height: bottom - top };
          };
          const visualAttentionRatio = ratio(visualRect, stageRect);
          const textOverlayRatio = ratio(coachRect, stageRect) + ratio(captionRect, stageRect);
          const inViewport = (r) => !!r && r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && r.bottom <= innerHeight + 1;
          const pillLabelIssues = active ? [...active.querySelectorAll('[data-visual-kind="pill"]')].flatMap((node) => {
            const box = node.querySelector("rect");
            if (!box || !box.getBBox) return [];
            const rb = box.getBBox();
            return [...node.querySelectorAll("text")].filter((text) => {
              const tb = text.getBBox();
              return tb.x < rb.x + 4 || tb.x + tb.width > rb.x + rb.width - 4 || tb.y < rb.y + 3 || tb.y + tb.height > rb.y + rb.height - 3;
            }).map((text) => (node.dataset.visibleNode || "pill") + ":" + (text.textContent || "").trim().slice(0, 18));
          }) : [];
          const svgTextIssues = active ? (() => {
            const issues = [];
            const texts = [...active.querySelectorAll("[data-visible-node] text")]
              .filter(visible)
              .map((text) => {
                const node = text.closest("[data-visible-node]");
                return { text, node, id: node?.dataset.visibleNode || "text", kind: node?.dataset.visualKind || "", label: (text.textContent || "").trim().slice(0, 18), rect: rect(text) };
              })
              .filter((item) => item.label && item.rect);
            for (let i = 0; i < texts.length; i += 1) {
              for (let j = i + 1; j < texts.length; j += 1) {
                if (texts[i].node === texts[j].node) continue;
                if (intersects(texts[i].rect, texts[j].rect, 3)) {
                  issues.push(texts[i].id + ":" + texts[i].label + "<->" + texts[j].id + ":" + texts[j].label);
                }
              }
            }
            for (const node of [...active.querySelectorAll('[data-visual-kind="flow_arrow"]')].filter(visible)) {
              const path = node.querySelector("path");
              if (!path || !path.getBBox) continue;
              const pb = path.getBBox();
              for (const text of [...node.querySelectorAll("text")].filter(visible)) {
                const tb = text.getBBox();
                const lineZone = { x: pb.x - 8, y: pb.y - 10, width: pb.width + 16, height: Math.max(20, pb.height + 20) };
                const overlapsLineZone = tb.x < lineZone.x + lineZone.width && tb.x + tb.width > lineZone.x && tb.y < lineZone.y + lineZone.height && tb.y + tb.height > lineZone.y;
                if (overlapsLineZone) {
                  issues.push((node.dataset.visibleNode || "flow_arrow") + " label too close to arrow:" + (text.textContent || "").trim().slice(0, 18));
                }
              }
            }
            return issues;
          })() : [];
          const svgBoardIssues = active ? (() => {
            const issues = [];
            for (const svg of [...active.querySelectorAll(".visual svg")].filter(visible)) {
              const svgRect = rect(svg);
              const board = [...svg.querySelectorAll("rect")]
                .map((el) => ({el, rect: rect(el)}))
                .filter((item) => item.rect && item.rect.width > svgRect.width * 0.45 && item.rect.height > svgRect.height * 0.35)
                .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height))[0]?.rect;
              if (!board) continue;
              for (const text of [...svg.querySelectorAll("[data-visible-node] text")].filter(visible)) {
                const textRect = rect(text);
                const label = (text.textContent || "").trim().slice(0, 18);
                if (!label || !textRect) continue;
                const inside = textRect.left >= board.left - 2 && textRect.right <= board.right + 2 && textRect.top >= board.top - 2 && textRect.bottom <= board.bottom + 2;
                if (!inside) issues.push(label);
              }
            }
            return issues;
          })() : [];
          const protectedEls = [
            ...document.querySelectorAll(".scene.active .visual, .caption-line, .scene.active .coach-card, .challenge-inline")
          ].filter(visible);
          const playerBlocks = protectedEls
            .map((el) => ({name: el.className || el.tagName, rect: rect(el)}))
            .filter((item) => intersects(playerRect, item.rect))
            .map((item) => item.name);
          const askRect = rect(document.querySelector("[data-ai-ask-entry]"));
          const askBlocks = protectedEls
            .map((el) => ({name: el.className || el.tagName, rect: rect(el)}))
            .filter((item) => intersects(askRect, item.rect))
            .map((item) => item.name);
          const centerPlayBlocks = [...document.querySelectorAll(".center-play")].filter(visible)
            .flatMap((overlay) => protectedEls
              .map((el) => ({name: el.className || el.tagName, rect: rect(el), overlayRect: rect(overlay)}))
              .filter((item) => intersects(item.overlayRect, item.rect))
              .map((item) => item.name));
          const captionCoachOverlap = intersects(rect(document.querySelector(".caption-line")), rect(document.querySelector(".scene.active .coach-card")));
          const offSceneVisible = [...document.querySelectorAll(".scene:not(.active) [data-visible-node]")].filter(visible).length;
          const sharedSwitchBranches = active ? [...active.querySelectorAll('[data-shared-switch-branch="1"]')].filter(visibleSvg).length : 0;
          const sharedSwitchDevices = active ? [...active.querySelectorAll('[data-shared-switch-device="1"]')].filter(visibleSvg).length : 0;
          const visibleHook = (el) => {
            const node = el.closest("[data-visible-node]");
            const step = el.closest("[data-primitive-step]");
            const stepOpacity = step ? Number(getComputedStyle(step).opacity || 1) : 1;
            return (!node || visible(node)) && stepOpacity > 0.05;
          };
          const domainObjectRects = active ? [
            ...active.querySelectorAll("[data-engineering-object], [data-threshold-line], [data-visual-signature-part]")
          ].filter(visibleHook).map(rect).filter(Boolean) : [];
          const domainObjectUnion = unionRect(domainObjectRects);
          const domainObjectCoverageRatio = ratio(domainObjectUnion, stageRect);
          const primaryObjectRects = active ? [
            ...active.querySelectorAll("[data-engineering-object], [data-visual-signature-part]")
          ]
            .filter((el) => !el.closest("[data-rule-card]") && !el.matches("[data-rule-card]"))
            .filter((el) => !el.matches("[data-threshold-line]"))
            .filter(visibleHook)
            .map(rect)
            .filter(Boolean) : [];
          const primaryObjectUnion = unionRect(primaryObjectRects);
          const primaryObjectCoverageRatio = ratio(primaryObjectUnion, diagramRect || visualRect || stageRect);
          const blueprintSurfaceRects = active ? [
            ...active.querySelectorAll("[data-engineering-object], [data-threshold-line], [data-visual-signature-part], [data-rule-card]")
          ].filter(visibleHook).map(rect).filter(Boolean) : [];
          const blueprintSurfaceUnion = unionRect(blueprintSurfaceRects);
          const blueprintSurfaceCoverageRatio = ratio(blueprintSurfaceUnion, stageRect);
          const ruleCardRects = active ? [...active.querySelectorAll("[data-rule-card]")]
            .filter(visibleHook)
            .map(rect)
            .filter(Boolean) : [];
          const ruleCardUnion = unionRect(ruleCardRects);
          const ruleCardTopInSvgRatio = active ? (() => {
            const card = [...active.querySelectorAll("[data-rule-card]")].filter(visibleHook)[0];
            const svg = card?.closest("svg");
            if (!card || !svg || typeof card.getBBox !== "function") return null;
            const viewBox = svg.viewBox?.baseVal;
            const box = card.getBBox();
            if (!viewBox || !viewBox.height) return null;
            return Math.max(0, Math.min(1, (box.y - viewBox.y) / viewBox.height));
          })() : null;
          const ruleCardAreaRatio = ratio(ruleCardUnion, diagramRect || visualRect || stageRect);
          const ruleCardTopRatio = Number.isFinite(ruleCardTopInSvgRatio) ? ruleCardTopInSvgRatio : ruleCardUnion && (diagramRect || visualRect || stageRect)
            ? Math.max(0, Math.min(1, (ruleCardUnion.top - (diagramRect || visualRect || stageRect).top) / (diagramRect || visualRect || stageRect).height))
            : 0;
          const ruleCardTextPressureRatio = active ? Math.min(1, [...active.querySelectorAll("[data-rule-card] text")]
            .filter(visibleSvg)
            .map(rect)
            .filter(Boolean)
            .reduce((sum, item) => sum + ratio(item, diagramRect || visualRect || stageRect), 0)) : 0;
          const ruleCardPrimaryOverlap = intersects(ruleCardUnion, primaryObjectUnion, 4);
          const svgTextPressureRatio = active ? Math.min(1, [...active.querySelectorAll("[data-visible-node] text, [data-rule-card] text")]
            .filter(visibleSvg)
            .map(rect)
            .filter(Boolean)
            .reduce((sum, item) => sum + ratio(item, stageRect), 0)) : 0;
          const labelClearance = active ? (() => {
            const labels = [...active.querySelectorAll("[data-visible-node] text")]
              .filter((el) => !el.closest("[data-rule-card]"))
              .filter(visibleSvg)
              .map((el) => ({ label: (el.textContent || "").trim().slice(0, 18), rect: rect(el) }))
              .filter((item) => item.label && item.rect);
            let nearest = Infinity;
            let pair = "";
            for (let i = 0; i < labels.length; i += 1) {
              for (let j = i + 1; j < labels.length; j += 1) {
                const current = gap(labels[i].rect, labels[j].rect);
                if (current < nearest) {
                  nearest = current;
                  pair = labels[i].label + "<->" + labels[j].label;
                }
              }
            }
            return { nearest: Number.isFinite(nearest) ? nearest : 999, pair };
          })() : { nearest: 999, pair: "" };
          const visibleThresholdLines = active ? [...active.querySelectorAll("[data-threshold-line]")].filter(visibleHook).length : 0;
          const visibleRuleCards = active ? [...active.querySelectorAll("[data-rule-card]")].filter(visibleHook).length : 0;
          const visualSignatures = active ? [...active.querySelectorAll("[data-visual-signature]")].filter(visibleHook).map((el) => el.dataset.visualSignature || "").filter(Boolean) : [];
          const visibleSignatureParts = active ? [...active.querySelectorAll("[data-visual-signature-part]")].filter(visibleHook).length : 0;
          const sharedSwitchPathTextIssues = active ? (() => {
            const issues = [];
            const texts = [...active.querySelectorAll('[data-visible-node] text')].filter(visibleSvg);
            for (const path of [...active.querySelectorAll('[data-shared-switch-branch="1"]')].filter(visibleSvg)) {
              if (typeof path.getBBox !== "function") continue;
              const pb = path.getBBox();
              const zone = { x: pb.x - 4, y: pb.y - 4, width: pb.width + 8, height: pb.height + 8 };
              for (const text of texts) {
                if (typeof text.getBBox !== "function") continue;
                const label = (text.textContent || "").trim().slice(0, 18);
                if (!label) continue;
                const tb = text.getBBox();
                const overlap = tb.x < zone.x + zone.width && tb.x + tb.width > zone.x && tb.y < zone.y + zone.height && tb.y + tb.height > zone.y;
                if (overlap) issues.push(label);
              }
            }
            return [...new Set(issues)];
          })() : [];
          const layoutOverlapIssues = active ? (() => {
            const issues = [];
            const describe = (el, fallback) =>
              el?.getAttribute("data-layout-item") ||
              el?.getAttribute("data-layout-label") ||
              el?.getAttribute("data-layout-shape") ||
              fallback;
            const overlap = (a, b) => intersects(a.rect, b.rect, 0.5);
            const items = [...active.querySelectorAll("[data-layout-item]")]
              .filter(visibleSvg)
              .map((el, index) => ({ id: describe(el, "item" + index), rect: rect(el) }))
              .filter((item) => item.rect);
            const labels = [...active.querySelectorAll("[data-layout-label]")]
              .filter(visibleSvg)
              .map((el, index) => ({ id: describe(el, "label" + index), rect: rect(el) }))
              .filter((item) => item.rect);
            const shapes = [...active.querySelectorAll("[data-layout-shape]")]
              .filter(visibleSvg)
              .map((el, index) => ({ id: describe(el, "shape" + index), rect: rect(el) }))
              .filter((item) => item.rect);
            for (let i = 0; i < items.length; i += 1) {
              for (let j = i + 1; j < items.length; j += 1) {
                if (overlap(items[i], items[j])) issues.push("object:" + items[i].id + "<->" + items[j].id);
              }
            }
            for (let i = 0; i < labels.length; i += 1) {
              for (let j = i + 1; j < labels.length; j += 1) {
                if (overlap(labels[i], labels[j])) issues.push("label:" + labels[i].id + "<->" + labels[j].id);
              }
            }
            for (const label of labels) {
              for (const shape of shapes) {
                if (overlap(label, shape)) issues.push("label-image:" + label.id + "<->" + shape.id);
              }
            }
            return [...new Set(issues)].slice(0, 12);
          })() : [];
          const layoutItemCountIssues = active ? (() => {
            const count = [...active.querySelectorAll("[data-layout-item]")].filter(visibleSvg).length;
            return count > 0 && (count < 2 || count > 6) ? ["expected 2-6 marked domain items, got " + count] : [];
          })() : [];
        return {
          state: playerState,
          activeScenes: activeScenes.length,
          visibleNodes: active ? [...active.querySelectorAll("[data-visible-node]")].filter(visible).map((el) => el.dataset.visibleNode) : [],
          primitiveTraceCount: primitiveTrace.length,
          primitiveMissing,
          primitiveMetadataIssues,
          keycards: active ? [...active.querySelectorAll(".coach-card")].filter(visible).length : 0,
          caption: document.querySelector("[data-caption]")?.textContent?.trim() || "",
	          coachInViewport: inViewport(coachRect),
	          pillLabelIssues,
	          svgTextIssues,
	          svgBoardIssues,
	          challengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter(visible).length,
          enabledChallengeCtas: [...document.querySelectorAll("[data-challenge-cta]")].filter((el) => visible(el) && el.getAttribute("aria-disabled") !== "true").length,
          playerBlocks,
          askBlocks,
          centerPlayBlocks,
          captionCoachOverlap,
          offSceneVisible,
          sharedSwitchBranches,
          sharedSwitchDevices,
          visibleThresholdLines,
          visibleRuleCards,
          visualSignatures,
          visibleSignatureParts,
          visualAttentionRatio,
          textOverlayRatio,
          domainObjectCoverageRatio,
          primaryObjectCoverageRatio,
          blueprintSurfaceCoverageRatio,
          ruleCardAreaRatio,
          ruleCardTextPressureRatio,
          ruleCardTopRatio,
          ruleCardPrimaryOverlap,
          svgTextPressureRatio,
          labelClearance,
          sharedSwitchPathTextIssues,
          layoutOverlapIssues,
          layoutItemCountIssues
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
        if (expectedPrimitiveActions.length) {
          if (value.primitiveTraceCount !== expectedPrimitiveActions.length) {
            fail("runtime_primitive_step_sequence", `${label}: expected ${expectedPrimitiveActions.length} primitive step trace item(s), got ${value.primitiveTraceCount}`);
          } else {
            pass("runtime_primitive_step_sequence", `${label}: traced ${value.primitiveTraceCount} primitive step action(s)`);
          }
          if (value.primitiveMissing.length) {
            fail("runtime_primitive_step_consumption", `${label}: missing primitive step target(s) ${value.primitiveMissing.join(", ")}`);
          } else {
            pass("runtime_primitive_step_consumption", `${label}: primitive step action targets are consumed by DOM steps`);
          }
          if (value.primitiveMetadataIssues.length) {
            fail("runtime_primitive_step_metadata", `${label}: primitive step metadata incomplete ${value.primitiveMetadataIssues.join(", ")}`);
          } else {
            pass("runtime_primitive_step_metadata", `${label}: primitive step DOM exposes id/kind/domain object metadata`);
          }
        }
        if (value.keycards !== 1) fail("runtime_keycard_budget", `${label}: ${value.keycards} visible keycards`);
        else pass("runtime_keycard_budget", `${label}: one keycard`);
        if (!value.caption) fail("runtime_caption", `${label}: caption is empty`);
        else pass("runtime_caption", `${label}: caption visible`);
        if (requiresBlueprintReference && blueprintTeachingSceneIds.has(scene.id)) {
          const captionChars = charLength(value.caption);
          if (captionChars > maxCaptionChars) {
            fail("runtime_blueprint_caption_budget", `${label}: visible caption ${captionChars} chars > ${maxCaptionChars}`);
          } else {
            pass("runtime_blueprint_caption_budget", `${label}: visible caption ${captionChars}/${maxCaptionChars} chars`);
          }
          if (value.visibleThresholdLines < 1) {
            fail("runtime_blueprint_threshold_visible", `${label}: no visible threshold/boundary line`);
          } else {
            pass("runtime_blueprint_threshold_visible", `${label}: ${value.visibleThresholdLines} visible threshold/boundary line(s)`);
          }
          if (value.visibleRuleCards < 1) {
            fail("runtime_blueprint_rule_card_visible", `${label}: no visible bottom rule card`);
          } else {
            pass("runtime_blueprint_rule_card_visible", `${label}: ${value.visibleRuleCards} visible bottom rule card(s)`);
          }
          if (!value.visualSignatures.length) {
            fail("runtime_blueprint_visual_signature", `${label}: no visible visual signature hook`);
          } else {
            pass("runtime_blueprint_visual_signature", `${label}: ${[...new Set(value.visualSignatures)].join(",")}`);
          }
          if (value.visibleSignatureParts < 1) {
            fail("runtime_blueprint_signature_parts", `${label}: no visible signature-part hook`);
          } else {
            pass("runtime_blueprint_signature_parts", `${label}: ${value.visibleSignatureParts} visible signature part(s)`);
          }
          if (isBlueprintPoster) {
            if (value.visualAttentionRatio < minVisualAttentionRatio) {
              fail("runtime_blueprint_poster_visual_attention", `${label}: visual ratio ${value.visualAttentionRatio.toFixed(2)} < ${minVisualAttentionRatio}`);
            } else {
              pass("runtime_blueprint_poster_visual_attention", `${label}: visual ratio ${value.visualAttentionRatio.toFixed(2)} >= ${minVisualAttentionRatio}`);
            }
            if (value.textOverlayRatio > maxTextOverlayRatio) {
              fail("runtime_blueprint_poster_text_overlay", `${label}: text overlay ratio ${value.textOverlayRatio.toFixed(2)} > ${maxTextOverlayRatio}`);
            } else {
              pass("runtime_blueprint_poster_text_overlay", `${label}: text overlay ratio ${value.textOverlayRatio.toFixed(2)} <= ${maxTextOverlayRatio}`);
            }
            if (value.domainObjectCoverageRatio < minDomainObjectCoverageRatio) {
              fail("runtime_blueprint_domain_object_coverage", `${label}: domain object coverage ${value.domainObjectCoverageRatio.toFixed(2)} < ${minDomainObjectCoverageRatio}`);
            } else {
              pass("runtime_blueprint_domain_object_coverage", `${label}: domain object coverage ${value.domainObjectCoverageRatio.toFixed(2)} >= ${minDomainObjectCoverageRatio}`);
            }
            if (value.primaryObjectCoverageRatio < minPrimaryObjectCoverageRatio) {
              fail("runtime_blueprint_primary_object_coverage", `${label}: primary object coverage ${value.primaryObjectCoverageRatio.toFixed(2)} < ${minPrimaryObjectCoverageRatio}`);
            } else {
              pass("runtime_blueprint_primary_object_coverage", `${label}: primary object coverage ${value.primaryObjectCoverageRatio.toFixed(2)} >= ${minPrimaryObjectCoverageRatio}`);
            }
            if (value.blueprintSurfaceCoverageRatio < minBlueprintSurfaceCoverageRatio) {
              fail("runtime_blueprint_surface_coverage", `${label}: blueprint surface coverage ${value.blueprintSurfaceCoverageRatio.toFixed(2)} < ${minBlueprintSurfaceCoverageRatio}`);
            } else {
              pass("runtime_blueprint_surface_coverage", `${label}: blueprint surface coverage ${value.blueprintSurfaceCoverageRatio.toFixed(2)} >= ${minBlueprintSurfaceCoverageRatio}`);
            }
            if (value.visibleRuleCards !== 1) {
              fail("runtime_blueprint_rule_card_budget", `${label}: rule cards ${value.visibleRuleCards}, expected exactly 1`);
            } else if (value.ruleCardAreaRatio > maxRuleCardAreaRatio || value.ruleCardTextPressureRatio > maxRuleCardTextPressureRatio || value.ruleCardTopRatio < minRuleCardTopRatio || value.ruleCardPrimaryOverlap) {
              fail("runtime_blueprint_rule_card_budget", `${label}: count=1 area=${value.ruleCardAreaRatio.toFixed(2)} text=${value.ruleCardTextPressureRatio.toFixed(2)} top=${value.ruleCardTopRatio.toFixed(2)} overlap=${value.ruleCardPrimaryOverlap}`);
            } else {
              pass("runtime_blueprint_rule_card_budget", `${label}: count=1 area=${value.ruleCardAreaRatio.toFixed(2)}<=${maxRuleCardAreaRatio} text=${value.ruleCardTextPressureRatio.toFixed(2)}<=${maxRuleCardTextPressureRatio} top=${value.ruleCardTopRatio.toFixed(2)}>=${minRuleCardTopRatio}`);
            }
            if (value.svgTextPressureRatio > maxSvgTextPressureRatio) {
              fail("runtime_blueprint_svg_text_pressure", `${label}: SVG text pressure ${value.svgTextPressureRatio.toFixed(2)} > ${maxSvgTextPressureRatio}`);
            } else {
              pass("runtime_blueprint_svg_text_pressure", `${label}: SVG text pressure ${value.svgTextPressureRatio.toFixed(2)} <= ${maxSvgTextPressureRatio}`);
            }
            if (value.labelClearance.nearest < minLabelClearancePx) {
              fail("runtime_blueprint_label_clearance", `${label}: nearest label clearance ${value.labelClearance.nearest.toFixed(1)}px < ${minLabelClearancePx}px (${value.labelClearance.pair})`);
            } else {
              pass("runtime_blueprint_label_clearance", `${label}: nearest label clearance ${value.labelClearance.nearest.toFixed(1)}px >= ${minLabelClearancePx}px`);
            }
          }
        }
        if (!value.coachInViewport) fail("runtime_coach_in_view", `${label}: coach card is outside viewport`);
        else pass("runtime_coach_in_view", `${label}: coach card is inside viewport`);
        if (value.pillLabelIssues.length) fail("runtime_svg_label_fit", `${label}: pill labels too close to edge ${value.pillLabelIssues.join(", ")}`);
        else pass("runtime_svg_label_fit", `${label}: pill labels have safe padding`);
        if (value.svgTextIssues.length) fail("runtime_svg_text_collision", `${label}: svg text collision/line crowding ${value.svgTextIssues.join(", ")}`);
        else pass("runtime_svg_text_collision", `${label}: svg text avoids other labels and arrows`);
        if (value.layoutOverlapIssues.length) fail("runtime_domain_layout_overlap", `${label}: domain object/text overlap ${value.layoutOverlapIssues.join(", ")}`);
        else pass("runtime_domain_layout_overlap", `${label}: marked domain objects, labels, and images do not overlap`);
        if (value.layoutItemCountIssues.length) fail("runtime_domain_layout_item_count", `${label}: ${value.layoutItemCountIssues.join(", ")}`);
        else pass("runtime_domain_layout_item_count", `${label}: marked domain object count is correct when declared`);
        if (value.sharedSwitchPathTextIssues.length) fail("runtime_shared_switch_branch_label_clearance", `${label}: shared switch branch crosses label text ${value.sharedSwitchPathTextIssues.join(", ")}`);
        else pass("runtime_shared_switch_branch_label_clearance", `${label}: shared switch branches avoid label text`);
        if (value.svgBoardIssues.length) fail("runtime_svg_text_in_board", `${label}: svg text outside primary board ${value.svgBoardIssues.join(", ")}`);
        else pass("runtime_svg_text_in_board", `${label}: svg text stays inside primary board`);
        if (value.playerBlocks.length) fail("runtime_player_occlusion", `${label}: player overlaps ${value.playerBlocks.join(", ")}`);
        else pass("runtime_player_occlusion", `${label}: player does not cover protected content`);
        if (value.askBlocks.length) fail("runtime_ai_ask_occlusion", `${label}: AI ask entry overlaps ${value.askBlocks.join(", ")}`);
        else pass("runtime_ai_ask_occlusion", `${label}: AI ask entry does not cover protected content`);
        if (value.centerPlayBlocks.length) fail("runtime_center_play_occlusion", `${label}: center play overlays ${value.centerPlayBlocks.join(", ")}`);
        else pass("runtime_center_play_occlusion", `${label}: center play does not cover protected content`);
        if (value.captionCoachOverlap) fail("runtime_caption_coach_overlap", `${label}: caption overlaps coach card`);
        else pass("runtime_caption_coach_overlap", `${label}: caption avoids coach card`);
        if (value.offSceneVisible) fail("runtime_non_cumulative_seek", `${label}: ${value.offSceneVisible} off-scene visible nodes`);
        else pass("runtime_non_cumulative_seek", `${label}: off-scene nodes are not visible`);
        if (sceneHasSharedSwitch) {
          if (value.sharedSwitchBranches < 2 || value.sharedSwitchDevices < 2) {
            fail("runtime_shared_switch_domain_objects", `${label}: needs two visible branches and two visible devices, got branches=${value.sharedSwitchBranches}, devices=${value.sharedSwitchDevices}`);
          } else {
            pass("runtime_shared_switch_domain_objects", `${label}: shared switch shows two branches and two devices`);
          }
          const revealSamples = [0.42, 0.52, 0.62, 0.72].map((fraction) =>
            sceneStart + Math.max(0.25, Math.min(sceneDur - 0.15, sceneDur * fraction))
          );
          const revealValue = await evalValue(`
            (() => {
              const visible = (el) => {
                const cs = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return cs.display !== "none" && cs.visibility !== "hidden" && Number(cs.opacity || 1) > 0.05 && r.width > 1 && r.height > 1;
              };
              const visibleSvg = (el) => {
                if (!el) return false;
                let cur = el;
                while (cur && cur.nodeType === 1) {
                  const cs = getComputedStyle(cur);
                  if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity || 1) <= 0.05) return false;
                  cur = cur.parentElement;
                }
                const r = el.getBoundingClientRect();
                if (r.width > 1 && r.height > 1) return true;
                if (typeof el.getBBox === "function") {
                  const b = el.getBBox();
                  return b.width > 1 || b.height > 1;
                }
                return false;
              };
              return ${JSON.stringify(revealSamples)}.map((sampleT) => {
                window.__IR_PLAYER__.seek(sampleT);
                const active = document.querySelector(".scene.active");
                return {
                  t: sampleT,
                  branches: active ? [...active.querySelectorAll('[data-shared-switch-branch="1"]')].filter(visibleSvg).length : 0,
                  devices: active ? [...active.querySelectorAll('[data-shared-switch-device="1"]')].filter(visibleSvg).length : 0,
                };
              });
            })()
          `);
          const badReveal = Array.isArray(revealValue) ? revealValue.find((item) => item.branches > 0 && item.devices < 2) : null;
          if (badReveal) {
            fail("runtime_shared_switch_atomic_reveal", `${label}: branch appears before two devices at ${Number(badReveal.t).toFixed(2)}s`);
          } else {
            pass("runtime_shared_switch_atomic_reveal", `${label}: branch/device reveal is atomic across sampled frames`);
          }
        }
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
      (async () => {
        document.querySelector("[data-theater-toggle]")?.click();
        await new Promise((resolve) => setTimeout(resolve, 80));
        const lesson = document.querySelector(".lesson");
        const controlsShown = lesson?.classList.contains("controls-visible") || false;
        if (${isBlueprintPoster ? "true" : "false"}) {
          lesson?.classList.remove("controls-visible");
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
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
          theater: lesson?.classList.contains("theater"),
          controlsVisible: controlsShown,
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
      if (isBlueprintPoster) {
        const widthRatio = theater.stageRect ? theater.stageRect.width / theater.viewport.width : 0;
        const heightRatio = theater.stageRect ? theater.stageRect.height / theater.viewport.height : 0;
        if (widthRatio < 0.95 || heightRatio < 0.95) {
          fail("runtime_blueprint_theater_stage_coverage", `${viewport.name}: theater clean stage ${widthRatio.toFixed(2)}x${heightRatio.toFixed(2)} of viewport`);
        } else {
          pass("runtime_blueprint_theater_stage_coverage", `${viewport.name}: theater clean stage covers ${widthRatio.toFixed(2)}x${heightRatio.toFixed(2)} of viewport`);
        }
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
