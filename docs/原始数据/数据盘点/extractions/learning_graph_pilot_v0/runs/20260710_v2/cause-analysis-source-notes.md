# Cause analysis source notes

- Audience: product stakeholders.
- Question: why the graph arm underperformed, and whether DeepTutor should still build a learning-reference module.
- Controlling metric source: `evaluation.json`; 20 paired cases, same model and prompt scaffold, baseline 17/20, graph 16/20.
- Case evidence: `report.md` and `outputs.internal.jsonl`; NP-02 is graph-specific over-traversal, NP-04 graph win, NP-11 graph schema invalid, NP-18/NP-19 shared direct-target misses.
- Chart contract: category comparison, horizontal bar, accuracy by arm, n=20 paired cases; zero baseline retained; single blue root plus neutral comparator; exact labels; output `cause-analysis-report.html`.
- The bar chart is intentionally limited to the two observed arms. Driver evidence uses a table because drivers are categorical mechanisms, not additive quantified contributions.
- Causal limit: this realized run cannot distinguish graph structure from extra structured text, and gold was not encrypted before the run.
- Recommended architecture is inference, not implemented fact: signed static graph supplies the map; approved learner evidence supplies position; one fat `NextBestLearningSkill` owns the ephemeral recommendation.
