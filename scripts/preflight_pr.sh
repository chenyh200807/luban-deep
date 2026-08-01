#!/usr/bin/env bash
#
# preflight_pr.sh —— 开 PR 前的本地三检（一条命令，非零即红）
#
# 为什么存在：这三项是 CI 上最常见、最容易在本地漏掉、且失败后返工代价最高的闸。
# 它们分散在 .github/workflows/tests.yml 的不同 step 里，本地想复现要拼三条形状
# 各异的命令（还得自己算 base sha），实测代价 = 推上去等 CI 红了再修一轮。
#
#   ① detect-secrets       —— 明文密钥进仓（CI 上 BLOCKING；本地 pre-commit hook 可绕过）
#   ② contracts 双拷贝      —— AGENTS.md §Hard Invariants：contracts/index.yaml 与
#                              deeptutor/contracts/index.yaml（packaged runtime copy）必须一致
#   ③ env / schema registry —— register-before-use：新 env/flag、新 schema id 未登记即红
#
# 本脚本**不是第二权威**：三项全部转调既有的单一权威脚本
# （scripts/ci/tests_workflow_scope.py / scripts/check_env_registry.py /
#  scripts/check_schema_registry.py），只做"一键跑 + 失败时打印修复配方"。
# 判据与 CI 同源。**本地绿 ≠ CI 全绿**（CI 还跑单测、contract guard、db/provider/process
# registry、路由 smoke…）；但本地红 = CI 一定红。
#
# 用法：
#   scripts/preflight_pr.sh                # 对 origin/main 的 merge-base 检查
#   scripts/preflight_pr.sh --base <ref>   # 换基准分支（默认 origin/main）
#   PREFLIGHT_BASE=upstream/main scripts/preflight_pr.sh
#
# 退出码：0 = 三检全过；1 = 至少一项失败（每项失败都会打印修复配方）。
#
# 有意 fail-closed：扫描器缺失 = 失败，不是跳过。"工具没装所以这项没跑"在输出里
# 长得和"这项通过了"一模一样，那正是假绿的来源。
#
# 兼容性：只用 bash 3.2 特性（macOS 自带就是 3.2）——不用 heredoc-in-$()、不用
# ${arr[@]} 展开空数组，否则在 owner 的 Mac 上直接 syntax error。

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "preflight: 不在 git 仓库里，退出。" >&2
  exit 1
}
cd "$REPO_ROOT" || exit 1

BASE_REF="${PREFLIGHT_BASE:-origin/main}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --base)
      shift
      [ "$#" -gt 0 ] || { echo "preflight: --base 需要一个 ref 参数" >&2; exit 1; }
      BASE_REF="$1"
      ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^#\{1,\} \{0,1\}//'
      exit 0
      ;;
    *)
      echo "preflight: 未知参数 '$1'（用 --help 看用法）" >&2
      exit 1
      ;;
  esac
  shift
done

if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BOLD=""; C_OFF=""
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
FAIL_COUNT=0
FAILED_LABELS=""   # 换行分隔的 "<label>\t<recipe_fn>"

_head() { printf '\n%s=== [%s/3] %s ===%s\n' "$C_BOLD" "$1" "$2" "$C_OFF"; }
_pass() { printf '%sPASS%s  %s\n' "$C_GREEN" "$C_OFF" "$1"; }
_fail() {
  printf '%sFAIL%s  %s\n' "$C_RED" "$C_OFF" "$1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED_LABELS="${FAILED_LABELS}${1}	${2}
"
}

# ---- 修复配方（函数形态：bash 3.2 下 heredoc 不能塞进 $(...)）-----------------
recipe_secrets() {
  cat <<'EOF'
  1) 先分清退出码语义（别看到非零就开始找"泄漏"）：
       exit 1 = 真发现了 .secrets.baseline 里没有的疑似密钥
       exit 3 = detect-secrets-hook 刷新了 .secrets.baseline 但它没 staged
  2) exit 3（最常见，往往只是行号/generated_at 漂了）：
       git add .secrets.baseline && scripts/preflight_pr.sh
  3) exit 1 且是**真密钥**：代码里删掉 + **轮换该凭据**（进过 git 历史就算已泄漏），
     改从 env 读，并在 contracts/env_registry.yaml 登记这个 env。
  4) exit 1 但是**误报**（测试 fixture / 样例 sha）：加窄口径 pragma
       # pragma: allowlist secret
     或审计后写进 baseline：detect-secrets scan --baseline .secrets.baseline
  5) 没装扫描器：pip install detect-secrets
EOF
}

recipe_contracts() {
  cat <<'EOF'
  两份 index.yaml 必须一致（deeptutor/contracts/index.yaml 是打包进 runtime 的副本，
  运行时读的是它；只改仓库根那份 = 线上还在跑旧契约，CI 的 parity 闸也会红）：
      cp contracts/index.yaml deeptutor/contracts/index.yaml
  先确认方向没搞反（谁是你刚编辑的那份），然后两份一起 commit。
EOF
}

recipe_env() {
  cat <<'EOF'
  env-registry：新 env / feature flag 必须先登记再读。
    - 新的 os.getenv / os.environ / env_store.get / env_flag 名字 → 加进
      contracts/env_registry.yaml（写清 owner、默认值、是否 secret）。
    - 尤其是 env_flag()：名字拼错不会报错，只会静默返回默认值 —— 灰度看着上线了其实没生效。
    - 单独复跑：python3 scripts/check_env_registry.py --all
EOF
}

recipe_schema() {
  cat <<'EOF'
  schema-registry closure：每个 schema version id 都要有 tier 裁定。
    - 新的判分/契约 typed object → 登记进 contracts/schema_registry.yaml
      （T1 判分对象 / T2 运行时消费契约）；临时中间态才走 T3 carve-out，别拿 T3 当垃圾桶。
    - 单独复跑：python3 scripts/check_schema_registry.py --closure
EOF
}

# ---------------------------------------------------------------------------
# base sha 解析：CI 用 PR base sha，本地等价物是 merge-base。
# 拿不到 base（例如没 fetch 过 origin/main）就 fail-closed —— 用错的 base 扫描等于没扫。
# ---------------------------------------------------------------------------
BASE_SHA="$(git merge-base "$BASE_REF" HEAD 2>/dev/null)"
if [ -z "$BASE_SHA" ]; then
  printf '%spreflight: 解析不出 %s 与 HEAD 的 merge-base。%s\n' "$C_RED" "$BASE_REF" "$C_OFF" >&2
  printf '  修复：git fetch origin main   （或用 --base <你的基准 ref>）\n' >&2
  exit 1
fi
HEAD_SHA="$(git rev-parse HEAD)"
printf '%spreflight_pr%s  repo=%s\n' "$C_BOLD" "$C_OFF" "$REPO_ROOT"
printf '             base=%s (%s)  head=%s\n' "$(echo "$BASE_SHA" | cut -c1-9)" "$BASE_REF" "$(echo "$HEAD_SHA" | cut -c1-9)"

# ===========================================================================
# ① detect-secrets
# ===========================================================================
_head 1 "detect-secrets（已提交 diff + 工作区未提交改动）"

if ! command -v detect-secrets-hook >/dev/null 2>&1; then
  _fail "detect-secrets：扫描器未安装（fail-closed，不当作通过）" recipe_secrets
else
  committed_rc=0
  worktree_rc=0
  # (a) 已提交的 diff —— 与 CI 的 "Secret scan changed files (BLOCKING)" step 同一条命令。
  "$PYTHON_BIN" scripts/ci/tests_workflow_scope.py scan-secrets-changed \
    --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" || committed_rc=$?

  # (b) 工作区未提交/未跟踪改动 —— CI 看不到它们，但 PR 一提交就归 CI 管。
  #     复用 tests_workflow_scope.secret_scan_files 这个**唯一**的扫描输入过滤器
  #     （生成物/二进制/runtime supply 的排除清单只有那一份），不在这里复制第二份。
  #     不用 xargs：BSD xargs 会把被调命令的退出码统一压成 1，而 1 与 3 的区别
  #     （真发现密钥 vs 只是刷了 baseline 行号）正是这里最需要保留的信息。
  worktree_files="$("$PYTHON_BIN" scripts/ci/preflight_worktree_scan_paths.py)"
  if [ -n "$worktree_files" ]; then
    scan_paths=()
    while IFS= read -r _p; do
      [ -n "$_p" ] && scan_paths[${#scan_paths[@]}]="$_p"
    done <<EOF
$worktree_files
EOF
    echo "Scanning ${#scan_paths[@]} uncommitted/untracked file(s)."
    detect-secrets-hook --baseline .secrets.baseline "${scan_paths[@]}" || worktree_rc=$?
  else
    echo "工作区无未提交改动需扫描。"
  fi

  if [ "$committed_rc" -eq 0 ] && [ "$worktree_rc" -eq 0 ]; then
    _pass "detect-secrets：已提交 diff + 工作区均无新密钥"
  elif [ "$committed_rc" -eq 3 ] || [ "$worktree_rc" -eq 3 ]; then
    # 3 是专用码：hook 把 baseline 的行号刷新了（**不是**发现密钥）。
    _fail "detect-secrets：退出码 3 —— 只是刷了 .secrets.baseline 行号，git add 它即可" recipe_secrets
  else
    _fail "detect-secrets：committed=$committed_rc worktree=$worktree_rc（1 = 真发现或 baseline 未 staged）" recipe_secrets
  fi
fi

# ===========================================================================
# ② contracts/index.yaml 双拷贝同步
# ===========================================================================
_head 2 "contracts/index.yaml 双拷贝同步"

if [ ! -f contracts/index.yaml ] || [ ! -f deeptutor/contracts/index.yaml ]; then
  _fail "contracts 双拷贝：有一份 index.yaml 不存在" recipe_contracts
elif diff -u contracts/index.yaml deeptutor/contracts/index.yaml; then
  _pass "contracts 双拷贝：contracts/index.yaml == deeptutor/contracts/index.yaml"
else
  _fail "contracts 双拷贝：两份 index.yaml 不一致（上方为 diff）" recipe_contracts
fi

# ===========================================================================
# ③ env / schema registry（register-before-use）
# ===========================================================================
_head 3 "env / schema registry 闸（register-before-use）"

if "$PYTHON_BIN" scripts/check_env_registry.py --all; then
  _pass "env-registry guard"
else
  _fail "env-registry guard" recipe_env
fi

if "$PYTHON_BIN" scripts/check_schema_registry.py --closure; then
  _pass "schema-registry closure"
else
  _fail "schema-registry closure" recipe_schema
fi

# ===========================================================================
# 汇总
# ===========================================================================
printf '\n%s=== 汇总 ===%s\n' "$C_BOLD" "$C_OFF"
if [ "$FAIL_COUNT" -eq 0 ]; then
  printf '%s三检全过。%s\n' "$C_GREEN" "$C_OFF"
  printf '%s提醒：这只覆盖三项高频闸——CI 还跑单测、contract guard、db/provider/process registry、\n' "$C_YELLOW"
  printf '路由 smoke 等。本地绿 ≠ CI 全绿；本地红 = CI 一定红。%s\n' "$C_OFF"
  exit 0
fi

printf '%s%d 项未通过：%s\n' "$C_RED" "$FAIL_COUNT" "$C_OFF"
printf '%s' "$FAILED_LABELS" | while IFS=$'\t' read -r label recipe_fn; do
  [ -n "$label" ] || continue
  printf '\n%s✗ %s%s\n' "$C_RED" "$label" "$C_OFF"
  "$recipe_fn"
done
printf '\n修完重跑：scripts/preflight_pr.sh\n'
exit 1
