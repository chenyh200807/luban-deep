import json
import subprocess


SCRIPT = "scripts/run_luban_m35_shadow_effectiveness_ab.py"


def test_shadow_effectiveness_marks_shadow_candidate_and_runs_executable_arms(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_rows = [
        {
            "answer_id": "A1",
            "question_id": "Q1",
            "student_answer": "甲 乙",
            "label_authority": "ai_governed_gold",
            "directionality_flag": "ai_governed_gold",
            "is_release_truth": False,
            "official_score_allowed": False,
            "quality_claim_allowed": False,
            "sample_bucket": "hit",
            "gold_point_matches": [
                {
                    "point_id": "Q1::SP1",
                    "status": "hit",
                    "max_score": 2.0,
                    "awarded_score": 2.0,
                }
            ],
        }
    ]
    (source / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in source_rows) + "\n",
        encoding="utf-8",
    )
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "source.v1",
                "is_release_truth": False,
                "official_score_allowed": False,
                "quality_claim_allowed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "Q1",
                        "stem": "题干",
                        "scoring_points": [
                            {
                                "point_id": "Q1::SP1",
                                "criterion": "甲；乙",
                                "max_score": 2.0,
                                "policy_type": "qualitative",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    shadow = tmp_path / "shadow"

    subprocess.run(
        [
            "python3",
            SCRIPT,
            "--source-gold-dir",
            str(source),
            "--shadow-output-dir",
            str(shadow),
            "--manifest",
            str(manifest),
            "--rag-corpus-root",
            str(tmp_path / "missing_corpus"),
            "--output",
            str(output),
        ],
        check=True,
    )

    shadow_rows = [
        json.loads(line)
        for line in (shadow / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert shadow_rows[0]["label_authority"] == "shadow_candidate_gold"
    assert shadow_rows[0]["source_label_authority"] == "ai_governed_gold"
    assert shadow_rows[0]["is_release_truth"] is False

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["reference"]["authority"] == "shadow_candidate_gold"
    assert report["arms"]["legacy_keyword_projection"]["status"] == "exercised"
    assert report["arms"]["artifact_first_compiled"]["status"] == "exercised"
    assert report["arms"]["current_rag"]["status"] == "not_exercised"
    assert report["safety"]["provider_call_count"] == 0


def test_current_rag_offline_adapter_exercises_local_corpus(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "student_answers.jsonl").write_text(
        json.dumps(
            {
                "answer_id": "A1",
                "question_id": "Q1",
                "student_answer": "甲 乙",
                "label_authority": "ai_governed_gold",
                "gold_point_matches": [
                    {
                        "point_id": "Q1::SP1",
                        "status": "hit",
                        "max_score": 2.0,
                        "awarded_score": 2.0,
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (source / "manifest.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "Q1",
                        "stem": "甲乙施工管理题",
                        "scoring_points": [
                            {
                                "point_id": "Q1::SP1",
                                "criterion": "甲；乙",
                                "max_score": 2.0,
                                "policy_type": "qualitative",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "FINAL_CLEANED_EXAM_V2099.json").write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "C1",
                        "source_meta": {"exam_year": 2099, "source": "local fixture"},
                        "content_markdown": "甲乙施工管理题依据：甲；乙。",
                        "exercises": [
                            {
                                "type": "case_study",
                                "question_data": {
                                    "stem": "甲乙施工管理题",
                                    "correct_answer": "甲；乙",
                                    "analysis": "甲乙均为得分依据。",
                                },
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    subprocess.run(
        [
            "python3",
            SCRIPT,
            "--source-gold-dir",
            str(source),
            "--shadow-output-dir",
            str(tmp_path / "shadow"),
            "--manifest",
            str(manifest),
            "--rag-corpus-root",
            str(corpus),
            "--output",
            str(output),
        ],
        check=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["arms"]["current_rag"]["status"] == "exercised"
    assert report["arms"]["current_rag"]["sample_count"] == 1
    assert report["rows_sample"]["current_rag"][0]["retrieval"]["source_count"] == 1
    assert report["safety"]["provider_call_count"] == 0


def test_artifact_first_guard_suppresses_low_coverage_false_positive(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "student_answers.jsonl").write_text(
        json.dumps(
            {
                "answer_id": "A1",
                "question_id": "Q1",
                "student_answer": "甲项",
                "label_authority": "ai_governed_gold",
                "gold_point_matches": [
                    {
                        "point_id": "Q1::SP1",
                        "status": "miss",
                        "max_score": 3.0,
                        "awarded_score": 0.0,
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (source / "manifest.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "Q1",
                        "stem": "题干",
                        "scoring_points": [
                            {
                                "point_id": "Q1::SP1",
                                "criterion": "甲项；乙项；丙项；丁项；戊项；己项；庚项；辛项；壬项；癸项",
                                "max_score": 3.0,
                                "policy_type": "qualitative",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    subprocess.run(
        [
            "python3",
            SCRIPT,
            "--source-gold-dir",
            str(source),
            "--shadow-output-dir",
            str(tmp_path / "shadow"),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
        check=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    artifact_row = report["rows_sample"]["artifact_first_compiled"][0]
    prediction = artifact_row["predictions"]["Q1::SP1"]
    assert prediction["status"] == "miss"
    assert prediction["score"] == 0.0
    assert prediction["guard"]["decision"] == "downgraded_low_evidence_coverage"
    assert report["arms"]["artifact_first_compiled"]["fail_open_rate"] == 0.0
