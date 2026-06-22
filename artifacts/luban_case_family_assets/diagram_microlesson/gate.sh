#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DIR="$ROOT/artifacts/luban_case_family_assets/diagram_microlesson"
CARD="${1:-J01}"

case "$CARD" in
  J01|M_danger_work_expert_argumentation)
    CARD_ID="J01"
    MASTER="$DIR/M_danger_work_expert_argumentation.master.json"
    LESSON="$DIR/J01_danger_work_expert_argumentation.lesson.json"
    TIMING="$DIR/J01_danger_work_expert_argumentation.lesson.timing.json"
    RENDERED="$DIR/M_danger_work_expert_argumentation.journey.html"
    PRACTICE="$DIR/M_danger_work_expert_argumentation.practice.html"
    ;;
  Q02|Q02_dtjnt)
    CARD_ID="Q02"
    MASTER="$DIR/Q02_dtjnt.master.json"
    LESSON="$DIR/Q02_dtjnt.lesson.json"
    TIMING="$DIR/Q02_dtjnt.lesson.timing.json"
    RENDERED="$DIR/Q02_dtjnt.journey.html"
    PRACTICE="$DIR/Q02_dtjnt.practice.html"
    ;;
  S06|S06_gcfh)
    CARD_ID="S06"
    MASTER="$DIR/S06_gcfh.master.json"
    LESSON="$DIR/S06_gcfh.lesson.json"
    TIMING="$DIR/S06_gcfh.lesson.timing.json"
    RENDERED="$DIR/S06_gcfh.journey.html"
    PRACTICE="$DIR/S06_gcfh.practice.html"
    ;;
  S02|S02_qzdz)
    CARD_ID="S02"
    MASTER="$DIR/S02_qzdz.master.json"
    LESSON="$DIR/S02_qzdz.lesson.json"
    TIMING="$DIR/S02_qzdz.lesson.timing.json"
    RENDERED="$DIR/S02_qzdz.journey.html"
    PRACTICE="$DIR/S02_qzdz.practice.html"
    ;;
  C04|C04_mbcc)
    CARD_ID="C04"
    MASTER="$DIR/C04_mbcc.master.json"
    LESSON="$DIR/C04_mbcc.lesson.json"
    TIMING="$DIR/C04_mbcc.lesson.timing.json"
    RENDERED="$DIR/C04_mbcc.journey.html"
    PRACTICE="$DIR/C04_mbcc.practice.html"
    ;;
  A01|A01_jypc)
    CARD_ID="A01"
    MASTER="$DIR/A01_jypc.master.json"
    LESSON="$DIR/A01_jypc.lesson.json"
    TIMING="$DIR/A01_jypc.lesson.timing.json"
    RENDERED="$DIR/A01_jypc.journey.html"
    PRACTICE="$DIR/A01_jypc.practice.html"
    ;;
  Q01|Q01_yhlf)
    CARD_ID="Q01"
    MASTER="$DIR/Q01_yhlf.master.json"
    LESSON="$DIR/Q01_yhlf.lesson.json"
    TIMING="$DIR/Q01_yhlf.lesson.timing.json"
    RENDERED="$DIR/Q01_yhlf.journey.html"
    PRACTICE="$DIR/Q01_yhlf.practice.html"
    ;;
  C05|C05_gjlj)
    CARD_ID="C05"
    MASTER="$DIR/C05_gjlj.master.json"
    LESSON="$DIR/C05_gjlj.lesson.json"
    TIMING="$DIR/C05_gjlj.lesson.timing.json"
    RENDERED="$DIR/C05_gjlj.journey.html"
    PRACTICE="$DIR/C05_gjlj.practice.html"
    ;;
  C02|C02_jdk)
    CARD_ID="C02"
    MASTER="$DIR/C02_jdk.master.json"
    LESSON="$DIR/C02_jdk.lesson.json"
    TIMING="$DIR/C02_jdk.lesson.timing.json"
    RENDERED="$DIR/C02_jdk.journey.html"
    PRACTICE="$DIR/C02_jdk.practice.html"
    ;;
  K01|K01_sp)
    CARD_ID="K01"
    MASTER="$DIR/K01_sp.master.json"
    LESSON="$DIR/K01_sp.lesson.json"
    TIMING="$DIR/K01_sp.lesson.timing.json"
    RENDERED="$DIR/K01_sp.journey.html"
    PRACTICE="$DIR/K01_sp.practice.html"
    ;;
  *)
    echo "usage: $0 J01|Q02|S06|S02|C04|C05|A01|Q01|C02|K01" >&2
    echo "unknown card: $CARD" >&2
    exit 2
    ;;
esac

STAMP="$(date +%Y%m%d-%H%M%S)-$$"
REPORT_DIR="$DIR/reports/$CARD_ID/$STAMP"
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
# $CARD_ID Diagram Microlesson Gate

- card: $CARD_ID
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
log "PASS deterministic $CARD_ID journey gates."
echo "gate report: $REPORT"
