#!/usr/bin/env bash
# Round 5 Stage 1 — 半自动化手动测试脚本
#
# 适用：BI v2 PR #19 合并 main 并部署到阿里云后，验证后端契约 (3.6 / 3.7 / 3.8)
# 的脚本部分。其余 (3.1-3.5, 3.9-3.11) 仍需在浏览器手动跑。
#
# 用法（在阿里云 SSH 内）：
#   bash docs/zh/bi/bi-v2-stage1-manual-test-runner.sh \
#       <ADMIN_TOKEN_A> <ADMIN_TOKEN_B> <USER_ID> <SESSION_ID>
#
# 期望：所有 step 都 PASS。任何 FAIL 立即记录到
# docs/zh/bi/bi-v2-stage1-debrief-$(date +%F).md。

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:3001}"
ADMIN_TOKEN_A="${1:-}"
ADMIN_TOKEN_B="${2:-}"
USER_ID="${3:-}"
SESSION_ID="${4:-}"

if [[ -z "$ADMIN_TOKEN_A" || -z "$ADMIN_TOKEN_B" || -z "$USER_ID" || -z "$SESSION_ID" ]]; then
  echo "Usage: $0 <ADMIN_TOKEN_A> <ADMIN_TOKEN_B> <USER_ID> <SESSION_ID>"
  echo
  echo "需要两个不同的 BI admin token + 一个真实会员 user_id + 一个该会员的真实 session_id"
  echo "(从 ops audit panel 或 supabase 查 session_store 拿)"
  exit 2
fi

PASS=0
FAIL=0

check() {
  local name="$1"
  local actual_status="$2"
  local expected_status="$3"
  local extra="${4:-}"
  if [[ "$actual_status" == "$expected_status" ]]; then
    echo "  PASS  $name  → HTTP $actual_status  $extra"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name  → HTTP $actual_status, expected $expected_status  $extra"
    FAIL=$((FAIL + 1))
  fi
}

URL="${BASE_URL}/api/v1/member/${USER_ID}/conversations/${SESSION_ID}/view-audit"

echo "============================================================"
echo "Step 3.7 — X-Idempotency-Key 格式守护"
echo "============================================================"

# 3.7a 缺 header
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  "${URL}")
check "缺 X-Idempotency-Key 应 400" "$status" "400"

# 3.7b 含 ':' 分隔符注入
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: with:colon" \
  "${URL}")
check "含 ':' 应 400 (分隔符注入)" "$status" "400"

# 3.7c 超长 (129 chars)
long_key=$(printf 'x%.0s' {1..129})
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: $long_key" \
  "${URL}")
check "超过 128 字符应 400" "$status" "400"

# 3.7d 含空格
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: has spaces" \
  "${URL}")
check "含空格应 400" "$status" "400"

# 3.7e 合法 UUID 风格
valid_key="test-stage1-$(date +%s)-$$-001"
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: $valid_key" \
  "${URL}")
check "合法 UUID 风格 key 应 200" "$status" "200" "(key=$valid_key)"

echo
echo "============================================================"
echo "Step 3.6 — Idempotency 真去重"
echo "============================================================"

dedup_key="test-stage1-dedup-$(date +%s)-$$"

# 第一次
resp1=$(curl -s -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: $dedup_key" \
  "${URL}")
audit_id_1=$(echo "$resp1" | python3 -c "import json,sys; print(json.load(sys.stdin).get('audit_id', ''))" 2>/dev/null)
deduped_1=$(echo "$resp1" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deduped', False))" 2>/dev/null)

echo "  第一次: audit_id=$audit_id_1  deduped=$deduped_1"

# 第二次同 key
resp2=$(curl -s -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: $dedup_key" \
  "${URL}")
audit_id_2=$(echo "$resp2" | python3 -c "import json,sys; print(json.load(sys.stdin).get('audit_id', ''))" 2>/dev/null)
deduped_2=$(echo "$resp2" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deduped', False))" 2>/dev/null)

echo "  第二次: audit_id=$audit_id_2  deduped=$deduped_2"

if [[ -n "$audit_id_1" && "$audit_id_1" == "$audit_id_2" && "$deduped_2" == "True" ]]; then
  echo "  PASS  同 key 重复请求返回同 audit_id + deduped=True"
  PASS=$((PASS + 1))
else
  echo "  FAIL  dedup 失败：第一次 audit_id=$audit_id_1，第二次 audit_id=$audit_id_2，deduped=$deduped_2"
  FAIL=$((FAIL + 1))
fi

echo
echo "============================================================"
echo "Step 3.8 — Operator binding (跨 admin 不互相 dedupe)"
echo "============================================================"

cross_key="test-stage1-cross-$(date +%s)-$$"

# Admin A 用 cross_key
respA=$(curl -s -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_A}" \
  -H "X-Idempotency-Key: $cross_key" \
  "${URL}")
audit_a=$(echo "$respA" | python3 -c "import json,sys; print(json.load(sys.stdin).get('audit_id', ''))" 2>/dev/null)

# Admin B 用同 cross_key
respB=$(curl -s -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN_B}" \
  -H "X-Idempotency-Key: $cross_key" \
  "${URL}")
audit_b=$(echo "$respB" | python3 -c "import json,sys; print(json.load(sys.stdin).get('audit_id', ''))" 2>/dev/null)
deduped_b=$(echo "$respB" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deduped', False))" 2>/dev/null)

echo "  Admin A: audit_id=$audit_a"
echo "  Admin B (同 key 不同 admin): audit_id=$audit_b deduped=$deduped_b"

if [[ -n "$audit_a" && -n "$audit_b" && "$audit_a" != "$audit_b" && "$deduped_b" != "True" ]]; then
  echo "  PASS  跨 admin 同 key 不被 dedupe (operator binding 生效)"
  PASS=$((PASS + 1))
else
  echo "  FAIL  跨 admin 被 dedupe (B2 漏洞复活)"
  FAIL=$((FAIL + 1))
fi

echo
echo "============================================================"
echo "汇总: $PASS PASS / $FAIL FAIL"
echo "============================================================"

if [[ "$FAIL" -gt 0 ]]; then
  echo "请将本次输出粘到 docs/zh/bi/bi-v2-stage1-debrief-$(date +%F).md"
  exit 1
fi
