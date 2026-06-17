"""Photo-answer OCR input layer.

Plan: docs/plan/2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md
This package turns photographed handwritten case answers into a confirmed_text
payload for the existing grading chain. It never writes learning_evidence and
never re-implements grading (thin wrapper; CaseGradingSkillKernel stays the
single grading authority).
"""
