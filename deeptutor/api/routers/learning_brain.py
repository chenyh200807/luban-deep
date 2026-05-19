from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.schema import CaseGradingResult
from deeptutor.services.construction_grading.writeback import write_grading_error_events
from deeptutor.services.learner_state import get_learner_state_service
from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
from deeptutor.services.runtime_env import env_flag, runtime_environment

router = APIRouter()


class LearningBrainHarnessRequest(BaseModel):
    user_id: str = Field(default="wechat_harness_learning_brain", min_length=1, max_length=120)
    user_answer: str = Field(
        default="应加强现场管理，落实责任，严格检查。",
        min_length=1,
        max_length=1000,
    )
    manual_confirm: bool = False


def render_learning_brain_harness_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>学习大脑 QA</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f8fb; color: #142033; }
    main { max-width: 1040px; margin: 0 auto; padding: 28px 20px 48px; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    h2 { margin: 28px 0 12px; font-size: 18px; }
    label { display: block; margin: 14px 0 6px; font-weight: 650; }
    input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #c8d3e2; border-radius: 8px; padding: 10px 12px; font: inherit; background: white; }
    textarea { min-height: 96px; resize: vertical; }
    button { border: 0; border-radius: 8px; padding: 10px 14px; margin: 12px 8px 0 0; color: white; background: #2563eb; font-weight: 700; cursor: pointer; }
    button.secondary { background: #475569; }
    button.success { background: #15803d; }
    .summary { color: #526173; margin-bottom: 20px; }
    .panel { background: white; border: 1px solid #d9e2ef; border-radius: 10px; padding: 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04); }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .item { border: 1px solid #e0e7f0; border-radius: 8px; padding: 12px; margin: 10px 0; background: #fbfdff; }
    .tag { display: inline-block; border-radius: 999px; padding: 3px 8px; background: #e0f2fe; color: #075985; font-size: 12px; font-weight: 700; }
    .meta { color: #64748b; font-size: 13px; margin-top: 6px; }
    .empty { color: #64748b; padding: 10px 0; }
    @media (max-width: 760px) { .grid { grid-template-columns: 1fr; } main { padding: 20px 14px 36px; } }
  </style>
</head>
<body>
  <main>
    <h1>学习大脑</h1>
    <p class="summary">中文可见链 QA：案例作答 → 阅卷证据 → 学习事实编译 → 下一步训练。</p>
    <section class="panel">
      <label for="userId">学员</label>
      <input id="userId">
      <label for="answer">中文案例作答</label>
      <textarea id="answer">应加强现场管理，落实责任，严格检查。</textarea>
      <button id="runWeak">生成薄弱点</button>
      <button id="runConfirm" class="secondary">老师确认 L2</button>
      <button id="runImprove" class="success">下一题训练改善</button>
      <div id="status" class="meta"></div>
    </section>
    <section class="grid">
      <div>
        <h2>当前可信结论</h2>
        <div id="truths" class="panel"></div>
      </div>
      <div>
        <h2>证据流</h2>
        <div id="evidence" class="panel"></div>
      </div>
      <div>
        <h2>下一步训练</h2>
        <div id="training" class="panel"></div>
      </div>
    </section>
    <section>
      <h2>完整训练链</h2>
      <div id="chain" class="panel"></div>
    </section>
  </main>
  <script>
    const userInput = document.getElementById("userId");
    const answerInput = document.getElementById("answer");
    const statusNode = document.getElementById("status");
    userInput.value = "wechat_harness_learning_brain_" + Date.now();

    function safeText(value) {
      return String(value || "")
        .replace(/wechat-harness-case-(\\d+)/gi, "专项训练 $1")
        .replace(/wechat-harness-learning-brain-[a-z0-9]+-(\\d+)/gi, "第 $1 次作答")
        .replace(/wechat-harness-learning-brain-confirm-[a-z0-9]+/gi, "老师确认")
        .replace(/1A\\d{6}/g, "知识点")
        .replace(/\\bE\\d{2}\\b/g, "错因");
    }
    function item(title, meta, tag) {
      return `<div class="item">${tag ? `<span class="tag">${safeText(tag)}</span>` : ""}<div>${safeText(title)}</div>${meta ? `<div class="meta">${safeText(meta)}</div>` : ""}</div>`;
    }
    function renderList(id, rows, emptyText) {
      document.getElementById(id).innerHTML = rows.length ? rows.join("") : `<div class="empty">${emptyText}</div>`;
    }
    function render(data) {
      const sections = data.visible_sections || {};
      renderList("truths", (sections.current_truth || []).map(x => item(x.display_title || x.current_truth, x.display_meta, x.evidence_level_label)), "暂无稳定结论");
      renderList("evidence", (sections.evidence_flow || []).map(x => item(x.display_title || x.display_label, x.display_path || x.display_meta, x.event_id ? "证据 " + String(x.event_id).slice(0, 8) : "")), "暂无证据流");
      renderList("training", (sections.next_training || []).map(x => item(x.display_title || x.claim, x.display_meta, x.evidence_level_label)), "暂无训练建议");
      const graph = data.graph_chain || {};
      const outcomes = [...(graph.training_improved_error || []), ...(graph.training_not_improved_error || [])];
      renderList("chain", outcomes.map(x => item(x.display_title, x.display_path || x.display_meta, x.edge_type === "training_improved_error" ? "已改善" : "仍需巩固")), "暂无训练结果链");
      statusNode.textContent = `事件 ${data.event_count || 0} 个，关系 ${data.typed_graph_edge_count || 0} 条`;
    }
    async function refresh() {
      const userId = userInput.value.trim();
      const res = await fetch(`/api/v1/learning-brain/harness-projection?user_id=${encodeURIComponent(userId)}`);
      if (!res.ok) throw new Error(await res.text());
      render(await res.json());
    }
    async function grade(answer, manualConfirm) {
      statusNode.textContent = "处理中...";
      const res = await fetch("/api/v1/learning-brain/harness-case-grading", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: userInput.value.trim(), user_answer: answer, manual_confirm: manualConfirm })
      });
      if (!res.ok) throw new Error(await res.text());
      render(await res.json());
    }
    document.getElementById("runWeak").onclick = () => grade(answerInput.value, false).catch(err => statusNode.textContent = err.message);
    document.getElementById("runConfirm").onclick = () => grade(answerInput.value, true).catch(err => statusNode.textContent = err.message);
    document.getElementById("runImprove").onclick = () => grade("应组织专家论证，编制专项施工方案并按规定审批；按专项施工方案实施，验收合格后方可进入下道工序。", false).catch(err => statusNode.textContent = err.message);
    refresh().catch(() => {});
  </script>
</body>
</html>"""


def _qa_enabled() -> bool:
    return runtime_environment() == "local" and env_flag("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", default=False)


def _demo_case_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "wechat-harness-case-001",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证，并编制专项施工方案后按规定审批。",
            "grading_keywords": ["专家论证", "专项施工方案", "审批"],
            "node_code": "1A432000",
            "testing_focus": "危险性较大工程专项方案程序",
        },
        {
            "id": "wechat-harness-case-002",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证，并按专项施工方案实施，验收合格后方可进入下道工序。",
            "grading_keywords": ["专家论证", "专项施工方案", "验收合格"],
            "node_code": "1A432000",
            "testing_focus": "专项方案与验收程序",
        },
    ]


def _visible_grading_result(result: CaseGradingResult, *, write_count: int) -> dict[str, Any]:
    missed_points = [item.criterion for item in result.rubric_items if item.status == "miss"]
    return {
        "question_id": result.question_id,
        "score_awarded": result.score_awarded,
        "max_score": result.max_score,
        "score_label": f"{result.score_awarded:g}/{result.max_score:g}",
        "missed_points": missed_points,
        "rewrite": result.rewrite_answer,
        "next_training_signal": dict(result.next_training_signal or {}),
        "write_count": write_count,
    }


@router.get("/harness-projection")
async def get_learning_brain_projection(
    user_id: str = Query(..., min_length=1, max_length=120),
) -> dict[str, Any]:
    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA projection is disabled")

    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    synthesis = get_learner_state_service().synthesize_learning_truth(
        normalized_user_id,
        dry_run=True,
        event_limit=50,
    )
    projection = dict(synthesis.get("projection") or {})
    return build_learning_brain_read_model(user_id=normalized_user_id, projection=projection, surface="mobile")


@router.post("/harness-case-grading")
async def run_learning_brain_harness_case_grading(
    payload: LearningBrainHarnessRequest,
) -> dict[str, Any]:
    """Dev harness for the visible Learning Brain chain.

    This wrapper owns no grading or memory truth. It only connects the Web QA
    surface to the existing grading, learner-state writeback, and synthesis
    authorities.
    """

    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA harness is disabled")

    user_id = payload.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    kernel = CaseGradingSkillKernel()
    learner_state_service = get_learner_state_service()
    run_id = uuid4().hex[:10]
    visible_results: list[dict[str, Any]] = []
    for index, row in enumerate(_demo_case_rows(), 1):
        result = kernel.grade(question_row=row, user_answer=payload.user_answer)
        source_id = f"wechat-harness-learning-brain-{run_id}-{index}"
        write_count = write_grading_error_events(
            learner_state_service=learner_state_service,
            user_id=user_id,
            grading_result=result,
            source_id=source_id,
            source_bot_id="construction-exam",
            include_success_events=True,
        )
        visible_results.append(_visible_grading_result(result, write_count=write_count))

    manual_confirmation: dict[str, Any] | None = None
    if payload.manual_confirm:
        event = learner_state_service.append_memory_event(
            user_id,
            source_feature="manual_correction",
            source_id=f"wechat-harness-learning-brain-confirm-{run_id}",
            memory_kind="learning_correction",
            payload_json={
                "event_type": "manual_correction",
                "action": "confirm",
                "concept_id": "1A432000",
                "error_code": "E02",
                "correction": "老师确认该学生反复漏写危险性较大工程专项方案程序。",
            },
            dedupe_key=f"{user_id}:wechat-harness-learning-brain-confirm:{run_id}",
        )
        manual_confirmation = {
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "memory_kind": event.memory_kind,
        }

    synthesis = learner_state_service.synthesize_learning_truth(
        user_id,
        dry_run=True,
        event_limit=50,
    )
    projection = dict(synthesis.get("projection") or {})
    read_model = build_learning_brain_read_model(user_id=user_id, projection=projection, surface="mobile")
    graph_chain = dict(read_model.get("graph_chain") or {})
    return {
        **read_model,
        "grading_results": visible_results,
        "manual_confirmation": manual_confirmation,
        "training_uses_question": graph_chain["has_training_uses_question"],
        "training_improved_error": graph_chain["has_training_improved_error"],
        "training_not_improved_error": graph_chain["has_training_not_improved_error"],
    }
