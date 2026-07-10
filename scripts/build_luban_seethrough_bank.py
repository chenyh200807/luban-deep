#!/usr/bin/env python3
"""F16 看穿(seethrough)签发内容包 builder——确定性结构化 + gate,写 candidate。

深母题 schema v2(2026-06-16)的 5 天看穿薄切片量产形态。**投影不生成**:内容
唯一来源 = 已定稿剧本转录的 ``_F16_seethrough_source.json``,builder 只做结构化 +
校验 + 签发形状落盘,不改一字、不新造。

与 R8 解药 builder 同纪律(``build_luban_r8_antidote_bank.py``):
- gate 100% 才写文件;三色/溯源/错因/无审视硬词/无重复全过。
- ``status="candidate"`` + ``source_pack_sha256 = manifest 该 pack content_sha256``;
  签发(candidate→signed)由 ``promote_variant_bank.py --kind seethrough`` 人闸完成。
- ``--check`` 确定性重跑门(零写入),供 promote 人闸复算。

gate(violation_keys:code_unregistered / anchor_unresolved / extension_unannotated /
forbidden_words):
- 每个干扰项 error_code + 定位证据 error_codes ∈ ``ERROR_CODE_REGISTRY``(E/M 系,
  禁 unknown_error)——否则 code_unregistered。
- 定位证据 ``syllabus_chunks`` 现为逐 chunk 对象
  ``{chunk, true_source_pack, source_ref, is_extension}``,按 owner「诚实扩展」规则 gate:
  · ``is_extension=false``:chunk 必须落在 F16 **自身** ``_F16_compiled_source.json``——
    否则 anchor_unresolved(裸跨包借用守卫:未标注且不在本包源料即失败)。
  · ``is_extension=true``:必须非空 ``true_source_pack`` + ``source_ref``(否则
    extension_unannotated),且 chunk 必须落在全 pack ``_*_compiled_source.json`` 并集
    (否则 anchor_unresolved)。
- 学员端文案(题干/选项/暖纠正/今日一刀)无审视硬词(看穿/识破/揭穿/露馅)——否则 forbidden_words。
- 结构自检(直接 raise,非 violation 列表):正确项 ∈ 选项;MCQ 天恰 4 选项;variant_id 唯一;
  干扰项 option_id ∈ 选项且 ≠ 正确项。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_SOURCE = _REPO / "docs" / "原始数据" / "考点原料" / "_F16_seethrough_source.json"
_COMPILED = _REPO / "docs" / "原始数据" / "考点原料" / "_F16_compiled_source.json"
_MANIFEST = _REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
_OUT_TEMPLATE = "_{pack_id}_seethrough_bank.v0.json"
_OUT_DIR = _REPO / "docs" / "原始数据" / "考点原料" / "成品"

_FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")
_SCHEMA_VERSION = "luban-f16-seethrough-bank.v0"


class BuildError(Exception):
    pass


def _load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise BuildError(f"{what} 不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_error_codes() -> set[str]:
    """ERROR_CODE_REGISTRY 的 E/M 系码全集(唯一 authority,不硬编列表)。"""
    from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

    return {
        str(code)
        for code, meta in ERROR_CODE_REGISTRY.items()
        if str(getattr(meta, "series", "") or getattr(meta, "code_series", "")).upper() in {"E", "M"}
        or str(code)[:1] in {"E", "M"}
    }


def _compiled_chunk_ids() -> set[str]:
    """_F16_compiled_source.json 里实存的 chunk_id 全集(溯源 gate 的锚集)。"""
    compiled = _load_json(_COMPILED, "compiled_source")
    ids: set[str] = set()
    for unit in compiled.get("units") or []:
        src = (unit or {}).get("source_ref") or {}
        cid = str(src.get("chunk_id") or "").strip()
        if cid:
            ids.add(cid)
        for sp in (unit or {}).get("scoring_points") or []:
            c = str((sp or {}).get("chunk") or "").strip()
            if c:
                ids.add(c)
    return ids


def _all_compiled_chunk_ids() -> set[str]:
    """全 pack ``_*_compiled_source.json`` 的 chunk_id 并集(诚实扩展锚 resolution 用)。"""
    ids: set[str] = set()
    for path in sorted(_COMPILED.parent.glob("_*_compiled_source.json")):
        try:
            compiled = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(compiled, dict):
            continue
        for unit in compiled.get("units") or []:
            if not isinstance(unit, dict):
                continue
            src = unit.get("source_ref")
            if isinstance(src, dict):
                cid = str(src.get("chunk_id") or "").strip()
                if cid:
                    ids.add(cid)
            for sp in unit.get("scoring_points") or []:
                if not isinstance(sp, dict):
                    continue
                c = str(sp.get("chunk") or "").strip()
                if c:
                    ids.add(c)
    return ids


def _manifest_content_sha(pack_id: str) -> str:
    manifest = _load_json(_MANIFEST, "manifest")
    for pack in manifest.get("packs") or []:
        if str(pack.get("pack_id") or "") == pack_id:
            return str(pack.get("content_sha256") or "")
    raise BuildError(f"manifest 无 pack {pack_id}")


def _has_forbidden(text: str) -> str:
    for w in _FORBIDDEN_WORDS:
        if w in str(text or ""):
            return w
    return ""


def _learner_facing_texts(day: dict[str, Any]) -> list[str]:
    """学员端会看到的文案(审视硬词 gate 的检查面);内部结构名(如 see_through 段
    标签)不计入,但其文本值(会渲染)计入。"""
    texts: list[str] = [str(day.get("today_cut") or ""), str(day.get("stem") or "")]
    for opt in day.get("options") or []:
        texts.append(str((opt or {}).get("text") or ""))
    st = day.get("see_through") or {}
    texts += [str(st.get(k) or "") for k in ("surface", "invariant", "examiner_intent", "learner_misconception")]
    for k in ("warm_correction", "tomorrow_promise", "retest_banner", "replay", "progress_receipt", "safety_net"):
        texts.append(str(day.get(k) or ""))
    return [t for t in texts if t]


def build(pack_id: str = "F16") -> dict[str, Any]:
    source = _load_json(_SOURCE, "seethrough source")
    if str(source.get("case_family_id") or "") != pack_id:
        raise BuildError(f"source case_family_id != {pack_id}")

    registered = _registered_error_codes()
    chunk_ids = _compiled_chunk_ids()
    all_chunk_ids = _all_compiled_chunk_ids()
    content_sha = _manifest_content_sha(pack_id)
    if not content_sha:
        raise BuildError("manifest content_sha256 为空")

    violations: dict[str, list[str]] = {
        "code_unregistered": [],
        "anchor_unresolved": [],
        "extension_unannotated": [],
        "forbidden_words": [],
    }
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for day in source.get("days") or []:
        d = int(day.get("day") or 0)
        variant_id = f"{pack_id}-D{d}-seethrough"
        if variant_id in seen_ids:
            raise BuildError(f"重复 variant_id: {variant_id}")
        seen_ids.add(variant_id)

        # 错因码 ∈ registry(干扰项 + 定位证据)
        codes: list[str] = [str((x or {}).get("error_code") or "") for x in (day.get("distractors") or [])]
        codes += [str(c) for c in ((day.get("evidence") or {}).get("error_codes") or [])]
        for sp in day.get("scoring_points") or []:  # Day4 采分点错因
            codes.append(str((sp or {}).get("error_code") or ""))
        for code in codes:
            code = code.strip()
            if code and code not in registered:
                violations["code_unregistered"].append(f"D{d}:{code}")

        # 溯源:每个 syllabus_chunk 现为对象{chunk,true_source_pack,source_ref,is_extension}
        # owner「诚实扩展」规则:标注跨包事实允许(须落全 pack 并集),裸借用(未标注且不在本包源料)失败。
        for entry in (day.get("evidence") or {}).get("syllabus_chunks") or []:
            entry = entry or {}
            chunk = str(entry.get("chunk") or "").strip()
            if bool(entry.get("is_extension")):
                pack = str(entry.get("true_source_pack") or "").strip()
                ref = str(entry.get("source_ref") or "").strip()
                if not pack or not ref:
                    violations["extension_unannotated"].append(f"D{d}:{chunk}")
                if chunk not in all_chunk_ids:
                    violations["anchor_unresolved"].append(f"D{d}:{chunk}")
            elif chunk not in chunk_ids:
                # 裸跨包借用守卫:未标注 is_extension 却不在 F16 自身源料 → 失败
                violations["anchor_unresolved"].append(f"D{d}:{chunk}")

        # 审视硬词(学员端)
        for text in _learner_facing_texts(day):
            w = _has_forbidden(text)
            if w:
                violations["forbidden_words"].append(f"D{d}:{w}")

        # 结构自检(MCQ 天):恰 4 选项 / 正确项 ∈ 选项 / 干扰项 option_id 合法
        options = day.get("options") or []
        if options:  # Day4 半写无 options
            opt_ids = [str((o or {}).get("option_id") or "") for o in options]
            if len(options) != 4:
                raise BuildError(f"D{d} MCQ 选项数 != 4: {len(options)}")
            correct = str(day.get("correct_option_id") or "")
            if correct not in opt_ids:
                raise BuildError(f"D{d} 正确项 {correct} 不在选项内")
            for dis in day.get("distractors") or []:
                oid = str((dis or {}).get("option_id") or "")
                if oid not in opt_ids or oid == correct:
                    raise BuildError(f"D{d} 干扰项 option_id 非法: {oid}")

        items.append(_project_item(pack_id, day, variant_id))

    total = len(items)
    passed = total if not any(violations.values()) else 0

    bank = {
        "schema_version": _SCHEMA_VERSION,
        "pack_id": pack_id,
        "status": "candidate",
        "source_pack_sha256": content_sha,
        "authored_from": source.get("authored_from"),
        "gate": {"passed": passed, "total": total, **violations},
        "items": items,
    }
    return bank


def _project_item(pack_id: str, day: dict[str, Any], variant_id: str) -> dict[str, Any]:
    """看穿签发形状(read-model 投影的即为此;剥离作者态,只留呈现所需)。"""
    return {
        "variant_id": variant_id,
        "day": int(day.get("day") or 0),
        "competency": str(day.get("competency") or ""),
        "invariant": str(day.get("invariant") or ""),
        "today_cut": str(day.get("today_cut") or ""),
        "retest_banner": str(day.get("retest_banner") or ""),
        "answer_mode": str(day.get("answer_mode") or "mcq"),
        "stem": str(day.get("stem") or ""),
        "options": [
            {"option_id": str((o or {}).get("option_id") or ""), "text": str((o or {}).get("text") or "")}
            for o in day.get("options") or []
        ],
        "correct_option_id": str(day.get("correct_option_id") or ""),
        "distractors": [
            {
                "option_id": str((x or {}).get("option_id") or ""),
                "misconception_id": str((x or {}).get("misconception_id") or ""),
                "wrong_mental_model": str((x or {}).get("wrong_mental_model") or ""),
                "error_code": str((x or {}).get("error_code") or ""),
            }
            for x in day.get("distractors") or []
        ],
        "see_through": day.get("see_through") or {},
        "evidence": day.get("evidence") or {},
        "warm_correction": str(day.get("warm_correction") or ""),
        "tomorrow_promise": str(day.get("tomorrow_promise") or ""),
        # Day4 半写:已签发 P10/P11 采分点文本(自我核对投影,非内核实判)
        "grading_artifact_id": str(day.get("grading_artifact_id") or ""),
        "task_scope": day.get("task_scope") or {},
        "scoring_points": day.get("scoring_points") or [],
        # Day5 综合复测
        "replay": str(day.get("replay") or ""),
        "progress_receipt": str(day.get("progress_receipt") or ""),
        "safety_net": str(day.get("safety_net") or ""),
        "honesty_label": str(day.get("honesty_label") or ""),
        "ledger": str(day.get("ledger") or "light_signal_only"),
        "anchor": str(day.get("anchor") or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="F16 看穿签发内容包 builder")
    ap.add_argument("pack_id", nargs="?", default="F16")
    ap.add_argument("--check", action="store_true", help="确定性重跑门,零写入(供 promote 人闸复算)")
    args = ap.parse_args()

    try:
        bank = build(args.pack_id)
    except BuildError as exc:
        print(f"BUILD FAIL: {exc}", file=sys.stderr)
        return 1

    gate = bank["gate"]
    ok = gate["passed"] == gate["total"] and gate["total"] > 0
    if not ok:
        print(f"GATE FAIL: passed={gate['passed']} total={gate['total']} violations=" +
              json.dumps({k: v for k, v in gate.items() if isinstance(v, list) and v}, ensure_ascii=False),
              file=sys.stderr)
        return 1

    if args.check:
        print(f"seethrough gate OK (--check): {gate['passed']}/{gate['total']} items, 零写入")
        return 0

    out = _OUT_DIR / _OUT_TEMPLATE.format(pack_id=args.pack_id)
    out.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE candidate: {out} ({gate['total']} items, gate 100%, status=candidate)")
    print("下一步签发(人闸): python3 docs/原始数据/考点原料/promote_variant_bank.py "
          f"{args.pack_id} --kind seethrough --basis '<基据>' --who '<教研>'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
