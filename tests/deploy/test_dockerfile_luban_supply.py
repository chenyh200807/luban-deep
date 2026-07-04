"""Dockerfile 必须携带鲁班 runtime 供给文件（防镜像缺 manifest 致 lessons 全空复发）。

2026-07-02 live 事故：容器无 _pack_manifest.json → lesson read_model fail-closed →
/api/v1/luban/lessons 恒空；unit 全绿（测试注入 manifest_path）掩盖了缺口。
本测试把「镜像必须 COPY 供给文件」固化为仓库不变量。
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dockerfile_copies_luban_pack_manifest_and_variant_bank() -> None:
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "_pack_manifest.json" in dockerfile, "镜像必须 COPY 深母题 pack manifest"
    assert "_S05_variant_bank.v0.json" in dockerfile, "镜像必须 COPY 变体池(次日复测供给)"
    # fusion-a(生命周期 join 工件)——缺任一则生产投影静默全空(Codex P3 回归缺口)
    assert "_question_pack_map.v0.json" in dockerfile, "镜像必须 COPY 题→pack 映射"
    assert "_pack_taxonomy_registry.v0.json" in dockerfile, "镜像必须 COPY pack→taxonomy 注册表"


def test_dockerignore_allowlists_luban_supply_files() -> None:
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")
    assert "!docs/原始数据/考点原料/成品/_pack_manifest.json" in dockerignore
    assert "!docs/原始数据/考点原料/成品/_S05_variant_bank.v0.json" in dockerignore
    assert "!docs/原始数据/考点原料/成品/_question_pack_map.v0.json" in dockerignore
    assert "!docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json" in dockerignore
