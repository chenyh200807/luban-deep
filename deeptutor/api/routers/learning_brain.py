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
    # AI-Draft shadow mode (QA-gated, dry_run, candidate_only). Default "kernel" preserves
    # the original harness behavior exactly. ai_draft does NOT write learner_memory_events
    # this round and never touches CaseGradingSkillKernel authority.
    mode: str = "kernel"
    case_id: str | None = None
    writeback: bool = False
    # engine selector for mode=ai_draft. Default deepseek_fast preserves existing behavior.
    # best_quality_4model adjudicates GPT5.5+Opus4.8+DeepSeek-V4+Qwen3.7 (test-only, highest capability).
    engine: str = "deepseek_fast"
    student_id: str | None = None


# Monkeypatchable grader hooks so tests can exercise the branches without live model calls.
def _ai_draft_grader(case_row: dict[str, Any], answer: str) -> dict[str, Any]:
    from scripts.run_luban_ai_draft_grading import ai_draft_grade  # lazy: dev harness only
    return ai_draft_grade(case_row, answer, student_id="harness")


def _best_quality_grader(case_row: dict[str, Any], student_id: str | None) -> dict[str, Any]:
    # Adjudicates cached real 4-model predictions. Raises BestQualityUnavailable -> fail closed.
    from deeptutor.services.construction_grading.best_quality_ai_draft import best_quality_for_golden
    return best_quality_for_golden(case_row, student_id=student_id)


def _golden_case(case_id: str | None) -> dict[str, Any] | None:
    import json
    from pathlib import Path
    fixture = Path(__file__).resolve().parents[3] / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
    if not fixture.exists():
        return None
    cases = json.loads(fixture.read_text(encoding="utf-8")).get("cases", [])
    if case_id:
        return next((c for c in cases if c.get("case_id") == case_id), None)
    return cases[0] if cases else None


def _run_ai_draft_harness(payload: "LearningBrainHarnessRequest") -> dict[str, Any]:
    """AI-Draft shadow path: candidate_only / dry_run / no writeback / no kernel touch.
    engine=deepseek_fast (default, single model) | best_quality_4model (adjudicated jury)."""
    case = _golden_case(payload.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="golden case not available for ai_draft mode")

    engine = payload.engine or "deepseek_fast"
    if engine == "best_quality_4model":
        from deeptutor.services.construction_grading.best_quality_ai_draft import BestQualityUnavailable
        try:
            draft = _best_quality_grader(case, payload.student_id)
        except BestQualityUnavailable as exc:
            # FAIL CLOSED — never impersonate best-quality with a single DeepSeek pass
            raise HTTPException(status_code=503, detail={"error": "best_quality_unavailable", "reason": str(exc)})
        authority = "best_quality_4model_shadow"
    elif engine == "deepseek_fast":
        draft = _ai_draft_grader(case, payload.user_answer)
        authority = "ai_draft_shadow"
    else:
        raise HTTPException(status_code=400, detail=f"unknown engine: {engine}")

    # QuestionGradingArtifact runtime gate (single rule for BOTH engines). The grader
    # wrappers keep their signatures; the gate is applied post-hoc to the assembled
    # draft here. published -> point-level auto allowed; draft/blocked/missing -> no
    # point may auto-certify (fail closed). The gate only downgrades, never upgrades.
    from deeptutor.services.construction_grading.artifact_runtime_gate import (
        apply_runtime_artifact_gate,
        resolve_runtime_artifact_gate,
    )

    gate = resolve_runtime_artifact_gate(case.get("case_id"))
    draft = apply_runtime_artifact_gate(draft, gate)

    return {
        "authority": authority,
        "engine": engine,
        "prediction_source": draft.get("prediction_source", "live_deepseek" if engine == "deepseek_fast" else "cached_4model_485"),
        "model_set": draft.get("model_set"),
        "candidate_only": True,
        "not_production_grade": True,
        "dry_run": True,
        "writeback_performed": False,
        "writeback_requested_ignored_this_round": bool(payload.writeback),
        "mode": "ai_draft",
        "case_id": case.get("case_id"),
        "artifact_gate": draft.get("artifact_gate"),
        "model_draft_score": draft.get("model_draft_score"),
        "auto_certified_score": draft.get("auto_certified_score"),
        "pending_review_score": draft.get("pending_review_score"),
        "bad_certified_count": draft.get("bad_certified_count", 0),
        "metric_gate": draft.get("metric_gate"),
        "parse_status": draft.get("parse_status"),
        "point_results": draft.get("point_results", []),
        "learning_evidence_payload_preview": draft.get("learning_evidence_payload_preview"),
        "note": "AI-Draft is a shadow assembler; it does NOT replace CaseGradingSkillKernel and writes nothing this round.",
    }


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
    input, textarea, select { width: 100%; box-sizing: border-box; border: 1px solid #c8d3e2; border-radius: 8px; padding: 10px 12px; font: inherit; background: white; }
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
    .score-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin:10px 0; }
    .score-card { border:1px solid #e0e7f0; border-radius:8px; padding:10px; background:#fbfdff; text-align:center; }
    .score-card b { font-size:22px; display:block; margin-top:4px; }
    .pt { border:1px solid #e0e7f0; border-radius:8px; padding:12px; margin:10px 0; }
    .st-auto { border-left:4px solid #15803d; }
    .st-pending { border-left:4px solid #d97706; background:#fffbeb; }
    .st-unsupported { border-left:4px solid #dc2626; background:#fef2f2; }
    .badge { display:inline-block; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:700; }
    .b-auto { background:#dcfce7; color:#166534; } .b-pending { background:#fef3c7; color:#92400e; } .b-unsupported { background:#fee2e2; color:#991b1b; }
    .ev { background:#fff7ed; border:1px dashed #fdba74; padding:6px 8px; border-radius:6px; margin:6px 0; }
    .ev mark { background:#fde68a; padding:0 2px; }
    .tr-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }
    .tr-row select, .tr-row input { width:auto; }
    .review-box { margin-top:12px; border:1px solid #bfdbfe; border-radius:8px; padding:12px; background:#eff6ff; }
    .review-box label { margin:0; display:flex; gap:8px; align-items:center; font-weight:650; }
    .review-box input[type="checkbox"] { width:auto; }
    .review-pending { color:#92400e; font-weight:700; }
    .teacher-note { min-width:220px; }
    .evidence-span { background:#fff7ed; border:1px dashed #fdba74; padding:6px 8px; border-radius:6px; margin:6px 0; }
    .next-suggestion { background:#ecfdf5; border-color:#86efac; }
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
    <section class="panel" style="margin-top:24px;">
      <h2>鲁班评分引擎 · AI-Draft 阅卷</h2>
      <p class="summary">candidate_only · dry_run · 不写库 · 不替代正式评分 authority。绿=自动认证 / 黄=待复核(非0分) / 红=证据不足。</p>
      <label for="aiEngine">引擎</label>
      <select id="aiEngine">
        <option value="deepseek_fast">DeepSeek Fast（成本最优·未来生产候选）</option>
        <option value="best_quality_4model">Best-Quality 4-Model（GPT5.5+Opus4.8+DeepSeek-V4+Qwen3.7 裁决·当前最高质量·测试用）</option>
      </select>
      <label for="aiCaseId">case_id（留空用第一题）</label>
      <input id="aiCaseId" placeholder="如 Q10-1A422000">
      <label for="aiStudent">student_id（Best-Quality 用缓存四模型预测，评 golden 答案；留空用 S1）</label>
      <input id="aiStudent" placeholder="如 S2">
      <label for="writebackUserId">writeback user_id（QA/test 文件后端，和缓存 student_id 分离）</label>
      <input id="writebackUserId" value="qa_luban_teacher_review_manual_v0">
      <label for="reviewSource">review_source（复核来源 authority；本地 QA 默认 operator_smoke，不冒充真人）</label>
      <select id="reviewSource">
        <option value="operator_smoke" selected>Operator Smoke（工程验证，非真人结论）</option>
        <option value="model_jury_teacher_review">LLM Jury（四模型复核，非真人）</option>
        <option value="manual_qa_teacher">Manual QA Teacher（真人 QA 老师）</option>
      </select>
      <label for="reviewerId">reviewer_id（QA 老师/复核人）</label>
      <input id="reviewerId" placeholder="如 qa_teacher_01">
      <label for="aiAnswer">学生案例题作答（DeepSeek Fast 评此答案；Best-Quality 评 golden 答案）</label>
      <textarea id="aiAnswer" placeholder="粘贴一建《建筑实务》案例题答案…"></textarea>
      <button id="runAiDraft">运行 AI-Draft 阅卷</button>
      <button id="exportReview" class="secondary">导出 teacher review JSON</button>
      <button id="dryRunWriteback" class="secondary">Dry-run 写回预览（不写库）</button>
      <button id="writebackNow" class="success">确认写入 QA/test Learning Brain</button>
      <div id="aiStatus" class="meta"></div>
      <div id="aiSummary"></div>
      <div id="writebackOut" class="panel" style="display:none;margin-top:12px;background:#f0fdf4;border-color:#bbf7d0;"></div>
      <div id="nextSuggestionPreview" class="panel next-suggestion" style="display:none;margin-top:12px;"></div>
      <div id="teacherReviewPanel" class="review-box" style="display:none;">
        <label><input id="teacherReviewedCheckbox" type="checkbox"> teacher_reviewed=true（AI shadow draft 不是最终事实；老师逐点确认/覆盖后才可写 Learning Brain）</label>
        <div class="meta">teacher_final_score preview: <b id="teacherFinalScorePreview">0</b></div>
      </div>
      <div id="aiPoints"></div>
    </section>
  </main>
  <script>
    const userInput = document.getElementById("userId");
    const answerInput = document.getElementById("answer");
    const statusNode = document.getElementById("status");
    userInput.value = "wechat_harness_learning_brain_" + Date.now();

    function safeText(value) {
      return escapeHtml(String(value || "")
        .replace(/wechat-harness-case-(\\d+)/gi, "专项训练 $1")
        .replace(/wechat-harness-learning-brain-[a-z0-9]+-(\\d+)/gi, "第 $1 次作答")
        .replace(/wechat-harness-learning-brain-confirm-[a-z0-9]+/gi, "老师确认")
        .replace(/1A\\d{6}/g, "知识点")
        .replace(/\\bE\\d{2}\\b/g, "错因"));
    }
    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
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

    // ===== 鲁班 AI-Draft 面板 (thin display only; scoring lives in ai_draft_shadow.py) =====
    const AI_ENDPOINT = "/api/v1/learning-brain/harness-case-grading";
    let aiDraftState = null;
    let reviewStartedAt = null;
    function escAi(s){ return String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c])); }
    function highlightSpan(answer, span){
      const a = String(answer||""); const s = String(span||"");
      if(!s) return escAi(a);
      const i = a.indexOf(s);
      if(i<0) return escAi(a);
      return escAi(a.slice(0,i)) + "<mark>" + escAi(s) + "</mark>" + escAi(a.slice(i+s.length));
    }
    function defaultReviewAction(p, gate){
      if((gate.artifact_status||"") !== "published") return "";
      if(p.high_risk_review || p.unsupported) return "";
      if(p.display_status === "auto_certified" && p.auto_certified && p.hit === "hit") return "confirm";
      return "";
    }
    function finalScoreForRow(row, p){
      const action = row.querySelector("[data-review-action]").value;
      const scoreValue = row.querySelector("[data-teacher-score]").value;
      if(action === "override") return scoreValue === "" ? 0 : Number(scoreValue || 0);
      if(action === "confirm") return Number(p.score || 0);
      return 0;
    }
    function updateTeacherFinalPreview(){
      if(!aiDraftState) return;
      const d = aiDraftState.draft;
      const total = Array.from(document.querySelectorAll("#aiPoints .pt")).reduce((sum,row)=>{
        const p = d.point_results[+row.getAttribute("data-idx")];
        return sum + finalScoreForRow(row, p);
      }, 0);
      const node = document.getElementById("teacherFinalScorePreview");
      if(node) node.textContent = String(Math.round(total * 100) / 100);
      const mirror = document.getElementById("teacherFinalScorePreviewMirror");
      if(mirror) mirror.textContent = node ? node.textContent : "0";
    }
    async function runAiDraft(){
      const caseId = document.getElementById("aiCaseId").value.trim();
      const studentId = document.getElementById("aiStudent").value.trim();
      const engine = document.getElementById("aiEngine").value;
      const answer = document.getElementById("aiAnswer").value.trim();
      const st = document.getElementById("aiStatus");
      st.textContent = engine==="best_quality_4model" ? "运行中…(四模型裁决，缓存预测，瞬时)" : "运行中…(DeepSeek 单题约 10-30s)";
      try{
        const res = await fetch(AI_ENDPOINT, {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({mode:"ai_draft", engine:engine, case_id: caseId||null, student_id: studentId||null, user_answer: answer||"（空）", writeback:false})});
        if(!res.ok){ const t=await res.text(); throw new Error("HTTP "+res.status+" "+t.slice(0,160)); }
        const d = await res.json();
        aiDraftState = {draft:d, answer:answer};
        reviewStartedAt = new Date();
        renderAiDraft(d, answer);
        st.textContent = "完成 · engine="+(d.engine||"")+" · "+d.authority+" · 来源="+(d.prediction_source||"")+" · dry_run="+d.dry_run+" · writeback_performed="+d.writeback_performed+" · case="+(d.case_id||"");
      }catch(e){ st.textContent = "错误: "+e.message; }
    }
    function renderAiDraft(d, answer){
      const counts = (d.point_results||[]).reduce((a,p)=>{ a[p.display_status]=(a[p.display_status]||0)+1; return a; }, {});
      const g = d.artifact_gate || {};
      const gateCls = g.artifact_status==="published" ? "b-auto" : (g.artifact_status==="artifact_missing"||g.artifact_status==="blocked" ? "b-unsupported" : "b-pending");
      const gateBanner = "<div class='meta'>artifact_gate: <span class='badge "+gateCls+"'>"+escAi(g.artifact_status||"unknown")+"</span>"
        + " · version "+escAi(g.artifact_version_id||"-")
        + " · auto_certification_allowed="+escAi(String(g.auto_certification_allowed))
        + (g.blocked_reason ? (" · reason: "+escAi(g.blocked_reason)) : "")
        + " · 未 published 的题/点不得自动认证</div>";
      document.getElementById("aiSummary").innerHTML =
        gateBanner
        + "<div class='score-grid'>"
        + "<div class='score-card'>模型草稿分<b>"+escAi(d.model_draft_score)+"</b></div>"
        + "<div class='score-card'>自动认证分<b>"+escAi(d.auto_certified_score)+"</b></div>"
        + "<div class='score-card' style='background:#fffbeb'>待复核分<b>"+escAi(d.pending_review_score)+"</b></div>"
        + "<div class='score-card'>teacher-final预览<b id='teacherFinalScorePreviewMirror'>0</b></div>"
        + "<div class='score-card'>bad_certified<b>"+escAi(d.bad_certified_count)+"</b></div>"
        + "</div>"
        + "<div class='meta'>auto_certified "+(counts.auto_certified||0)+" · pending_review "+(counts.pending_review||0)+" · unsupported "+(counts.unsupported||0)+" · 待复核分为复核分非0</div>";
      document.getElementById("teacherReviewPanel").style.display = "block";
      document.getElementById("teacherReviewedCheckbox").checked = false;
      document.getElementById("writebackOut").style.display = "none";
      document.getElementById("nextSuggestionPreview").style.display = "none";
      document.getElementById("aiPoints").innerHTML = (d.point_results||[]).map((p,idx)=>{
        const cls = p.display_status==="auto_certified" ? "st-auto" : (p.display_status==="unsupported" ? "st-unsupported" : "st-pending");
        const bdg = p.display_status==="auto_certified" ? "b-auto" : (p.display_status==="unsupported" ? "b-unsupported" : "b-pending");
        const reviewAction = defaultReviewAction(p, g);
        const pendingText = reviewAction ? "" : "<span class='review-pending'>pending teacher review</span>";
        const votes = p.model_votes ? Object.keys(p.model_votes).map(m=>m.toUpperCase()+":"+escAi(p.model_votes[m].hit)).join(" / ") : "";
        return "<div class='pt "+cls+"' data-idx='"+idx+"'>"
          + "<div><span class='badge "+bdg+"'>"+escAi(p.display_status)+"</span> "
          + "<span class='tag'>"+escAi(p.policy_type)+"</span> <b>"+escAi(p.point_id)+"</b> "
          + escAi(p.hit)+" · "+escAi(p.score)+"/"+escAi(p.max_score)+"</div>"
          + "<div class='meta'>"+escAi(p.expected_point_label)+"</div>"
          + (p.high_risk_review ? "<div class='meta review-pending'>high_risk_review：默认 pending，不自动 mastery</div>" : "")
          + (p.unsupported ? "<div class='meta review-pending'>unsupported：默认 pending，不自动 mastery</div>" : "")
          + (p.model_votes ? ("<div class='meta model-votes'>四模型: "+votes+" · <b>"+escAi(p.disagreement_summary||"")+"</b></div>") : "")
          + (p.adjudication_reason ? ("<div class='meta'>裁决: "+escAi(p.adjudication_reason)+"</div>") : "")
          + "<div class='ev evidence-span'>证据: "+highlightSpan(answer, p.evidence_span)+"</div>"
          + "<div class='meta'>理由: "+escAi(p.rationale)+(p.review_reason ? (" · review_reason: "+escAi(p.review_reason)) : "")+"</div>"
          + "<div class='meta'>默认复核状态: "+(reviewAction ? "<b>confirm</b>" : pendingText)+"</div>"
          + "<div class='tr-row'>老师复核: "
          + "<select class='tr-action' data-review-action><option value=''>pending</option><option value='confirm' "+(reviewAction==="confirm"?"selected":"")+">confirm AI</option><option value='override'>override</option></select>"
          + "<select class='tr-hit' data-teacher-hit><option value=''>teacher_hit</option><option value='hit'>hit</option><option value='partial'>partial</option><option value='miss'>miss</option></select>"
          + "<input class='tr-score' data-teacher-score type='number' min='0' max='"+escAi(p.max_score)+"' step='0.1' placeholder='teacher_score'>"
          + "<input class='tr-note teacher-note' data-teacher-note placeholder='teacher_note'></div>"
          + "</div>";
      }).join("");
      document.querySelectorAll("#aiPoints [data-review-action], #aiPoints [data-teacher-score]").forEach(el=>el.addEventListener("change", updateTeacherFinalPreview));
      updateTeacherFinalPreview();
      const mirror = document.getElementById("teacherFinalScorePreviewMirror");
      if(mirror) mirror.textContent = document.getElementById("teacherFinalScorePreview").textContent;
    }
    function buildReviewJson(){
      const d = aiDraftState.draft, answer = aiDraftState.answer;
      const point_reviews = Array.from(document.querySelectorAll("#aiPoints .pt")).map(row=>{
        const p = d.point_results[+row.getAttribute("data-idx")];
        const action = row.querySelector("[data-review-action]").value;
        const th = row.querySelector("[data-teacher-hit]").value;
        const ts = row.querySelector("[data-teacher-score]").value;
        const tn = row.querySelector("[data-teacher-note]").value;
        return {point_id:p.point_id, label:p.expected_point_label, policy_type:p.policy_type,
          max_score:p.max_score, ai_hit:p.hit, ai_score:p.score,
          high_risk_review:p.high_risk_review, unsupported:p.unsupported, auto_certified:p.auto_certified,
          model_votes:p.model_votes||null, adjudication_reason:p.adjudication_reason||null,
          teacher_hit: th||null, teacher_score: ts!=="" ? Number(ts) : null,
          teacher_note: tn||null, review_action: action};
      });
      return {engine:d.engine||"deepseek_fast", authority:d.authority, prediction_source:d.prediction_source||null,
        teacher_reviewed:document.getElementById("teacherReviewedCheckbox").checked, case_id:d.case_id, student_id:(document.getElementById("aiStudent").value.trim()||"S1"),
        ...(()=>{const s=(document.getElementById("reviewSource")||{}).value||"operator_smoke";
          const M={manual_qa_teacher:{reviewer_type:"human_qa_teacher",authority_label:"teacher_final",jury_models:[],adjudication_protocol:""},
            model_jury_teacher_review:{reviewer_type:"llm_jury",authority_label:"model_jury_teacher_final",jury_models:["gpt55","opus48","deepseek_v4","qwen37"],adjudication_protocol:"teacher_review_jury_v0"},
            operator_smoke:{reviewer_type:"operator",authority_label:"operator_smoke_final",jury_models:[],adjudication_protocol:""}};
          const p=M[s]||M.operator_smoke;
          return {review_source:s,reviewer_type:p.reviewer_type,authority_label:p.authority_label,jury_models:p.jury_models,adjudication_protocol:p.adjudication_protocol};})(),
        reviewer_id:(document.getElementById("reviewerId").value.trim()||"qa_teacher_review"),
        reviewed_at:new Date().toISOString(),
        review_started_at:reviewStartedAt ? reviewStartedAt.toISOString() : null,
        review_duration_seconds:reviewStartedAt ? Math.max(0, Math.round((Date.now()-reviewStartedAt.getTime())/1000)) : null,
        review_ui_version:"teacher_review_ux_v0",
        student_answer:answer,
        ai_draft_summary:{model_draft_score:d.model_draft_score, auto_certified_score:d.auto_certified_score, pending_review_score:d.pending_review_score, bad_certified_count:d.bad_certified_count},
        point_reviews:point_reviews, not_production_grade:true};
    }
    function exportReview(){
      if(!aiDraftState){ alert("先运行 AI-Draft"); return; }
      const out = buildReviewJson();
      const blob = new Blob([JSON.stringify(out,null,2)], {type:"application/json"});
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "teacher_review_"+(out.case_id||"case")+".json"; a.click();
    }
    async function dryRunWriteback(){
      if(!aiDraftState){ alert("先运行 AI-Draft"); return; }
      const out = document.getElementById("writebackOut");
      out.style.display = "block"; out.innerHTML = "<div class='meta'>Dry-run 预览中…</div>";
      try{
        const res = await fetch("/api/v1/learning-brain/harness-case-grading-review", {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({review:buildReviewJson(), dry_run:true, writeback:false})});
        if(!res.ok){ const t=await res.text(); throw new Error("HTTP "+res.status+" "+t.slice(0,160)); }
        const r = await res.json();
        const s = r.point_event_summary||{};
        out.innerHTML = "<b>Dry-run 写回预览（未真正写库）</b>"
          + "<div class='meta'>authority="+escAi(r.authority)+" · dry_run="+r.dry_run+" · writeback_performed="+r.writeback_performed+"</div>"
          + "<div class='meta'>override "+(s.overridden||0)+" · confirm "+(s.confirmed||0)+" · reject "+(s.rejected||0)+" · 可计 mastery "+(s.mastery_eligible||0)+" · high_risk/unsupported 降权 "+(s.downweighted_high_risk_or_unsupported||0)+"</div>"
          + "<div class='meta'>将写入 learning_evidence 摘要: 题="+escAi(r.case_id)+" · mastery点="+JSON.stringify(r.mastery_point_ids||[])+"</div>"
          + "<div class='meta'>策略: AI未复核="+escAi(r.memory_write_policy.ai_draft_without_teacher_review)+" / high_risk未复核="+escAi(r.memory_write_policy.high_risk_without_teacher_review)+"</div>"
          + "<div class='meta' style='color:#92400e'>仅预览，未写 learner_memory_events。真实写回需 QA/test user + teacher_reviewed=true + dry_run=false。</div>";
      }catch(e){ out.innerHTML = "<div class='meta'>错误: "+escAi(e.message)+"</div>"; }
    }
    async function writebackNow(){
      if(!aiDraftState){ alert("先运行 AI-Draft"); return; }
      if(!document.getElementById("teacherReviewedCheckbox").checked){ alert("请先勾选 teacher_reviewed=true"); return; }
      const out = document.getElementById("writebackOut");
      const next = document.getElementById("nextSuggestionPreview");
      out.style.display = "block"; out.innerHTML = "<div class='meta'>QA/test 写入中…</div>";
      try{
        const rawUser = document.getElementById("writebackUserId").value.trim() || "qa_luban_teacher_review_manual_v0";
        const writeUser = /^(qa_|test_)/i.test(rawUser) ? rawUser : "qa_"+rawUser;
        const res = await fetch("/api/v1/learning-brain/harness-case-grading-review", {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({review:buildReviewJson(), dry_run:false, writeback:true, user_id:writeUser})});
        if(!res.ok){ const t=await res.text(); throw new Error("HTTP "+res.status+" "+t.slice(0,180)); }
        const r = await res.json();
        const s = r.point_event_summary||{};
        out.innerHTML = "<b>Teacher-final 写回结果</b>"
          + "<div class='meta'>authority="+escAi(r.authority)+" · dry_run="+r.dry_run+" · writeback_performed="+r.writeback_performed+" · events="+r.learner_memory_event_count+"</div>"
          + "<div class='meta'>override "+(s.overridden||0)+" · confirm "+(s.confirmed||0)+" · mastery "+(s.mastery_eligible||0)+" · skipped "+(r.skipped_points||[]).length+"</div>";
        next.style.display = "block";
        next.innerHTML = "<b>next suggestion preview</b>"
          + "<div class='meta'>薄弱点优先：复习 teacher_note 指出的官方术语；补练 pending/override 的同类采分点；计算类只按计算证据生成建议，不归为术语错因。</div>"
          + "<div class='meta'>mastery_point_ids="+escAi(JSON.stringify(r.mastery_point_ids||[]))+"</div>";
      }catch(e){ out.innerHTML = "<div class='meta'>错误: "+escAi(e.message)+"</div>"; }
    }
    document.getElementById("runAiDraft").onclick = () => runAiDraft();
    document.getElementById("exportReview").onclick = () => exportReview();
    document.getElementById("dryRunWriteback").onclick = () => dryRunWriteback();
    document.getElementById("writebackNow").onclick = () => writebackNow();
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


def _demo_evidence_rows() -> list[dict[str, Any]]:
    return [
        {
            "source": "kb_chunks",
            "field": "危险性较大工程专项施工方案",
            "content": "危险性较大的分部分项工程应编制专项施工方案，超过一定规模的应组织专家论证。",
        }
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

    Latency note: this endpoint intentionally runs the full grading + writeback +
    synthesis chain end-to-end so the visible-chain mirror exercises real
    authorities. It is a dev-only harness (gated by ``_qa_enabled()``), not a
    production hot path; production grading goes through the capability +
    TutorBot loop, not this endpoint.
    """

    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA harness is disabled")

    user_id = payload.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # AI-Draft shadow branch (candidate_only / dry_run / no writeback / no kernel touch).
    # mode != "ai_draft" falls through to the original kernel harness behavior unchanged.
    if payload.mode == "ai_draft":
        return _run_ai_draft_harness(payload)

    kernel = CaseGradingSkillKernel()
    learner_state_service = get_learner_state_service()
    run_id = uuid4().hex[:10]
    visible_results: list[dict[str, Any]] = []
    for index, row in enumerate(_demo_case_rows(), 1):
        result = kernel.grade(question_row=row, user_answer=payload.user_answer, evidence_rows=_demo_evidence_rows())
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


class TeacherReviewWritebackRequest(BaseModel):
    """QA-panel teacher review submission. dry_run preview by default; writeback only
    when QA enabled AND teacher_reviewed AND writeback=true."""
    review: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    writeback: bool = False
    user_id: str = Field(default="qa_teacher_review", min_length=1, max_length=120)


# Monkeypatchable hook (tests don't hit a real LearnerStateService).
def _teacher_review_grader(review: dict[str, Any], *, dry_run: bool,
                           learner_state_service: Any | None, user_id: str | None) -> dict[str, Any]:
    from deeptutor.services.construction_grading.teacher_review_writeback import build_teacher_review_writeback
    return build_teacher_review_writeback(review, dry_run=dry_run, learner_state_service=learner_state_service, user_id=user_id)


@router.post("/harness-case-grading-review")
async def run_learning_brain_teacher_review_writeback(payload: TeacherReviewWritebackRequest) -> dict[str, Any]:
    """Teacher-review writeback (QA-only). AI-Draft alone is never written; only a
    teacher-reviewed result becomes learning evidence, via the EXISTING writeback path."""
    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA harness is disabled")
    review = payload.review or {}
    if review.get("teacher_reviewed") is not True:
        raise HTTPException(status_code=400, detail="teacher_reviewed must be true")
    user_id = payload.user_id.strip()
    if bool(payload.writeback) and not payload.dry_run and not _is_qa_teacher_review_user_id(user_id):
        raise HTTPException(status_code=400, detail="writeback user_id must be QA/test scoped")

    # validate teacher overrides at the boundary: hit in {hit,partial,miss}, score in [0,max_score]
    for pr in (review.get("point_reviews") or []):
        if str(pr.get("review_action") or "").lower() == "override":
            if str(pr.get("teacher_hit") or "") not in ("hit", "partial", "miss"):
                raise HTTPException(status_code=400, detail=f"{pr.get('point_id')}: invalid teacher_hit")
            ts, mx = pr.get("teacher_score"), pr.get("max_score")
            if ts is not None and mx is not None:
                try:
                    if float(ts) < 0 or float(ts) > float(mx) + 1e-9:
                        raise HTTPException(status_code=400, detail=f"{pr.get('point_id')}: teacher_score out of [0,{mx}]")
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"{pr.get('point_id')}: teacher_score not a number")

    do_write = bool(payload.writeback) and not payload.dry_run

    learner_state_service = get_learner_state_service() if do_write else None
    try:
        result = _teacher_review_grader(review, dry_run=not do_write,
                                        learner_state_service=learner_state_service, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    plan = result.get("write_plan", [])
    summary = {
        "overridden": sum(1 for r in plan if r.get("authority") == "teacher_override"),
        "rejected": sum(1 for r in plan if r.get("authority") == "teacher_reject"),
        "confirmed": sum(1 for r in plan if r.get("authority") in ("teacher_confirm", "ai_draft")),
        "mastery_eligible": sum(1 for r in plan if r.get("mastery_eligible")),
        "downweighted_high_risk_or_unsupported": sum(1 for r in plan if r.get("disposition", "").startswith("downweighted")),
    }
    memory_event_count = int(result.get("writeback_count", 0))
    skipped_points = [
        {
            "point_id": row.get("point_id"),
            "reason": row.get("disposition"),
            "high_risk_review": bool(row.get("high_risk_review")),
            "unsupported": bool(row.get("unsupported")),
            "authority": row.get("authority"),
        }
        for row in plan
        if not row.get("mastery_eligible")
    ]
    return {
        "authority": "teacher_reviewed_grading",
        "qa_gated": True,
        "dry_run": result.get("dry_run", True),
        "writeback_performed": do_write and memory_event_count > 0,
        "learner_memory_event_count": memory_event_count,
        "writeback_count": memory_event_count,
        "case_id": result.get("case_id"),
        "engine": result.get("engine"),
        "point_event_summary": summary,
        "skipped_points": skipped_points,
        "mastery_point_ids": result.get("mastery_point_ids", []),
        "write_plan": plan,
        "learning_evidence_payload_preview": result.get("learning_evidence_payload"),
        "memory_write_policy": {
            "ai_draft_without_teacher_review": "not_written",
            "high_risk_without_teacher_review": "downweighted_not_mastery",
            "unsupported_without_teacher_review": "downweighted_not_mastery",
            "teacher_reviewed": "eligible",
        },
        "note": "Teacher-final is the higher authority; AI-Draft alone is never written. Reuses existing learning_evidence/learner_memory_events; no new table.",
    }


def _is_qa_teacher_review_user_id(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith(("qa_", "test_"))
