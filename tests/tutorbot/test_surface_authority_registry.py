"""判分链「学生提交面」消费点登记表——**止血带，不是语义闭包**。

## 这是什么

2026-08-01 一天之内，同一个病理以五张脸复发（判分 ctx / 直批探针 / 入口安全闸 /
narration 尺 / narration 面），根因都是：**消费者拿组装后的 turn 信封当"学生这轮的
真实提交"用**。信封由 ``services/session/turn_runtime.py`` 拼装
（``[Attached Documents]`` / ``[Notebook Context]`` / ``[History Context]`` /
``[User Question]``，或 ``## 参考证据`` / ``### 局部工作记忆投影`` / ``## 当前用户问题``），
**随账号历史逐轮变化**——所以离线用干净存档永远复现不出来。

单一权威：
- ``AgentLoop._case_submission_surface(md, current_message)``
- ``deep_question._submission_surface(context)``（同口径，复用同一剥离器）
- ``ChatOrchestrator._routing_user_message(context)``

本测试把「信封变量的消费点」冻成一张登记表：**新增一个消费点就红**，作者必须显式登记
并写明它的语义主语是「学生这轮真实提交」（→ 必须先过 surface 权威）还是「整段组装消息」
（→ 豁免，写理由）。

## ⚠️ 这挡不住什么（诚实分层）

scanner 是**语法级**的：它只知道"这里消费了信封变量"，**不知道消费得对不对**。
它挡不住的语义级绕过至少有三类：

1. 把信封先赋给一个别的名字（``m = current_message`` 之后消费 ``m``）——不在名单里。
2. 已登记为 ``EXEMPT`` 的点后来被改成有权力的判据——登记项不会自动变红。
3. **本文件之外**的任何新消费者（信封会流向 turn_runtime / capabilities / tools）。

真正的闭包是 ``contracts/turn.md §判分链学生提交单一来源`` 那条散文合同 + code review，
以及 ``tests/tutorbot/test_case_submission_surface_authority_sweep.py`` 里那些
**语义级可证伪**用例。本文件只负责让"又多了一个消费点"这件事**无法静默发生**。

## 怎么改

改动被本测试拦下时：先判定语义主语，收权（或写豁免理由），然后把
``pytest -q tests/tutorbot/test_surface_authority_registry.py`` 报出的实际清单更新进
``REGISTERED_CONSUMPTION_SITES``。**不要为了让测试变绿而直接抄新清单**——抄之前必须逐条
回答那个判定问题。
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# 每个文件只扫**该文件里承载组装信封的那些名字**。
# 例如 question_followup.py 全模块没有 metadata 入参，它的 ``message`` / ``user_message``
# 是"调用方给什么就是什么"的纯字符串形参，不是信封本身——面的纪律归调用侧
# （orchestrator._routing_user_message / loop._case_submission_surface），
# 故这里只扫 ``ctx.user_message`` 这种确定指向信封的形态。
SCAN_TARGETS: dict[str, tuple[str, ...]] = {
    # loop.py 的 finalize 链把 current_message 以 ``user_message=`` 传下去，两个名字同源。
    "deeptutor/tutorbot/agent/loop.py": ("current_message", "user_message"),
    "deeptutor/capabilities/deep_question.py": ("context.user_message",),
    "deeptutor/runtime/orchestrator.py": ("context.user_message",),
    "deeptutor/services/question_lifecycle_skills.py": ("ctx.user_message",),
    "deeptutor/services/question_followup.py": ("ctx.user_message",),
}


# 只登记**判据形状**的消费：模式匹配 / 切割 / 计数 / 分类。
# 纯搬运（``build_messages(current_message=...)`` / prefetch / 落库 / logger）不是病灶形状，
# 也不该进登记表——把它们扫进来只会让表长到没人读，反而掩盖真正的新增判据。
_JUDGEMENT_PREFIXES = (
    "looks_like",
    "_looks_like",
    "is_",
    "_is_",
    "has_",
    "_has_",
    "detect_",
    "_detect_",
    "classify_",
    "_classify_",
    "extract_",
    "_extract_",
    "split_",
    "_split_",
    "resolve_submission",
    "_resolve_submission",
    "submission_confidence",
    "prepare_exact_question_probe",
    "case_grading_context_from_full_submission",
    "mcq_grading_context_from_full_submission",
)
_JUDGEMENT_SUFFIXES = ("_request", "_matches_user_stem", "_probe", "_titles")
_JUDGEMENT_MODULES = ("re",)


def _is_judgement_callee(func: ast.AST) -> bool:
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name) and func.value.id in _JUDGEMENT_MODULES:
            return True
        leaf = func.attr
    elif isinstance(func, ast.Name):
        leaf = func.id
    else:
        return False
    return leaf.startswith(_JUDGEMENT_PREFIXES) or leaf.endswith(_JUDGEMENT_SUFFIXES)


def _expr_src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def _mentions(node: ast.AST, names: tuple[str, ...]) -> bool:
    src = _expr_src(node)
    return any(name in src for name in names)


class _Collector(ast.NodeVisitor):
    """收集「信封变量被消费」的点：函数调用实参、``in`` 成员测试、切片。

    赋值/形参默认值不算消费（那是搬运，不是判据）。
    """

    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names
        self.stack: list[str] = []
        self.sites: set[str] = set()

    def _qualname(self) -> str:
        return ".".join(self.stack) or "<module>"

    def _push(self, node: ast.AST) -> None:
        self.stack.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _push
    visit_AsyncFunctionDef = _push
    visit_ClassDef = _push

    def _record(self, expr: ast.AST) -> None:
        self.sites.add(f"{self._qualname()} :: {_expr_src(expr)}")

    def visit_Call(self, node: ast.Call) -> None:
        if not _is_judgement_callee(node.func):
            self.generic_visit(node)
            return
        callee = _expr_src(node.func)
        for arg in node.args:
            if _mentions(arg, self.names):
                self._record(ast.parse(f"{callee}({_expr_src(arg)})", mode="eval").body)
        for kw in node.keywords:
            if kw.value is not None and _mentions(kw.value, self.names):
                self._record(
                    ast.parse(
                        f"{callee}({kw.arg or '**'}={_expr_src(kw.value)})", mode="eval"
                    ).body
                )
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) and any(
            _mentions(cmp, self.names) for cmp in node.comparators
        ):
            self._record(node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if _mentions(node.value, self.names):
            self._record(node)
        self.generic_visit(node)


def collect_consumption_sites(path: pathlib.Path, names: tuple[str, ...]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    collector = _Collector(names)
    collector.visit(tree)
    return collector.sites


# ---------------------------------------------------------------------------
# 登记表。每一项后面的注释是**判定理由**，不是描述。
#   COLLAPSED = 已过 surface 权威（或本身就是权威/权威的解析器）
#   EXEMPT    = 语义主语确实是整段组装消息，或该点零判据权力
# ---------------------------------------------------------------------------
#
# ⚠️ 特别注意 ``REBOUND`` 一类：函数头把形参重新绑定成 surface
# （``user_message = cls._case_submission_surface(metadata, user_message)``）之后，
# 函数体里的判据虽然仍写着 ``user_message``，看的却已经是干净面。scanner **看不出**这个
# 区别——所以这些条目的注释必须写明"已在函数头收面"，改动这些函数时要一并核对那一行还在。
REGISTERED_CONSUMPTION_SITES: dict[str, set[str]] = {
    "deeptutor/tutorbot/agent/loop.py": {
        # --- AUTHORITY：surface 权威 / 信封剥离器自身 ---
        "AgentLoop._case_submission_surface :: cls._extract_current_user_question_section(str(current_message or \'\'))",
        "AgentLoop._resolve_tool_query :: cls._extract_current_user_question_section(current_message)",
        # --- COLLAPSED（调用侧显式过 surface）---
        "AgentLoop._run_case_grading_direct :: looks_like_practice_generation_request(self._case_submission_surface(runtime_metadata, current_message))",
        # --- REBOUND（函数头已 user_message = _case_submission_surface(...)，函数体判据看的是干净面）---
        "AgentLoop._should_guard_degraded_exact_answer_claim :: looks_like_free_text_mcq_answer_request(user_message)",
        "AgentLoop._should_guard_degraded_exact_answer_claim :: cls._extract_answer_letter_claim(user_message)",
        "AgentLoop._degraded_mcq_grading_response :: looks_like_free_text_mcq_grading_request(user_message)",
        "AgentLoop._degraded_mcq_grading_response :: cls._extract_answer_letter_claim(user_message)",
        "AgentLoop._case_grading_no_authority_score_fallback :: looks_like_practice_generation_request(user_message)",
        "AgentLoop._build_v1_case_ctx :: case_grading_context_from_full_submission(user_message)",
        "AgentLoop._build_v1_case_ctx :: AgentLoop._split_case_grading_submission(user_message)",
        # --- DOWNSTREAM：形参由已收面的调用方喂入（_case_grading_live_preview_text 的唯一
        #     调用点在 _run_case_grading_direct，喂的是 _case_submission_surface 的产物）---
        "AgentLoop._case_grading_live_preview_text :: AgentLoop._split_case_grading_submission(user_message)",
        "AgentLoop._split_case_grading_submission :: split_full_case_answer_submission(user_message)",
        # --- EXEMPT ---
        # 观测标签，零门控权力（整个表达式只进 logger.debug 的格式化参数）。
        # 若哪天升格成判据，必须重新判定语义主语。
        "AgentLoop._finalize_visible_answer :: \'【题目】\' in user_message",
        "AgentLoop._finalize_visible_answer :: \'case\' in user_message[:30].lower()",
        "AgentLoop._finalize_visible_answer :: user_message[:30]",
        # RAG 身份探针的面归 _resolve_tool_query（它本身就是 surface 解析器，见 AUTHORITY）。
        "AgentLoop._process_message :: prepare_exact_question_probe(self._resolve_tool_query(current_message, runtime_metadata))",
        # skill 预装：装多一个 skill 无破坏性（不夺判分权、不改路由终点）；
        # 注入上下文里出现出题语汇时把 deep-question 备着是合理的。语义主语确实是整段。
        "AgentLoop._select_progressive_skill_names :: looks_like_practice_generation_request(current_message)",
    },
    # 这三个模块目前**零**判据形状的信封消费点：
    # - deep_question：唯一读 context.user_message 的地方是 _submission_surface 权威自身；
    # - orchestrator：唯一读的是 _routing_user_message 权威自身，加两处零判据权力的回显/观测；
    # - question_lifecycle_skills / question_followup：全模块只拿字符串形参
    #   （question_followup 连 metadata 入参都没有），面的纪律归调用侧
    #   （orchestrator._routing_user_message 已在 lifecycle scene 入口收面）。
    # 任何人在这四个文件里新写一个 looks_like_*/_extract_*/re.* 直接吃信封，这里立刻变红。
    "deeptutor/capabilities/deep_question.py": set(),
    "deeptutor/runtime/orchestrator.py": set(),
    "deeptutor/services/question_lifecycle_skills.py": set(),
    "deeptutor/services/question_followup.py": set(),
}


def test_surface_consumption_sites_match_registry() -> None:
    failures: list[str] = []
    for rel, names in SCAN_TARGETS.items():
        actual = collect_consumption_sites(REPO_ROOT / rel, names)
        expected = REGISTERED_CONSUMPTION_SITES[rel]
        added = sorted(actual - expected)
        removed = sorted(expected - actual)
        if added:
            failures.append(
                f"\n{rel} 新增了未登记的信封消费点（先判定语义主语，再登记）：\n  "
                + "\n  ".join(added)
            )
        if removed:
            failures.append(
                f"\n{rel} 登记表里有已不存在的条目（收权后请删掉登记）：\n  "
                + "\n  ".join(removed)
            )
    assert not failures, (
        "".join(failures)
        + "\n\n判定问题：这个点的语义主语是「学生**这轮**真实提交」还是「整段组装消息」？"
        "\n  前者 → 必须先过 _case_submission_surface / _submission_surface / _routing_user_message；"
        "\n  后者 → 登记为 EXEMPT 并在注释里写清理由。"
        "\n（本 scanner 是止血带：它只看语法，挡不住语义级绕过——见模块 docstring。）"
    )


def test_scan_targets_are_all_registered() -> None:
    """登记表与扫描目标必须一一对应（防止加了扫描目标却忘了建登记项）。"""
    assert set(SCAN_TARGETS) == set(REGISTERED_CONSUMPTION_SITES)
    for rel in SCAN_TARGETS:
        assert (REPO_ROOT / rel).is_file(), rel
