#!/bin/bash
# run_local_scheduled.sh — 本地 macOS launchd 定时跑 accuracy_gate 的 wrapper(持续质量飞轮 V2).
#
# 为什么是本地 launchd 而不是 GitHub Actions cron:
#   SHA 门要 ssh 到阿里云读 host .env / container env, 不想把生产 SSH 私钥放进 CI.
#   所以调度器留在本机(有 ~/.ssh/aliyun_ecs_2 + Aliyun-ECS-2 别名), 跑同一个
#   scheduled_run.py. 将来 CI 具备安全私钥注入后可切回 Actions(见 README 迁移说明).
#
# 红线(自动化绝不放大假绿 —— 与 accuracy_gate 的反自证地基一致):
#   - 只跑 eval + 落报告/metrics/日志; 绝不自动盖 GO / 绝不 ship 生产 / 绝不改代码 / 绝不 git add.
#   - SHA 门不齐 -> scheduled_run.py 自己 exit 2 skip(不花钱); 本 wrapper 只记日志.
#   - BLOCK(exit 3) 只记日志 + 可选本地弹窗提醒; 绝不自动修(治本设计人在环).
#   - 幂等 + 不常驻: launchd 用 StartCalendarInterval 定点触发, 跑完即退, 无后台进程.
#
# 退出码透传 scheduled_run.py(单一口径):
#   0 WEAK-GO(结构判定, 待人盖封板) | 2 SHA skip | 3 BLOCK | 4 无法判定.
set -uo pipefail

# --- launchd 环境自包含(launchd 不加载 shell profile, PATH/HOME 极简) ---
export HOME="${HOME:-/Users/yehongchen}"
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
# pyenv shims 必须在 PATH: scheduled_run 及其子探针都用裸 `python` 调用.
# /usr/bin 提供 ssh/git; /opt/homebrew/bin 兜底.
export PATH="$PYENV_ROOT/shims:$PYENV_ROOT/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# --- 定位仓库根(脚本在 scripts/quality_gate/ 下) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT" || { echo "FATAL: 无法 cd 到 $REPO_ROOT" >&2; exit 4; }

RUNS="${ACCURACY_GATE_RUNS:-3}"
LOG_DIR="$REPO_ROOT/artifacts/quality_gate/scheduled"
CRON_LOG="$LOG_DIR/cron.log"
mkdir -p "$LOG_DIR"

TS="$(date '+%Y-%m-%d %H:%M:%S')"

# --- 注入 .env + QA 凭证(与手动跑口径一致) ---
if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "[$TS] FATAL: 缺 .env, 跳过本次调度" | tee -a "$CRON_LOG"
  exit 4
fi
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a
export DEEPTUTOR_QA_USERNAME="${WECHAT_QA_USERNAME:-}"
export DEEPTUTOR_QA_PASSWORD="${WECHAT_QA_PASSWORD:-}"
# 强制 test2 部署, 绝不用 .env 里的 dev 127.0.0.1.
export DEEPTUTOR_QA_BASE_URL="https://test2.yousenjiaoyu.com"

echo "[$TS] ===== accuracy_gate 调度开始 (runs=$RUNS, base=$DEEPTUTOR_QA_BASE_URL) =====" | tee -a "$CRON_LOG"

# --- 跑门(判定逻辑单一权威在 scheduled_run.py -> accuracy_gate.py, 本 wrapper 不重复) ---
python "$SCRIPT_DIR/scheduled_run.py" --runs "$RUNS" >>"$CRON_LOG" 2>&1
CODE=$?

TS_END="$(date '+%Y-%m-%d %H:%M:%S')"
case "$CODE" in
  0) VERDICT="WEAK-GO(结构判定, 待人盖封板)";;
  2) VERDICT="SKIP(SHA 门不齐, 未花钱)";;
  3) VERDICT="BLOCK(某维复现, 需人工核 evidence 治本)";;
  4) VERDICT="INCONCLUSIVE(登录失败/全降级, 非内容失败)";;
  *) VERDICT="UNKNOWN(exit=$CODE)";;
esac
echo "[$TS_END] ===== 调度结束 exit=$CODE -> $VERDICT =====" | tee -a "$CRON_LOG"

# --- BLOCK 可选本地提醒(best-effort, 失败不影响退出码); 绝不自动修 ---
if [ "$CODE" = "3" ]; then
  /usr/bin/osascript -e 'display notification "accuracy_gate 某维复现 BLOCK, 需人工核 evidence" with title "DeepTutor 质量门"' 2>/dev/null || true
fi

exit "$CODE"
