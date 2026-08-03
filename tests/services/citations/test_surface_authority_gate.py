"""L1 防漂移闸：引用装配的 surface 只能是 student(或走 fail-safe 默认)。

为什么需要这条闸(2026-08-03 收权结论)：

「这条来源能不能给学生看」的唯一防线是 `normalizer._public_source_candidates`
→ `_is_hidden_source`，而 `_is_hidden_source` 只在 ``policy.surface == "student"``
时才丢弃命中 `HIDDEN_AUTHORITY_FIELDS` 的来源。也就是说这道防线**由 surface 取值
把守**：任何一个生产调用点传了 reviewer/internal，答案 key、采分点正文就会被
`_public_quote()` 原样搬进 `public_quote` 并进入公开载荷，而下游 `quality.py`
与 unified_ws `_redact_event_for_public` 都只匹配**字段名**、抓不到**字段值**
(实测：L1 关闭后 public_quote == 'A' / '采分点:防水等级一级' 一路畅通)。

所以 L1 的失效方式不是"逻辑写错"(那有 test_normalizer.py 兜)，而是**调用点漂移**：
某天有人新增一个 reviewer 面调用点，或把 surface 参数化成变量。本模块用 AST
穷举生产代码里所有 `CitationPolicy(...)` 构造点，逐个判定。

已知缺口(未修，推荐方向)：public_quote 缺值级溯源闸——它应当被要求追到非 hidden
字段的来源，而不是任取 source dict 里的 ``value``。该改动触及引用装配语义，
已作为判断题呈 owner，本轮不做。在它落地前，本文件这条闸是唯一的漂移防护。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from deeptutor.services.citations.schema import CitationPolicy

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ROOT = REPO_ROOT / "deeptutor"

# 唯一允许的公开装配面。reviewer/internal 是内部审阅面，故意不丢弃 hidden 字段，
# 因此绝不能出现在会走到公开载荷的生产装配路径上。
ALLOWED_SURFACE = "student"


def _iter_production_python_files() -> list[Path]:
    return sorted(
        path
        for path in PRODUCTION_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _citation_policy_call_sites() -> list[tuple[Path, ast.Call]]:
    """穷举生产代码里所有 CitationPolicy(...) 构造点。"""
    sites: list[tuple[Path, ast.Call]] = []
    for path in _iter_production_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 生产树不该有语法错
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if name == "CitationPolicy":
                sites.append((path, node))
    return sites


def test_citation_policy_default_surface_is_student() -> None:
    """fail-safe 默认必须是 student —— 省略 surface 的调用点全靠它。"""
    assert CitationPolicy().surface == ALLOWED_SURFACE


def test_scanner_actually_finds_the_known_call_sites() -> None:
    """反空转:扫描器必须真的扫到调用点,否则这条闸是假绿。

    2026-08-03 实测生产共 5 处(terminal_result_assembler / deep_question /
    tutorbot ×2 / agentic_pipeline)。允许增长,但不允许归零 —— 若某次重构把
    CitationPolicy 换了名字或改为间接构造,这里会先红,提醒同步更新本闸。
    """
    sites = _citation_policy_call_sites()
    assert len(sites) >= 5, (
        f"只扫到 {len(sites)} 个 CitationPolicy 构造点(预期 >=5)。"
        "构造方式可能已变更,本防漂移闸需同步更新,否则形同虚设。"
    )


def _surface_violations(sites: list[tuple[Path, ast.Call]]) -> list[str]:
    """判定逻辑的单一实现 —— 真实闸与可证伪自证共用同一条代码路径。"""
    violations: list[str] = []
    for path, call in sites:
        rel = path.name if not path.is_relative_to(REPO_ROOT) else path.relative_to(REPO_ROOT)
        surface_kwargs = [kw for kw in call.keywords if kw.arg == "surface"]

        # surface 也可能以位置参数传入(它是 CitationPolicy 的第一个字段)。
        if call.args:
            arg = call.args[0]
            if not (isinstance(arg, ast.Constant) and arg.value == ALLOWED_SURFACE):
                violations.append(
                    f"{rel}:{call.lineno} 以位置参数传 surface,必须显式写 surface=\"student\""
                )
            continue

        if not surface_kwargs:
            # 省略 = 走 fail-safe 默认,由 test_citation_policy_default_surface_is_student 兜住。
            continue

        for kw in surface_kwargs:
            value = kw.value
            if not isinstance(value, ast.Constant):
                violations.append(
                    f"{rel}:{call.lineno} 把 surface 参数化(非字面量)。"
                    "L1 隐藏来源防线由 surface 取值把守,不得运行时可变。"
                )
            elif value.value != ALLOWED_SURFACE:
                violations.append(
                    f"{rel}:{call.lineno} surface={value.value!r},"
                    "reviewer/internal 面不丢弃 hidden 字段,不得用于公开装配路径。"
                )
    return violations


def test_all_production_citation_policies_use_student_surface() -> None:
    """所有生产装配调用点的 surface 只能是字面量 'student',或省略走默认。"""
    violations = _surface_violations(_citation_policy_call_sites())
    assert not violations, "引用装配 surface 漂移:\n" + "\n".join(violations)


@pytest.mark.parametrize("bad_surface", ["reviewer", "internal"])
def test_gate_is_falsifiable(tmp_path: Path, bad_surface: str, monkeypatch) -> None:
    """可证伪性自证:注入一个非 student 调用点,上面那条闸必须变红。

    没有这条,前一条断言可能因为扫描器失灵而恒绿。
    """
    fake_module = tmp_path / "deeptutor" / "capabilities"
    fake_module.mkdir(parents=True)
    (fake_module / "drifted.py").write_text(
        "from deeptutor.services.citations import CitationPolicy\n"
        f'POLICY = CitationPolicy(surface="{bad_surface}")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        f"{__name__}.PRODUCTION_ROOT", tmp_path / "deeptutor", raising=True
    )

    sites = _citation_policy_call_sites()
    assert len(sites) == 1, "注入的漂移调用点未被扫描器发现"

    # 关键:走的是真实闸同一个判定函数,证明"新增非 student 调用点 → 红"。
    violations = _surface_violations(sites)
    assert violations, f"注入 surface={bad_surface!r} 后闸门仍为绿 —— 这条闸是假的"
    assert bad_surface in violations[0]


def test_gate_is_falsifiable_for_parameterized_surface(tmp_path: Path, monkeypatch) -> None:
    """把 surface 参数化(而非硬编码 reviewer)同样必须变红 —— 这是更隐蔽的漂移。"""
    fake_module = tmp_path / "deeptutor" / "capabilities"
    fake_module.mkdir(parents=True)
    (fake_module / "drifted.py").write_text(
        "from deeptutor.services.citations import CitationPolicy\n"
        "def build(surface):\n"
        "    return CitationPolicy(surface=surface)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        f"{__name__}.PRODUCTION_ROOT", tmp_path / "deeptutor", raising=True
    )

    violations = _surface_violations(_citation_policy_call_sites())
    assert violations, "surface 被参数化后闸门仍为绿"
    assert "参数化" in violations[0]
