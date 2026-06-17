from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The real prompt templates live under deeptutor/agents/<agent>/prompts/{en,zh,cn}; the old
# ``src/agents`` path holds only an empty package stub, so this parity gate used to no-op
# (0 module dirs with prompts/en → trivially green). Point it at the live tree so the en↔zh
# key + placeholder parity is actually enforced (schema-governance P3#12).
AGENTS_DIR = PROJECT_ROOT / "deeptutor" / "agents"

# Template placeholders are expected to be like {topic}, {knowledge_title}, etc.
# Avoid false positives from LaTeX (\frac{1}{3}) and Mermaid (B{{Processing}}).
PLACEHOLDER_RE = re.compile(r"(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*\}(?!\})")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _iter_yaml_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.rglob("*.yaml") if p.is_file()])


def _get_placeholders(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found |= set(PLACEHOLDER_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            found |= _get_placeholders(v)
    elif isinstance(value, list):
        for v in value:
            found |= _get_placeholders(v)
    return found


def _collect_keys(value: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.add(path)
            keys |= _collect_keys(v, path)
    elif isinstance(value, list):
        if prefix:
            keys.add(prefix)
    else:
        if prefix:
            keys.add(prefix)
    return keys


def test_prompts_key_and_placeholder_parity():
    assert AGENTS_DIR.exists(), f"Agents dir not found: {AGENTS_DIR}"

    failures: list[str] = []

    for module_dir in sorted([p for p in AGENTS_DIR.iterdir() if p.is_dir()]):
        prompts_dir = module_dir / "prompts"
        en_dir = prompts_dir / "en"
        if not en_dir.exists():
            continue

        zh_dir = prompts_dir / "zh"
        cn_dir = prompts_dir / "cn"

        for en_file in _iter_yaml_files(en_dir):
            rel = en_file.relative_to(en_dir)
            en_obj = _load_yaml(en_file)

            candidates: list[tuple[str, Path]] = []
            if zh_dir.exists():
                candidates.append(("zh", zh_dir / rel))
            if cn_dir.exists():
                candidates.append(("cn", cn_dir / rel))

            if not candidates:
                continue

            for lang_name, target_file in candidates:
                if not target_file.exists():
                    failures.append(f"[MISSING {lang_name}] {module_dir.name}: {rel.as_posix()}")
                    continue

                target_obj = _load_yaml(target_file)
                en_keys = _collect_keys(en_obj)
                target_keys = _collect_keys(target_obj)

                missing = sorted(en_keys - target_keys)
                extra = sorted(target_keys - en_keys)

                en_ph = _get_placeholders(en_obj)
                target_ph = _get_placeholders(target_obj)
                ph_missing = sorted(en_ph - target_ph)
                ph_extra = sorted(target_ph - en_ph)

                if missing or extra or ph_missing or ph_extra:
                    msg = [f"[DIFF {lang_name}] {module_dir.name}: {rel.as_posix()}"]
                    if missing:
                        msg.append("  missing keys: " + ", ".join(missing[:50]))
                    if extra:
                        msg.append("  extra keys: " + ", ".join(extra[:50]))
                    if ph_missing:
                        msg.append("  missing placeholders: " + ", ".join(ph_missing))
                    if ph_extra:
                        msg.append("  extra placeholders: " + ", ".join(ph_extra))
                    failures.append("\n".join(msg))

    assert not failures, "Prompt parity failures:\n" + "\n\n".join(failures)


# Template placeholders verify en↔zh FILE parity above; this closure verifies the other,
# previously-unguarded direction: every prompt that code declares it will LOAD actually resolves
# to a real prompt file. PromptManager._load_with_fallback returns ``{}`` (and get_prompt returns
# the empty fallback) when no file is found — a typo'd / deleted prompt degrades silently to a
# blank prompt, never an error. This is the `dormant authority` failure shape: a prompt reference
# with no enforcement that its target exists.
_PROMPT_USE_RE = re.compile(r"self\.prompts|self\.get_prompt|get_prompt\(")


def _declared_prompt_consuming_agents() -> set[tuple[str, str]]:
    """Statically discover every ``(module_name, agent_name)`` an agent passes to BaseAgent AND
    that the declaring file actually consumes (references ``self.prompts`` / ``get_prompt``).

    An agent may pass module_name/agent_name purely for logging/config without ever reading
    file-based prompts (e.g. ``vision_solver_agent`` builds prompts inline) — those are correctly
    out of scope. register-before-use here means "if you USE a prompt, it must resolve", not
    "every agent must own a prompt file". This is a principled filter, not an allowlist.
    """
    pairs: set[tuple[str, str]] = set()
    for py in AGENTS_DIR.rglob("*.py"):
        try:
            src = py.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        if not _PROMPT_USE_RE.search(src):
            continue  # declaring file does not consume file-based prompts
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if isinstance(k.value, ast.Constant)}
            module, agent = kw.get("module_name"), kw.get("agent_name")
            if (
                module is not None
                and agent is not None
                and isinstance(module.value, str)
                and isinstance(agent.value, str)
            ):
                pairs.add((module.value, agent.value))
    return pairs


def test_every_prompt_consuming_agent_resolves_a_prompt():
    """register-before-use closure for prompts — NO second authority.

    The filesystem (under deeptutor/agents/*/prompts/) stays the single inventory authority and
    the production ``PromptManager`` stays the single resolution authority; this test maintains no
    duplicate registry YAML. It drives the REAL loader for every prompt-consuming agent and fails
    if it silently returns an empty dict, which would leave that agent running on a blank prompt.
    """
    from deeptutor.services.prompt.manager import get_prompt_manager

    pm = get_prompt_manager()
    declared = _declared_prompt_consuming_agents()
    assert declared, "AST scan found no prompt-consuming agents — the scan is broken, not the prompts"

    unresolved = sorted(
        f"{module}/{agent}"
        for module, agent in declared
        if not pm.load_prompts(module_name=module, agent_name=agent, language="zh")
    )
    assert not unresolved, (
        "prompt-consuming agents whose declared prompt does NOT resolve to a file "
        "(silent blank-prompt risk — register-before-use violated):\n  " + "\n  ".join(unresolved)
    )

    # Discrimination: the closure must actually catch a missing prompt, else it is a no-op gate.
    assert not pm.load_prompts(
        module_name="__nonexistent_module__", agent_name="__nope__", language="zh"
    ), "PromptManager resolved a bogus agent — the closure check cannot distinguish missing prompts"
