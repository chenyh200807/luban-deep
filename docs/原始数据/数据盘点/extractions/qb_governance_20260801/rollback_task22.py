"""Rollback for Task#22 relabel: essay -> case_study, for exactly the 627 written ids.

Guarded the same way as the forward write: id whitelist + question_type=eq.essay +
source_type guard. Running it twice is a no-op (second run matches 0 rows).
Authority for the old value: public.questions_bank_qtype_backup_20260801 (627 rows,
old_question_type all 'case_study') and backup_task22_rows.jsonl.gz (full 33-col snapshot).
Usage:  python3 rollback_task22.py --confirm
"""
import json, sys, sbclient as S

def main():
    if "--confirm" not in sys.argv:
        print("refusing to run without --confirm"); sys.exit(1)
    ids = json.load(open("writelog_task22_relabel.json"))["ids"] + json.load(open("canary_done.json"))
    ids = sorted(set(ids))
    assert len(ids) == 627, len(ids)
    # old value must be uniform in the backup table before we trust a blanket restore
    chk = S.mgmt_sql("select count(*) n, count(distinct old_question_type) k, min(old_question_type) v "
                     "from public.questions_bank_qtype_backup_20260801;")[1][0]
    assert chk["n"] == 627 and chk["k"] == 1 and chk["v"] == "case_study", chk
    restored = []
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        _, rows, _ = S.rest("questions_bank", method="PATCH", body={"question_type": "case_study"},
            params={"id": "in.(%s)" % ",".join(map(str, chunk)),
                    "question_type": "eq.essay",
                    "source_type": "in.(TEXTBOOK,textbook_exercise)",
                    "select": "id,question_type"}, prefer="return=representation")
        assert all(r["question_type"] == "case_study" for r in rows), rows[:3]
        restored += [r["id"] for r in rows]
        print(f"  restored {len(restored)}/{len(ids)}", flush=True)
    print(json.dumps({"restored": len(restored), "expected": 627}))
if __name__ == "__main__":
    main()
