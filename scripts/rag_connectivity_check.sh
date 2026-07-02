#!/usr/bin/env bash
# RAG 连通性自检 — 验证主 KB(kb_chunks)和 SUPABASE_URL 指向同一个有数据的项目。
# 用途: 上线前 / KB 迁移前确认 RAG 不是哑的。只读, 不改任何数据。
#
# 用法:
#   scripts/rag_connectivity_check.sh                 # 读本地 .env
#   SUPABASE_URL=... SUPABASE_KEY=... scripts/rag_connectivity_check.sh   # 显式覆盖(测生产配置)
set -uo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] && { set -a; source .env; set +a; }

PSQL="$(command -v /opt/homebrew/opt/libpq/bin/psql || command -v psql)"
KEY="${SUPABASE_SERVICE_ROLE_KEY:-${SUPABASE_KEY:-}}"
URL="${SUPABASE_URL:-}"
fail=0

ref_of_url()  { sed -E 's#https://([^.]+)\..*#\1#' <<<"$1"; }
ref_of_pg()   { sed -E 's#.*://[^.]*\.([^:@]+).*#\1#; t; s#.*://postgres\.([^:]+):.*#\1#' <<<"$1"; }

echo "================ 1. 配置指向的项目 ref ================"
printf "SUPABASE_URL  -> %s\n" "$(ref_of_url "$URL")"
printf "DB_URL(主KB)  -> %s\n" "$(sed -E 's#.*://([^:]+):.*#\1#' <<<"${DB_URL:-}")"

echo ""
echo "================ 2. PostgREST 能否查到 kb_chunks ================"
if [[ -z "$URL" || -z "$KEY" ]]; then
  echo "!! SUPABASE_URL 或 KEY 缺失, 跳过 REST 检查"; fail=1
else
  # HEAD + Prefer count, 只取行数, 不拉数据
  cnt=$(curl -s -I -X HEAD \
    "$URL/rest/v1/kb_chunks?select=id" \
    -H "apikey: $KEY" -H "Authorization: Bearer $KEY" \
    -H "Range: 0-0" -H "Prefer: count=exact" 2>/dev/null \
    | tr -d '\r' | sed -nE 's#content-range: .*/([0-9]+)#\1#Ip')
  if [[ -n "$cnt" ]]; then
    echo "✅ SUPABASE_URL 项目可查到 kb_chunks, 共 $cnt 行"
    [[ "$cnt" == "0" ]] && { echo "   ⚠️ 但行数为 0 — RAG 会返回空!"; fail=1; }
  else
    echo "❌ SUPABASE_URL 项目查不到 kb_chunks(表不存在 / 连错项目 / KEY 无权)"; fail=1
  fi
fi

echo ""
echo "================ 3. 直连 DB_URL 的真实 kb_chunks 行数(基准真相) ================"
if [[ -n "${DB_URL:-}" ]]; then
  real=$("$PSQL" "${DB_URL/:6543/:5432}" -t -A -c \
    "SELECT count(*), count(embedding) FROM kb_chunks;" 2>/dev/null)
  echo "DB_URL 项目 kb_chunks: ${real:-查询失败}  (总数|有向量)"
fi

echo ""
echo "================ 4. 裁决 ================"
if [[ "$fail" == "0" ]]; then
  echo "✅ RAG 连通正常: SUPABASE_URL 指向的项目有 kb_chunks 数据"
else
  echo "❌ RAG 连通异常: SUPABASE_URL 与主 KB 数据可能不在同一项目, 或 RAG 会返回空。"
  echo "   修复: 把 SUPABASE_URL/SUPABASE_KEY 指向 DB_URL 所在项目, 再重跑本脚本。"
fi
exit "$fail"
