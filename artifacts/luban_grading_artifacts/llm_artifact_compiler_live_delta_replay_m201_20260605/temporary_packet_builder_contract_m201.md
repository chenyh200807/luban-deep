# Temporary Packet Builder Contract (M20.1)

- Scope: test/script-only M20 delta harness.
- Activation: only inside `run_luban_llm_artifact_compiler_live_delta_replay_m201.py`.
- Explicit live flag: real provider calls only run with `--run-live-delta-replay`.
- Runtime default: unchanged.
- Published registry: unchanged.
- Formal GradingPacket builder: unchanged on disk; monkeypatch is restored after each script run.
- Source truth: M20 deltas are candidate context only and never textbook/spec/list authority.
- Auto permission: M20 deltas cannot raise auto authority; deterministic validator remains safety floor.
- Output provenance: every delta packet has `m20_delta_packet_hash`, `base_packet_hash`, and `delta_ids_applied`.
- Writes: production DB and canonical learner truth writes are forbidden and remain zero.
