"""Task#22 question_type relabel writer.

Guardrails (every PATCH):
  - id=in.(<explicit whitelist>)              -> cannot touch an unplanned row
  - question_type=eq.case_study               -> cannot double-apply; cannot touch a non-case row
  - source_type=in.(TEXTBOOK,textbook_exercise) -> cannot leak into the 2 skipped (broken-answer) sources
  - Prefer: return=representation             -> read back what PostgREST actually wrote
Any count/readback mismatch => sys.exit non-zero, leaving the scene untouched for inspection.
"""
import json, sys, time
import sbclient as S

NEW = "essay"
GUARD_SOURCES = "TEXTBOOK,textbook_exercise"
CHUNK = 100

def load_batches():
    ids = json.load(open(__import__("os").environ.get("IDFILE","go_ids.json")))
    return [ids[i:i+CHUNK] for i in range(0, len(ids), CHUNK)]

def patch(ids, dry):
    if dry:
        _, rows, _ = S.rest("questions_bank", params={
            "select": "id,question_type,source_type",
            "id": "in.(%s)" % ",".join(map(str, ids)),
            "question_type": "eq.case_study",
            "source_type": "in.(%s)" % GUARD_SOURCES,
            "order": "id.asc"})
        return rows
    _, rows, _ = S.rest("questions_bank", method="PATCH",
        body={"question_type": NEW},
        params={"id": "in.(%s)" % ",".join(map(str, ids)),
                "question_type": "eq.case_study",
                "source_type": "in.(%s)" % GUARD_SOURCES,
                "select": "id,question_type,source_type"},
        prefer="return=representation")
    return rows

def main(dry):
    batches = load_batches()
    total = sum(len(b) for b in batches)
    print(f"batches={len(batches)} rows_planned={total} dry={dry} new_value={NEW}", flush=True)
    written, log, t0 = [], [], time.time()
    for n, ids in enumerate(batches, 1):
        got = patch(ids, dry)
        if len(got) != len(ids):
            print(json.dumps({"FATAL": "touched %d != planned %d" % (len(got), len(ids)),
                              "batch": n, "ids": ids}, ensure_ascii=False)); sys.exit(2)
        for g in got:
            want = "case_study" if dry else NEW
            if g["question_type"] != want:
                print(json.dumps({"FATAL": "readback mismatch", "row": g}, ensure_ascii=False)); sys.exit(3)
            if g["source_type"] not in ("TEXTBOOK", "textbook_exercise"):
                print(json.dumps({"FATAL": "source guard leaked", "row": g}, ensure_ascii=False)); sys.exit(4)
        written += [g["id"] for g in got]
        log.append({"batch": n, "ids": ids, "returned": len(got)})
        print(f"  batch {n}/{len(batches)} rows={len(written)} {time.time()-t0:.1f}s", flush=True)
    assert len(written) == total and len(set(written)) == total, "duplicate or missing row"
    res = {"new_value": NEW, "dry": dry, "rows_written": len(written), "batches": len(batches),
           "elapsed_s": round(time.time()-t0, 1)}
    if not dry:
        json.dump({**res, "log": log, "ids": sorted(written)},
                  open("writelog_task22_relabel.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    main("--dry" in sys.argv)
