#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://test2.yousenjiaoyu.com}"
BACKUP_KEEP="${BACKUP_KEEP:-2}"
READINESS_CHANGED_ARGS=""
FAST_RELOAD_BLOCKED_PATTERN='^(Dockerfile|docker-compose\.yml|deployment/aliyun/|requirements(/|\.txt$)|requirements\.txt$|pyproject\.toml$|web/|package(-lock)?\.json$|wx_miniprogram/|yousenwebview/)'
while IFS= read -r changed_file; do
  [ -n "${changed_file}" ] || continue
  if printf "%s\n" "${changed_file}" | grep -Eq "${FAST_RELOAD_BLOCKED_PATTERN}"; then
    echo "快速发布拒绝: ${changed_file} 需要镜像/前端/依赖重建，请改用 scripts/deploy_aliyun.sh。" >&2
    exit 1
  fi
  READINESS_CHANGED_ARGS+=" --changed-file $(printf "%q" "${changed_file}")"
done < <(git show --pretty= --name-only --first-parent HEAD)

echo "执行阿里云快速发布: sync + no-build container refresh + restart"
echo "适合 Python 后端 / Prompt / YAML / TutorBot skill 资产改动；若改了 Dockerfile、requirements、前端构建产物，请改用 deploy_aliyun.sh"

# 部署前磁盘预检（本脚本会 docker build + 建 release 快照 + 数据备份,需要数 GB 空闲;
# 盘满到 0 会让容器写不了 /tmp 崩溃成 502,见 docs/zh/guide/aliyun-deploy.md §16）。
DISK_PREFLIGHT_MIN_GB="${DISK_PREFLIGHT_MIN_GB:-6}"
avail_gb="$(ssh "${REMOTE_HOST}" "df -BG --output=avail / | tail -1 | tr -dc '0-9'" 2>/dev/null || echo 0)"
if [ -n "${avail_gb}" ] && [ "${avail_gb}" -lt "${DISK_PREFLIGHT_MIN_GB}" ]; then
  echo "磁盘预检失败：远端根盘仅剩 ${avail_gb}G（< ${DISK_PREFLIGHT_MIN_GB}G）。" >&2
  echo "  本次发布会 docker build + 备份,继续会撑爆盘致 502。请先腾空间：" >&2
  echo "  ssh ${REMOTE_HOST} 'docker builder prune -af && docker image prune -af'" >&2
  echo "  （绝不要删 langfuse 数据卷；详见 docs/zh/guide/aliyun-deploy.md §16。确认空间后用 DISK_PREFLIGHT_MIN_GB=0 跳过本检查）" >&2
  exit 1
fi
echo "磁盘预检通过：远端根盘剩 ${avail_gb}G。"

"${SCRIPT_DIR}/sync_to_aliyun.sh" once
"${SCRIPT_DIR}/validate_aliyun_release_env.sh"
echo "执行远端运行态备份，作为本次快速发布的回滚基线..."
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && python3 scripts/backup_data.py --project-root '${REMOTE_DIR}' --keep '${BACKUP_KEEP}'"
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' bash scripts/server_fast_reload_aliyun.sh"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
bash "${SCRIPT_DIR}/verify_aliyun_observability.sh"

# 把一条 readiness 证据写进运行时 control_plane,让 launch_readiness 不再恒 NOT_RUN。
# 运行时 control_plane 在容器 /app/tmp 下；host python 可能过旧，不能作为脚本解释器 authority。
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && docker compose exec -T deeptutor python scripts/run_readiness_check.py --check-id contract_guard --report-only${READINESS_CHANGED_ARGS}" \
  || echo "readiness check non-fatal"

# observe-only: 部署后跑控制面 shadow 测量，把"单一权威是否被违反"打印到部署日志（这是
# 既有 SSH hook 的复用，不新建 Aliyun crontab）。退出码 0=clean / 1=有 compat·fabricate 生产
# 命中需排查 / 2=窗口未累积满。数据底座 TurnEventLog 已收口到持久挂载卷（data/runtime/
# observability），7 天窗不再每次部署清零，故此测量从此能真正累积。non-fatal。
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && docker compose exec -T deeptutor python scripts/report_control_plane_shadow_hits.py --days 7" \
  && echo "control-plane shadow: clean（单一权威无 compat/fabricate 生产命中）" \
  || echo "control-plane shadow: 退出码非 0（1=有命中需排查 / 2=窗口未累积满，observe-only non-fatal）"

# 发布后清 build cache（治本：本脚本经 server_fast_reload 每次都 `docker compose build`，
# 生成 GB 级 build cache 层且从不自动清，多次发布累积到撑爆 99G 盘 → 容器写不了 /tmp 崩 → 502。
# 详见 docs/zh/guide/aliyun-deploy.md §16。只清未用缓存,绝不碰 Langfuse 业务数据卷。non-fatal。
echo "清理本次发布产生的 docker build cache（防磁盘累积爆盘，见 aliyun-deploy.md §16）..."
ssh "${REMOTE_HOST}" "docker builder prune -f >/dev/null 2>&1 && df -h / | tail -1" \
  || echo "build cache 清理 non-fatal（手动 docker builder prune -af 兜底）"
