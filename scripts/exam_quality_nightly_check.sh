#!/usr/bin/env bash
#
# Nightly closed-book exam-quality regression check (eval 观测 north-star B, Phase 1).
#
# Runs the PRODUCTION model closed-book against the 337-MCQ ground-truth past-exam bank
# inside the deeptutor container, compares the accuracy to a floor, and:
#   - always appends the run to a history log (accuracy trend over time);
#   - on regression (accuracy < floor) POSTs an alert to Alertmanager → email, reusing the
#     same observability delivery pipe as infra alerts (single alert authority);
#   - if the eval itself fails to produce a number, alerts too (a broken quality check is a
#     blind spot, not a silent pass).
#
# Runs on the HOST via crontab (orchestration = host bash + curl); the eval itself runs in
# the container (python 3.11 — the host python is 3.6.8 and cannot import the eval).
#
# Baseline established 2026-07-04: dashscope:deepseek-v4-flash = 0.8635 (291/337).
# Floor 0.81 ≈ baseline − 5pp. Override any of these via env.
#
#   crontab:  0 4 * * *  /root/deeptutor/scripts/exam_quality_nightly_check.sh >> \
#               /root/deeptutor/data/runtime/observability/exam_quality_cron.out 2>&1
#
# NOTE (Phase 2, rides next deeptutor image rebuild): also export accuracy as a Prometheus
# gauge (deeptutor_exam_quality_accuracy) via the app /metrics endpoint + a rule-based alert
# + staleness alert, for at-a-glance dashboards. Until then this cron IS the live signal.

set -Eeuo pipefail

MODEL="${EXAM_QUALITY_MODEL:-dashscope:deepseek-v4-flash}"
FLOOR="${EXAM_QUALITY_FLOOR:-0.81}"
BASELINE="${EXAM_QUALITY_BASELINE:-0.8635}"
CONTAINER="${DEEPTUTOR_CONTAINER:-deeptutor}"
ALERTMANAGER_URL="${ALERTMANAGER_URL:-http://127.0.0.1:9093}"
HISTORY_LOG="${EXAM_QUALITY_LOG:-/root/deeptutor/data/runtime/observability/exam_quality_history.log}"

ts="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
mkdir -p "$(dirname "$HISTORY_LOG")"

post_alert() {
    # $1=alertname $2=summary $3=description
    curl -s -XPOST "${ALERTMANAGER_URL}/api/v2/alerts" \
        -H 'Content-Type: application/json' \
        -d "[{\"labels\":{\"alertname\":\"$1\",\"severity\":\"critical\",\"job\":\"exam_quality\"},\"annotations\":{\"summary\":\"$2\",\"description\":\"$3\"},\"startsAt\":\"${ts}\"}]" \
        >/dev/null || true
}

# Run the eval in the container; capture output (never abort the script on eval non-zero —
# we want to detect and alert on a broken check rather than crash silently).
out="$(docker exec "${CONTAINER}" python -m deeptutor.services.benchmark.exam_quality_eval "${MODEL}" 2>&1 || true)"
acc="$(printf '%s\n' "${out}" | grep -oE 'accuracy=[0-9.]+' | head -1 | cut -d= -f2 || true)"

if [ -z "${acc}" ]; then
    printf '%s\tmodel=%s\taccuracy=ERROR\tfloor=%s\n' "${ts}" "${MODEL}" "${FLOOR}" >> "${HISTORY_LOG}"
    post_alert "ExamQualityCheckBroken" \
        "考试质量夜检无法产出准确率" \
        "model=${MODEL} 的 closed-book eval 未产出 accuracy — 质量监测本身瞎了, 需排查 (keys/网络/模型)."
    echo "exam-quality nightly: ERROR (no accuracy produced)"
    exit 1
fi

printf '%s\tmodel=%s\taccuracy=%s\tfloor=%s\tbaseline=%s\n' \
    "${ts}" "${MODEL}" "${acc}" "${FLOOR}" "${BASELINE}" >> "${HISTORY_LOG}"

below="$(awk -v a="${acc}" -v f="${FLOOR}" 'BEGIN{print (a+0 < f+0) ? 1 : 0}')"
if [ "${below}" = "1" ]; then
    post_alert "ExamQualityRegression" \
        "考试质量准确率跌破地板 (AI 可能变笨)" \
        "model=${MODEL} accuracy=${acc} < floor=${FLOOR} (baseline=${BASELINE}). 对 337 道真题的 closed-book 准确率下降, 请排查 prompt/模型/检索改动."
    echo "exam-quality nightly: REGRESSION accuracy=${acc} < floor=${FLOOR} (alert sent)"
    exit 0
fi

echo "exam-quality nightly: OK accuracy=${acc} (>= floor=${FLOOR})"
