"""M25-H — read-only objective registry extract -> validate -> sign (release_candidate).

Authorized scope: objective REAL_EXAM rows from Supabase `questions_bank` (DB_URL, READ ONLY).
Signs a MINIMAL tracked release_candidate supply (answer_key + hashes + provenance; NO raw stem /
option text dumped). NO publish / deploy / production write / schema change. The runtime never
touches the DB — only this offline signer does, read-only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_grading_artifacts/objective_registry_signing_m25h_20260606"
RC_DIR = REPO / "deeptutor/services/construction_grading/runtime_supply/v2_objective_release_candidate"
SCHEMA_VERSION = "luban_objective_answer_key.v2_release_candidate"
NAMESPACE = "objective_answer_key_real"
STATUS = "release_candidate"
OBJECTIVE_TYPES = ("single_choice", "multi_choice", "judgment")
EXTRACT_COLUMNS = ("id", "original_id", "question_type", "options", "correct_answer", "question_stem",
                   "exam_year", "exam_session", "source", "source_type", "source_meta",
                   "source_chunk_id", "cited_standard_codes", "based_on_version", "content_hash", "node_code")


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _canonical(o) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _env():
    e = {}
    for line in (REPO.parents[0] / "deeptutor" / ".env").read_text().splitlines() if False else \
            Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/.env").read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            e[k] = v
    return e


def _option_keys(options) -> list[str]:
    """Robust option-key extraction: explicit key field, else positional letter."""
    keys = []
    if isinstance(options, list):
        for i, opt in enumerate(options):
            k = ""
            if isinstance(opt, dict):
                for f in ("key", "label", "id", "option", "value"):
                    if str(opt.get(f) or "").strip():
                        cand = str(opt.get(f)).strip().upper()
                        if len(cand) == 1 and cand.isalpha():
                            k = cand
                            break
            keys.append(k or chr(ord("A") + i))
    elif isinstance(options, dict):
        keys = [str(k).strip().upper() for k in options.keys()]
    return keys


def _answer_letters(correct_answer) -> set[str]:
    if isinstance(correct_answer, list):
        s = "".join(str(x) for x in correct_answer)
    else:
        s = str(correct_answer or "")
    return {c for c in s.upper() if c.isalpha()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RC_DIR.mkdir(parents=True, exist_ok=True)
    env = _env()
    where = ("question_type in ('single_choice','multi_choice','judgment') "
             "and source_type='REAL_EXAM' and options is not null and correct_answer is not null")
    query = f"select {','.join(EXTRACT_COLUMNS)} from questions_bank where {where} order by id"
    query_fp = _sha(query)

    conn = psycopg2.connect(env.get("DB_URL", ""), connect_timeout=30)
    conn.set_session(readonly=True, autocommit=True)  # READ ONLY hard guard
    cur = conn.cursor()
    cur.execute("select count(*) from questions_bank where question_type in ('single_choice','multi_choice') and correct_answer is not null")
    all_objective = cur.fetchone()[0]
    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    records, rejected, conflicts = [], [], []
    seen_qid, seen_stemkey = {}, {}
    src_meta_present = cited_present = 0
    for r in rows:
        d = dict(zip(EXTRACT_COLUMNS, r))
        qid = str(d.get("id") or "").strip()
        qtype = str(d.get("question_type") or "").strip()
        options = d.get("options")
        okeys = _option_keys(options)
        ans = _answer_letters(d.get("correct_answer"))
        stem = str(d.get("question_stem") or "").strip()

        if not qid or not okeys or not ans:
            rejected.append({"id": qid, "reason": "missing_id_options_or_answer"}); continue
        if not ans.issubset(set(okeys)):
            rejected.append({"id": qid, "reason": "answer_not_in_options"}); continue
        if qtype == "single_choice" and len(ans) != 1:
            rejected.append({"id": qid, "reason": "single_choice_multi_answer"}); continue

        answer_key = "T" if (qtype == "judgment" and ans == {"A"}) else ("F" if (qtype == "judgment" and ans == {"B"}) else "".join(sorted(ans)))
        options_hash = _sha(_canonical(okeys))
        stem_hash = _sha(stem)
        if qid in seen_qid and seen_qid[qid] != options_hash:
            conflicts.append({"id": qid, "reason": "same_id_different_options"}); continue
        if stem_hash in seen_stemkey and seen_stemkey[stem_hash] != answer_key:
            conflicts.append({"id": qid, "reason": "duplicate_stem_different_key", "stem_hash": stem_hash}); continue
        seen_qid[qid] = options_hash
        seen_stemkey[stem_hash] = answer_key

        sm_present = bool(d.get("source_meta"))
        cs_present = bool(d.get("cited_standard_codes"))
        src_meta_present += int(sm_present)
        cited_present += int(cs_present)
        records.append({
            "question_id": qid,
            "original_id": str(d.get("original_id") or ""),
            "question_type": qtype,
            "answer_key": answer_key,
            "answer_key_hash": _sha(answer_key),
            "options_hash": options_hash,
            "stem_hash": stem_hash,
            "option_count": len(okeys),
            "exam_year": str(d.get("exam_year") or ""),
            "exam_session": str(d.get("exam_session") or ""),
            "source_type": str(d.get("source_type") or ""),
            "based_on_version": str(d.get("based_on_version") or ""),
            "db_content_hash": str(d.get("content_hash") or ""),
            "source_meta_present": sm_present,
            "cited_standard_codes_present": cs_present,
            "source_ref": {"kind": "governed_production_registry", "table": "questions_bank",
                           "source_type": str(d.get("source_type") or ""), "exam_year": str(d.get("exam_year") or "")},
        })

    records.sort(key=lambda x: x["question_id"])
    content_hash = _sha(_canonical(records))
    manifest = {
        "schema_version": SCHEMA_VERSION, "namespace": NAMESPACE, "status": STATUS,
        "published": False, "production_default_connected": False, "release_authority": None,
        "source_table": "questions_bank", "source_authority": "questions_bank.correct_answer (REAL_EXAM, governed)",
        "extraction_query_hash": query_fp,
        "all_objective_count_all_sources": all_objective,
        "scope": "objective REAL_EXAM (single_choice/multi_choice/judgment) with valid options+answer_key",
        "row_count": len(rows), "clean_count": len(records),
        "rejected_count": len(rejected), "conflict_count": len(conflicts),
        "source_meta_present_count": src_meta_present, "cited_standard_codes_present_count": cited_present,
        "content_hash": content_hash,
        "source_hashes": {"questions_bank_extract_query": query_fp},
        "signature": _sha(content_hash + "|" + NAMESPACE + "|" + STATUS),
        "separate_from_case_registry": True,
        "rollback_pointer": "v2_objective_real_candidate (prior signed supply); loader fail-closed -> objective lane absent; production default OFF",
        "minimal_supply_note": "answer_key + hashes + provenance only; raw stem/option TEXT not dumped (stem_hash/options_hash seal integrity).",
    }
    # tracked release_candidate supply
    (RC_DIR / "objective_answer_key_seed_release.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records), "utf-8")
    (RC_DIR / "runtime_supply_v2_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

    # ledgers (gitignored artifacts)
    (OUT / "objective_release_candidate_records_m25h.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records), "utf-8")
    (OUT / "rejected_or_conflict_rows_m25h.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (rejected + conflicts)) or "", "utf-8")
    (OUT / "readonly_extract_ledger_m25h.json").write_text(json.dumps({
        "readonly_transaction": True, "transport": "DB_URL Supabase main pooler (psycopg2 readonly)",
        "db_project": "main app (DB_URL)", "table": "questions_bank",
        "extraction_query_hash": query_fp, "columns": list(EXTRACT_COLUMNS),
        "all_objective_all_sources": all_objective, "extracted_real_exam_rows": len(rows),
        "clean": len(records), "rejected": len(rejected), "conflicts": len(conflicts),
        "secrets_printed": False, "pii_dumped": False, "raw_stem_option_text_in_supply": False,
        "excluded_non_real_exam_objective": all_objective - len(rows),
        "excluded_reason": "source_type != REAL_EXAM (TEXTBOOK/textbook_exercise/TEXTBOOK_ASSESSMENT) -> scope-expansion work_order, NOT signed this round (governance decision pending)",
    }, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "release_candidate_manifest_m25h.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"extracted_real_exam": len(rows), "clean": len(records), "rejected": len(rejected),
                      "conflicts": len(conflicts), "all_objective_all_sources": all_objective,
                      "status": STATUS, "published": False, "content_hash16": content_hash[:16]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
