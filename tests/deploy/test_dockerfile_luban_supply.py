"""Dockerfile 必须携带鲁班 runtime 供给文件（防镜像缺 manifest/变体池致运行时空转复发）。

事故史（两次同型）：
- 2026-07-02：容器无 _pack_manifest.json → lessons fail-closed 恒空（#344/#345 修）。
- 2026-07-03：#344 逐文件 COPY 只写了 S05 → F16 变体池不进镜像 → F16 复测线上空。
治本：成品目录整目录 COPY + .dockerignore 白名单通配（新站补池零 Dockerfile 改动）。
本测试固化通配语义 + 用真实磁盘文件核验白名单实际命中（防模式写错的假绿）。
"""
import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUPPLY_DIR = "docs/原始数据/考点原料/成品"


def _dockerignore_patterns() -> list[str]:
    lines = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def _excluded(path: str, patterns: list[str]) -> bool:
    # docker patternmatcher 近似: last-match-wins, `!` 反排除
    verdict = False
    for pat in patterns:
        neg = pat.startswith("!")
        core = (pat[1:] if neg else pat).rstrip("/")
        if (
            fnmatch.fnmatch(path, core)
            or path.startswith(core + "/")
            or fnmatch.fnmatch(path, core + "/*")
        ):
            verdict = not neg
    return verdict


def test_dockerfile_copies_supply_dir() -> None:
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert f'COPY ["{SUPPLY_DIR}/"' in dockerfile, (
        "镜像必须整目录 COPY 供给目录(配 dockerignore 白名单)——"
        "逐文件 COPY 是 F16 漏拷事故的根因, 禁止回退"
    )


def test_dockerignore_allowlists_luban_supply_files() -> None:
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")
    assert "!docs/原始数据/考点原料/成品/_pack_manifest.json" in dockerignore
    assert "!docs/原始数据/考点原料/成品/_*_variant_bank.v0.json" in dockerignore
    # 考点卡池(复习模块 §6.2)——同 F16 漏拷教训, 通配白名单进镜像
    assert "!docs/原始数据/考点原料/成品/_*_concept_card_bank.v0.json" in dockerignore
    # fusion-a(生命周期 join 工件)——缺任一则生产投影静默全空(Codex P3 回归缺口)
    assert "!docs/原始数据/考点原料/成品/_question_pack_map.v0.json" in dockerignore
    assert "!docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json" in dockerignore


def test_dockerignore_wildcard_covers_all_variant_banks_on_disk() -> None:
    """白名单必须命中磁盘上全部 bank + manifest + 生命周期 join 工件（真实文件核验, 防模式假绿）。"""
    patterns = _dockerignore_patterns()
    supply = REPO / SUPPLY_DIR
    targets = sorted(p.name for p in supply.glob("_*_variant_bank.v0.json"))
    assert targets, "磁盘上应存在至少一个变体池(S05/F16 已产)"
    assert len(targets) >= 2, f"S05+F16 双池时代, 实际: {targets}"
    card_banks = sorted(p.name for p in supply.glob("_*_concept_card_bank.v0.json"))
    assert len(card_banks) >= 5, f"首批五站考点卡池(S05/A01/F16/J01/N01), 实际: {card_banks}"
    targets += card_banks
    for name in targets + [
        "_pack_manifest.json",
        "_question_pack_map.v0.json",
        "_pack_taxonomy_registry.v0.json",
    ]:
        assert not _excluded(f"{SUPPLY_DIR}/{name}", patterns), (
            f"{name} 被 .dockerignore 挡在 build context 外(远端 build 后运行时缺供给)"
        )


def test_dockerignore_still_excludes_pack_bodies() -> None:
    """白名单只放供给 sidecar，pack 正文/jury 等不进镜像（防镜像膨胀）。"""
    patterns = _dockerignore_patterns()
    for name in ("S05_临时用电三级配电.md", "_S05_jury.json", "_pack_manifest.overrides.json"):
        assert _excluded(f"{SUPPLY_DIR}/{name}", patterns), f"{name} 不应进镜像"
