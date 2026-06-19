#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DIR="$ROOT/artifacts/luban_case_family_assets/diagram_microlesson"
CARD="${1:-J01}"

case "$CARD" in
  J01|M_danger_work_expert_argumentation)
    MASTER="$DIR/M_danger_work_expert_argumentation.master.json"
    LESSON="$DIR/J01_danger_work_expert_argumentation.lesson.json"
    TIMING="$DIR/J01_danger_work_expert_argumentation.lesson.timing.json"
    RENDERED="$DIR/M_danger_work_expert_argumentation.journey.html"
    PRACTICE="$DIR/M_danger_work_expert_argumentation.practice.html"
    ;;
  *)
    echo "usage: $0 J01" >&2
    echo "unknown card: $CARD" >&2
    exit 2
    ;;
esac

STAMP="$(date +%Y%m%d-%H%M%S)-$$"
REPORT_DIR="$DIR/reports/J01/$STAMP"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/gate.md"
MANIFEST="$REPORT_DIR/card_bundle_manifest.json"

log() {
  printf '%s\n' "$*" | tee -a "$REPORT"
}

run_gate() {
  local name="$1"
  shift
  log ""
  log "## $name"
  log '```text'
  set +e
  "$@" 2>&1 | tee -a "$REPORT"
  local status=${PIPESTATUS[0]}
  set -e
  log '```'
  if [[ $status -ne 0 ]]; then
    log ""
    log "**FAIL:** $name exited $status"
    exit "$status"
  fi
}

cat > "$REPORT" <<EOF
# J01 Diagram Microlesson Gate

- card: J01
- generated_at: $STAMP
- rendered: $RENDERED
- practice: $PRACTICE
- manifest: $MANIFEST
- note: preview gate does not generate MP4. This gate covers current journey HTML + independent practice HTML deterministic path.
EOF

run_gate "schema spine" python "$DIR/validate_schema_drafts.py"
run_gate "animation_action schema" python "$DIR/validate_animation_action_schema.py" --require-actions "$LESSON"
run_gate "timing sync" node "$DIR/validate_timing_sync.mjs" "$TIMING" --max 151
run_gate "render journey" python "$DIR/render_archetype_journey.py" "$MASTER"
run_gate "render practice" python "$DIR/render_archetype_practice.py" "$MASTER"
run_gate "data-id targets" node "$DIR/validate_data_id_targets.mjs" "$MASTER" "$RENDERED"
run_gate "learning stage runtime" node "$DIR/validate_learning_stage_runtime.mjs" "$RENDERED"
run_gate "practice preview" node "$DIR/validate_video_first_preview.mjs" "$RENDERED" "$PRACTICE"
run_gate "bundle manifest" python "$DIR/build_card_bundle_manifest.py" "$MASTER" --rendered "$RENDERED" --out "$MANIFEST" --require-practice

log ""
log "## Result"
log "PASS deterministic J01 journey gates."
echo "gate report: $REPORT"
