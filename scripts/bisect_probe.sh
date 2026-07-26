#!/usr/bin/env bash
# bisect_probe.sh — good/bad/skip 判定器,供 `git bisect run` 调用。
#
# 用法:
#   1) 写一个能表征该 bug 的最小测试(要求:<30s、不联网、不依赖生产数据)
#   2) export BISECT_TEST="tests/path/to/test_repro.py::test_name"
#   3) git bisect start --first-parent
#      git bisect bad  HEAD
#      git bisect good <已知好的 sha/tag>
#      git bisect run scripts/bisect_probe.sh
#
# 为什么要 --first-parent:本仓 3456 commits 里 590 个是 merge,工作流是
# 分支→PR→merge,first-parent 线上每个点 = 一个完整 PR。先在 PR 粒度二分
# (约 10 步),定位到 PR 后再在该 PR 分支内部二分(约 3-5 步)。
#
# 退出码契约(git bisect run 强制):
#   0        good   — 该 commit 不含此 bug
#   1        bad    — 该 commit 含此 bug
#   125      skip   — 无法在此 commit 判定(环境装不上/依赖漂移/测试文件不存在)
#   128-255  abort  — 终止整个 bisect
#
# 125 是本脚本最关键的一行。本仓 requirements*/pyproject 改过 35 次,跨越
# 依赖变更点时旧 commit 装不上环境;没有 125,这些 commit 会被误判成 bad,
# bisect 会给出一个完全错误的答案。

set -uo pipefail

SKIP=125

# ── 0) 参数校验 ────────────────────────────────────────────────────────────
if [ -z "${BISECT_TEST:-}" ]; then
    echo "[probe] FATAL: 未设置 BISECT_TEST" >&2
    echo "[probe]        例: export BISECT_TEST='tests/services/test_x.py::test_y'" >&2
    exit 128   # abort:配置错误不该被当成 bad
fi

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
echo "[probe] === $SHA ==="

# ── 1) 环境探针:装不上 → skip,绝不当 bad ────────────────────────────────
if ! python -c "import deeptutor" >/dev/null 2>&1; then
    echo "[probe] $SHA: import deeptutor 失败 → SKIP(依赖漂移或包结构不同)"
    exit $SKIP
fi

# ── 2) 测试目标存在性:该 commit 上还没这个测试 → skip ────────────────────
TEST_FILE="${BISECT_TEST%%::*}"
if [ ! -f "$TEST_FILE" ]; then
    echo "[probe] $SHA: $TEST_FILE 不存在 → SKIP(测试晚于此 commit 引入)"
    exit $SKIP
fi

# ── 3) 跑复现测试 ──────────────────────────────────────────────────────────
# -p no:randomly 关掉随机顺序;bisect 要求同一 commit 每次判定结果一致。
OUT="$(python -m pytest "$BISECT_TEST" -x -q -p no:randomly 2>&1)"
RC=$?

case $RC in
    0)
        echo "[probe] $SHA: GOOD"
        exit 0
        ;;
    1)
        # pytest 退出码 1 = 有测试失败(而非收集错误)
        echo "[probe] $SHA: BAD"
        exit 1
        ;;
    2|3|4)
        # 2=中断 3=内部错误 4=用法错误 → 判不了
        echo "[probe] $SHA: pytest rc=$RC → SKIP"
        exit $SKIP
        ;;
    5)
        echo "[probe] $SHA: 未收集到测试 → SKIP"
        exit $SKIP
        ;;
    *)
        # 收集错误/import 错误常见于历史 commit,一律 skip 而不是 bad
        echo "[probe] $SHA: pytest rc=$RC → SKIP"
        echo "$OUT" | tail -5 >&2
        exit $SKIP
        ;;
esac
