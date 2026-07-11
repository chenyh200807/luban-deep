# 鲁班首次体验 × 五模块原生旅程实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. owner 已于 2026-07-11 授权 commit、review、push、开 PR 并合并 main；仍未授权部署。本轮继续由当前会话 inline execution，不使用 subagent。

**Goal:** 把老蓝最终版首次体验适配为五模块「学习」首页的原生首段旅程，并在报告完成时一次性、幂等写回 canonical Learner State。

**Architecture:** 以当前五模块产品视觉线 `origin/luban/seethrough-visuals-on-main@22c2a218` 为实施基线；名义 `origin/main@b3e9ab09` 尚未包含这 15 个五模块视觉/看穿学习提交，因此不能再把它当成正确 UI 基线。小程序负责 UI、本地断点和一次完成提交；`POST /api/v1/first-run/complete` 是薄边界；`FirstRunWritebackService` 以 signed manifest 重新判定并写入既有 learner events/profile/home personalization，`home_next_step_projection` 继续是唯一下一步仲裁。第 4 题双教研 verdict 未完成前，服务端必须 fail closed，代码可以完成但不得宣称 production-ready。未来进入 `main` 前必须先把产品视觉线与 `origin/main` 的 2 个独有提交做显式整合，禁止退回旧 TabBar。

**Tech Stack:** Python 3.11、FastAPI/Pydantic、pytest、DeepTutor Learner State services、微信小程序原生 JavaScript/WXML/WXSS、Node VM contract tests、微信开发者工具 CLI。

## Execution status（2026-07-11）

| Task | 状态 | 当前证据 |
|---|---|---|
| 1. canonical manifest | Complete | 4 个稳定 question ID/content hash；默认 `blocked_pending_human_verdict`；manifest 测试通过 |
| 2. 幂等写回 authority | Complete | server re-score、same-body replay、conflict、partial-crash retry、Learner State evidence/profile/home projection 测试通过 |
| 3. 薄 API 与 contract | Complete | `/api/v1/first-run/complete`、严格 model、409/422/503；contract/route/schema/mirror gates 通过 |
| 4. 前端 API/本地状态 | Complete | DONE 降级 UI cache；checkpoint/pending/done 以 canonical user 隔离；注册后统一进入学习首页 |
| 5. 学习首页入口 | Complete | 首次/续做/同步中/blocked/已完成状态；pending 幂等重试；五 Tab 由学习首页恢复 |
| 6. 原生旅程适配 | Complete | paper-ink 五模块视觉；自定义安全区顶栏；一页一题；报告完成一次提交；返回学习首页 |
| 7. 联调与真实入口 | Local authenticated PASS / release blocked | 正确 DevTools 项目根真实走通首次旅程；隔离 `qa_eval` 账号登录本地 authority 成功，课程/首页/学情三条请求均 200，学习→复习→问鲁班→学情→我的五 Tab 全部可进入。首次完成接口实测继续以 `409 first_run_content_not_signed` 诚实阻断；4 题仍待双教研 signed verdict |
| 8. 首次完成与旧摸底收权 | Complete | `/assessment/profile` 只读投影 canonical `learner_state.learning_preferences.first_run`；问鲁班以该服务端完成事实抑制旧 8 分钟摸底弹窗，跨设备不依赖本地 DONE；服务与前端 authority tests 通过 |

当前终态：`implemented_and_local_authenticated_pass_but_content_release_blocked`。`real_wechat_package` 页面级旅程与本地 auth-chain 均 PASS；唯一剩余内容启用 stop condition 是四题双教研 signed verdict。owner 已授权把 fail-closed 代码候选合入 main，但未授权部署或开启 unsigned 内容。

本轮 fresh verification（rebase 到最新 `origin/main` 后）：后端/五模块聚焦集 `238 passed`，另有依赖本机只读教材权威库的 concept-card 编译器 `22 passed`；首次旅程、学习入口、注册、五 Tab shell、首页 prompt、旧摸底 authority、learn/review/errorbank/gauntlet view model、seethrough page 共 12 个 Node 脚本 exit 0；exact CI contract、schema、REST route、runtime assets、Ruff、secret scan、双 index mirror、whitespace gate 全部通过。DevTools 真页面验证：答题态五 Tab 隐藏，`稍后 -> 回学习` 后恢复五 Tab；首次体验适配未覆盖正确基线的 TabBar 实现。

## Global Constraints

- 正确产品视觉基线：`origin/luban/seethrough-visuals-on-main@22c2a218`；名义 `origin/main@b3e9ab09` 缺少当前五模块 TabBar/看穿学习等 15 个提交，旧实施树只保留作对照，不再继续开发。
- 隔离工作树：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-first-run-current-five-module`；目标分支：`codex/first-run-current-five-module`。
- 一等事实：canonical learner 完成某版本首次诊断并形成可追溯学习证据与显式偏好。
- 唯一 writer：`FirstRunWritebackService`；前端不提交正式分数、正确性、mastery、training intent 或 next step。
- 完成语义：报告完成时一次提交；中途只保留按 canonical user 隔离的本地 checkpoint，不建服务端中途 session。
- UI：学习首页入口；答题时隐藏五 Tab，完成/退出后恢复；严格一页一题；当前题反馈可滚动但不能滚到下一题。
- 内容：最大程度保留最终版三问、资料揭示、四题、逐项拆解、采分点/来源/量尺、口诀、四次侧写、画像、完整报告、次日复测钩子。
- 内容门：四题必须全部有稳定 first-run question ID、source refs、content hash 和双教研 signed verdict；缺任一项时 completion fail closed。
- 幂等：同一 `canonical_user_id + completion_id + script_version` 同 body 重放返回同一结果；不同 body 返回 409。
- Learner State：仅复用 `learner_memory_events`、profile、training intent、home personalization；禁止第二 learner table 和第二 recommendation authority。
- Contract：修改 `contracts/index.yaml` 时同步 `deeptutor/contracts/index.yaml`；protected domain 变更必须同步测试并运行 contract guard。
- 微信真实入口：DevTools `--project` 必须指向 `yousenwebview` 根；目标分包为 `packageDeeptutor`；仅 `islogin`/`open` 不算场景 PASS。
- Git：本任务已获 owner 明确授权 commit、review、push、PR merge main；只提交本任务文件，部署仍排除在本轮之外。

---

## File map

### 新建

- `deeptutor/services/first_run/__init__.py`：导出 manifest 与 writeback 公共接口。
- `deeptutor/services/first_run/script_manifest.v1.json`：首次体验唯一内容/答案/签发 manifest。
- `deeptutor/services/first_run/manifest.py`：加载、hash 校验、signed gate、server-side scoring。
- `deeptutor/services/first_run/writeback.py`：唯一完成写回 authority。
- `deeptutor/services/first_run/status.py`：从 canonical Learner State profile 只读投影首次完成事实，供旧摸底兼容入口收权。
- `tests/services/first_run/test_manifest.py`：内容 ID、hash、题集完整性、未签发 fail-closed。
- `tests/services/first_run/test_writeback.py`：重新判定、幂等 replay/conflict、profile 与首页投影。
- `tests/services/first_run/test_status.py`：首次完成事实投影 fail-closed 与 provenance。
- `tests/api/test_mobile_first_run.py`：鉴权、请求边界、HTTP 错误语义。
- `yousenwebview/tests/test_first_run_native_journey.js`：一页一题、本地断点、一次提交、回学习首页。
- `yousenwebview/tests/test_learn_first_run_entry.js`：学习首页入口与同步状态。

### 修改

- `deeptutor/api/routers/mobile.py`：新增 request model 与薄 completion endpoint。
- `contracts/index.yaml`：注册 `/api/v1/first-run`、`first_run_diagnostic` evidence source 与 learner_state test file。
- `deeptutor/contracts/index.yaml`：与根 contract index 字节同步。
- `contracts/schema_registry.yaml`：注册 `first_run_completion.v1` 稳定边界 schema。
- `contracts/learner-state.md`：记录首次诊断 writer、信号分层与完成幂等语义。
- `yousenwebview/packageDeeptutor/utils/api.js`：新增 `completeFirstRun(payload)`。
- `yousenwebview/packageDeeptutor/utils/first-run-entry.js`：本地 checkpoint/pending sync key；DONE 降级为 UI cache。
- `yousenwebview/packageDeeptutor/pages/register/register.js`：注册成功进入学习首页，不再直跳独立 onboarding。
- `yousenwebview/packageDeeptutor/pages/learn/learn.js`：首页首次旅程入口、pending sync 重试、完成后刷新。
- `yousenwebview/packageDeeptutor/pages/learn/learn.wxml`：纸墨朱竹首次旅程卡。
- `yousenwebview/packageDeeptutor/pages/learn/learn.wxss`：复用现有 paper-ink token 的卡片状态。
- `yousenwebview/packageDeeptutor/pages/first-run/script-data.js`：加入 manifest version、canonical IDs、source refs；删除正式 `rx` authority。
- `yousenwebview/packageDeeptutor/pages/first-run/first-run.js`：单题状态机、安全区、本地恢复、完成提交、同步状态与回学习首页。
- `yousenwebview/packageDeeptutor/pages/first-run/first-run.wxml`：固定头部、一页一题、当前题反馈、完整报告。
- `yousenwebview/packageDeeptutor/pages/first-run/first-run.wxss`：五模块纸墨朱竹适配、固定 viewport 与反馈滚动区。
- `yousenwebview/packageDeeptutor/pages/first-run/first-run.json`：自定义导航/页面配置。
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`：只认服务端 `diagnostic_sources.first_run`，抑制完成后第二套摸底 onboarding。
- `yousenwebview/tests/test_chat_diagnostic_authority.js`：首次完成后不再弹旧摸底框。
- `docs/plan/鲁班移动端提分闭环/2026-07-11-first-run-four-question-dual-teacher-review-packet.md`：四题逐题来源、hash、风险与双 reviewer 签发位。
- `docs/plan/INDEX.md`：登记本实施计划与实际状态。
- `docs/plan/鲁班移动端提分闭环/implementation-notes.md`：按实际发现追加 deviation，不预写成功。

---

### Task 1: 建立 canonical manifest 与签发阻断门

**Files:**
- Create: `deeptutor/services/first_run/script_manifest.v1.json`
- Create: `deeptutor/services/first_run/manifest.py`
- Create: `deeptutor/services/first_run/__init__.py`
- Create: `tests/services/first_run/test_manifest.py`

**Interfaces:**
- Produces: `load_first_run_manifest() -> dict[str, Any]`
- Produces: `score_first_run_answers(*, script_version: str, answers: list[dict[str, Any]]) -> list[dict[str, Any]]`
- Raises: `FirstRunManifestUnsigned`, `FirstRunManifestVersionConflict`, `FirstRunAnswerSetInvalid`
- Consumer: Task 2 `FirstRunWritebackService.complete()`

- [ ] **Step 1: 写 manifest RED 测试**

```python
def test_manifest_exposes_four_stable_question_ids_and_hashes() -> None:
    manifest = load_first_run_manifest()
    assert manifest["schema_id"] == "first_run_script.v1"
    assert [item["question_id"] for item in manifest["questions"]] == [
        "first_run.v1:qigu_gebu",
        "first_run.v1:zhiliang_jihua",
        "first_run.v1:tianchongqiang_fangbie",
        "first_run.v1:zhuangpeishi_laji",
    ]
    assert all(len(item["content_sha256"]) == 64 for item in manifest["questions"])


def test_unsigned_question_blocks_server_scoring() -> None:
    with pytest.raises(FirstRunManifestUnsigned, match="zhuangpeishi_laji"):
        score_first_run_answers(
            script_version=load_first_run_manifest()["script_version"],
            answers=_four_valid_answers(),
        )
```

- [ ] **Step 2: 运行 RED**

Run: `pytest -q tests/services/first_run/test_manifest.py`

Expected: FAIL during import because `deeptutor.services.first_run` does not exist.

- [ ] **Step 3: 写唯一 manifest 与加载器**

Manifest 固定四个 first-run canonical IDs；source refs 使用现有真题资产，不把旧 `slug` 当 source authority：

```json
{
  "schema_id": "first_run_script.v1",
  "script_version": "first_run_script.v1@<computed-manifest-sha256>",
  "release_status": "blocked_pending_human_verdict",
  "questions": [
    {
      "question_id": "first_run.v1:qigu_gebu",
      "source_question_id": "Q18-1A434000",
      "source_scoring_point_id": "Q18-1A434000::P11",
      "concept_id": "1A434000-B017",
      "concept_label": "屋面卷材起鼓",
      "right": "A",
      "content_sha256": "<由 stem+opts+right 的 canonical JSON 机械计算>",
      "review_status": "pending_dual_teacher_verdict",
      "review_refs": []
    }
  ]
}
```

`manifest.py` 必须机械计算 hash、验证题目集合与签发状态；不能接受前端自报答案：

```python
def score_first_run_answers(*, script_version: str, answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest = load_first_run_manifest()
    if script_version != manifest["script_version"]:
        raise FirstRunManifestVersionConflict(script_version)
    unsigned = [q["question_id"] for q in manifest["questions"] if q["review_status"] != "signed"]
    if unsigned:
        raise FirstRunManifestUnsigned(",".join(unsigned))
    submitted = {str(item["question_id"]): str(item["selected_key"]) for item in answers}
    expected_ids = {str(item["question_id"]) for item in manifest["questions"]}
    if set(submitted) != expected_ids:
        raise FirstRunAnswerSetInvalid("answer_set_mismatch")
    return [
        {
            "question_id": question["question_id"],
            "source_question_id": question["source_question_id"],
            "source_scoring_point_id": question["source_scoring_point_id"],
            "concept_id": question["concept_id"],
            "concept_label": question["concept_label"],
            "learner_answer": submitted[question["question_id"]],
            "correct_answer": question["right"],
            "is_correct": submitted[question["question_id"]] == question["right"],
            "content_sha256": question["content_sha256"],
        }
        for question in manifest["questions"]
    ]
```

- [ ] **Step 4: 运行 manifest 测试**

Run: `pytest -q tests/services/first_run/test_manifest.py`

Expected: PASS；其中未签发测试证明 production scoring 被阻断。

- [ ] **Step 5: diff checkpoint**

Run: `git diff --check && git status --short`

Expected: 只出现本任务 4 个新文件；无提交。

---

### Task 2: 实现一次性幂等 Learner State 写回 authority

**Files:**
- Create: `deeptutor/services/first_run/writeback.py`
- Modify: `deeptutor/services/first_run/__init__.py`
- Create: `tests/services/first_run/test_writeback.py`

**Interfaces:**
- Consumes: `score_first_run_answers()`
- Consumes: `LearnerStateService.append_memory_event/read_profile/write_profile_strict/merge_progress`
- Consumes: `build_learning_training_intent()`、`build_home_personalization_projection_from_learning_signal()`、`write_home_personalization_projection()`
- Produces: `FirstRunWritebackService.complete(*, user_id, completion_id, script_version, answers, declared_preferences, completed_at) -> dict[str, Any]`
- Raises: `FirstRunIdempotencyConflict`

- [ ] **Step 1: 写 server re-score 与幂等 RED 测试**

```python
def test_complete_ignores_client_score_and_replays_without_duplicate_events(signed_manifest, fake_learner_state):
    service = FirstRunWritebackService(learner_state_service=fake_learner_state)
    body = _completion(answers={"first_run.v1:qigu_gebu": "B"})
    first = service.complete(user_id="u1", **body)
    replay = service.complete(user_id="u1", **body)
    assert first == replay
    assert len(fake_learner_state.events) == 4
    assert first["items"][0]["is_correct"] is False


def test_same_completion_id_with_different_body_conflicts(signed_manifest, fake_learner_state):
    service = FirstRunWritebackService(learner_state_service=fake_learner_state)
    service.complete(user_id="u1", **_completion(completion_id="c1"))
    with pytest.raises(FirstRunIdempotencyConflict):
        service.complete(user_id="u1", **_completion(completion_id="c1", material_version="older"))
```

- [ ] **Step 2: 运行 RED**

Run: `pytest -q tests/services/first_run/test_writeback.py`

Expected: FAIL because `FirstRunWritebackService` is absent.

- [ ] **Step 3: 实现 request hash 与第一事件冲突闸**

```python
request_hash = hashlib.sha256(
    json.dumps(canonical_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
```

先写第一题 event；`append_memory_event` 若按 dedupe key 返回旧 event，必须先比较旧 `request_hash`，不同立即抛 409 所对应异常，再写其余三题：

```python
dedupe_key = f"first_run_item:{user_id}:{completion_id}:{item['question_id']}"
event = self._learner_state.append_memory_event(
    user_id,
    source_feature="first_run_diagnostic",
    source_id=f"{completion_id}:{item['question_id']}",
    memory_kind="learning_evidence",
    payload_json=payload,
    dedupe_key=dedupe_key,
)
if str(event.payload_json.get("request_hash") or "") != request_hash:
    raise FirstRunIdempotencyConflict(completion_id)
```

- [ ] **Step 4: 写入客观证据、显式偏好与 canonical intent**

选择首个错误题；若全对则使用第一题但 reason 标为 `first_run_clean_baseline`。所有四个 event 共享同一 canonical `training_intent_id`，但不写 mastery：

```python
intent = build_learning_training_intent(
    user_id=user_id,
    concept_id=focus_item["concept_id"],
    concept_label=focus_item["concept_label"],
    evidence_refs=event_ids,
    source="first_run_diagnostic",
    reason="first_run_first_missed_item" if missed else "first_run_clean_baseline",
    training_mode="mixed_review",
)
```

profile 只合并显式声明：

```python
profile = dict(self._learner_state.read_profile(user_id) or {})
learning_preferences = dict(profile.get("learning_preferences") or {})
learning_preferences["first_run"] = {
    "memory_channel": declared_preferences.get("memory_channel", ""),
    "study_slot": declared_preferences.get("study_slot", ""),
    "motivation": declared_preferences.get("motivation", ""),
    "source": "explicit_first_run_v1",
}
profile["learning_preferences"] = learning_preferences
self._learner_state.write_profile_strict(user_id, profile)
```

然后用既有函数写 home personalization；不调用 `build_home_next_step_projection()` 写结果，因为它是 read-only arbitration。

- [ ] **Step 5: 测试 crash/retry 可补齐且无重复**

新增 fake 在第 3 次 append 抛异常；第二次调用同 payload 后应得到 4 个唯一 dedupe keys，证明“逻辑一次完成 + 可恢复”，不声称跨存储 ACID。

Run: `pytest -q tests/services/first_run/test_writeback.py`

Expected: PASS。

- [ ] **Step 6: diff checkpoint**

Run: `git diff --check && git status --short`

Expected: 仅 first_run service/test 增量；无已有 learner_state authority 文件改写。

---

### Task 3: 接入薄 mobile API 与 contract registry

**Files:**
- Modify: `deeptutor/api/routers/mobile.py`
- Create: `tests/api/test_mobile_first_run.py`
- Modify: `contracts/index.yaml`
- Modify: `deeptutor/contracts/index.yaml`
- Modify: `contracts/schema_registry.yaml`
- Modify: `contracts/learner-state.md`

**Interfaces:**
- Consumes: `FirstRunWritebackService.complete()`
- Produces: `POST /api/v1/first-run/complete`
- Request schema: `FirstRunCompleteRequest`
- Response errors: 409 version/idempotency/unsigned content；422 invalid shape；401 invalid auth；503 learner-state unavailable

- [ ] **Step 1: 写 API RED 测试**

```python
def test_first_run_complete_requires_auth(client):
    response = client.post("/api/v1/first-run/complete", json=_valid_body())
    assert response.status_code == 401


def test_first_run_complete_delegates_canonical_user(client, monkeypatch, auth_header):
    captured = {}
    monkeypatch.setattr(mobile, "first_run_writeback_service", _FakeService(captured))
    response = client.post("/api/v1/first-run/complete", json=_valid_body(), headers=auth_header)
    assert response.status_code == 200
    assert captured["user_id"] == "canonical-user-id"
    assert "score" not in captured["request"]
```

- [ ] **Step 2: 运行 RED**

Run: `pytest -q tests/api/test_mobile_first_run.py`

Expected: 404 because route is absent.

- [ ] **Step 3: 添加严格 request model**

```python
class FirstRunAnswerRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=128)
    selected_key: str = Field(pattern="^[A-D]$")
    duration_ms: int = Field(default=0, ge=0, le=900_000)


class FirstRunCompleteRequest(BaseModel):
    completion_id: str = Field(min_length=8, max_length=128)
    script_version: str = Field(min_length=1, max_length=128)
    completed_at: str = Field(min_length=1, max_length=64)
    answers: list[FirstRunAnswerRequest] = Field(min_length=4, max_length=4)
    declared_preferences: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: 添加薄 endpoint 与稳定错误语义**

```python
@router.post(
    "/first-run/complete",
    dependencies=[Depends(route_rate_limit("mobile_first_run_complete", default_max_requests=10, default_window_seconds=60.0))],
)
async def first_run_complete(body: FirstRunCompleteRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            first_run_writeback_service.complete,
            user_id=user_id,
            **body.model_dump(),
        )
    except FirstRunIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "first_run_idempotency_conflict"}) from exc
    except FirstRunManifestUnsigned as exc:
        raise HTTPException(status_code=409, detail={"error": "first_run_content_not_signed"}) from exc
    except FirstRunManifestVersionConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "first_run_version_conflict"}) from exc
```

- [ ] **Step 5: register-before-use**

根与 packaged `index.yaml` 同步加入：

```yaml
- {prefix: /api/v1/first-run, reason: "Authenticated first-run completion adapter; server re-scores signed static content and delegates a single idempotent learner-state writeback."}
```

`learning_state_inference.allowed_evidence_sources` 加 `first_run_diagnostic`；learner_state `test_files` 加 `tests/services/first_run/test_writeback.py` 与 `tests/api/test_mobile_first_run.py`。`schema_registry.yaml` 注册 `first_run_completion.v1`，producer 为 mobile adapter，consumer 为 `FirstRunWritebackService`。

- [ ] **Step 6: 运行 API、contract 与 mirror 测试**

Run:

```bash
pytest -q tests/api/test_mobile_first_run.py tests/services/first_run/test_manifest.py tests/services/first_run/test_writeback.py
python scripts/check_contract_guard.py deeptutor/api/routers/mobile.py contracts/index.yaml deeptutor/contracts/index.yaml contracts/schema_registry.yaml contracts/learner-state.md deeptutor/services/first_run/writeback.py tests/api/test_mobile_first_run.py tests/services/first_run/test_writeback.py
cmp contracts/index.yaml deeptutor/contracts/index.yaml
```

Expected: pytest PASS；`contract-guard: passed`；`cmp` exit 0。

- [ ] **Step 7: diff checkpoint**

Run: `git diff --check && git status --short`

Expected: API/contract changes only match this task；无 commit。

---

### Task 4: 把注册入口收敛到学习首页并接完成 API

**Files:**
- Modify: `yousenwebview/packageDeeptutor/utils/api.js`
- Modify: `yousenwebview/packageDeeptutor/utils/first-run-entry.js`
- Modify: `yousenwebview/packageDeeptutor/pages/register/register.js`
- Modify: `yousenwebview/packageDeeptutor/pages/first-run/script-data.js`
- Create: `yousenwebview/tests/test_first_run_native_journey.js`
- Modify: `yousenwebview/tests/test_register_flow.js`

**Interfaces:**
- Produces: `api.completeFirstRun(payload, opts) -> Promise`
- Produces: `firstRunEntry.CHECKPOINT_KEY/PENDING_SYNC_KEY/readCheckpoint/writeCheckpoint/clearCheckpoint`
- Registration target: `/packageDeeptutor/pages/learn/learn`

- [ ] **Step 1: 写 API 与入口 RED contract**

```javascript
assert(apiSource.indexOf('url: "/api/v1/first-run/complete"') >= 0);
assert(apiSource.indexOf("completeFirstRun") >= 0);
assert(registerSource.indexOf("pages/learn/learn") >= 0);
assert(registerSource.indexOf("redirectIfNeeded") < 0);
assert(firstRunEntrySource.indexOf("PENDING_SYNC_KEY") >= 0);
```

- [ ] **Step 2: 运行 RED**

Run: `node yousenwebview/tests/test_first_run_native_journey.js && node yousenwebview/tests/test_register_flow.js`

Expected: first command FAIL because completion API and keys are absent.

- [ ] **Step 3: 添加 completion API**

```javascript
function completeFirstRun(payload, opts) {
  return request({
    url: "/api/v1/first-run/complete",
    method: "POST",
    data: payload || {},
    loading: !(opts && opts.silent),
  });
}
```

将 `completeFirstRun` 加入唯一 `module.exports`。

- [ ] **Step 4: 降级 DONE、加入 checkpoint/pending keys**

```javascript
var DONE_KEY = "deeptutor_first_run_done_v1"; // UI cache only
var CHECKPOINT_KEY = "deeptutor_first_run_checkpoint_v1";
var PENDING_SYNC_KEY = "deeptutor_first_run_pending_sync_v1";
```

所有存储对象必须带 `userId` 与 `scriptVersion`；读取时不匹配即返回 null，防换账号串卷。

- [ ] **Step 5: 注册成功统一进入学习首页**

将原注册完成后的 first-run 直跳改成：

```javascript
wx.reLaunch({ url: route.resolve("pages/learn/learn") });
```

不在注册页判断 DONE、不直接进入 chat。

- [ ] **Step 6: script-data 加稳定 ID，删除前端正式推荐字段**

每题加入与 server manifest 一致的 `questionId/sourceQuestionId/sourceScoringPointId/contentSha256`；保留 `right` 仅用于即时 UI 反馈，但完成 payload 不提交 `ok/score/rx`，服务端仍重新判定。

- [ ] **Step 7: 运行 Node contract**

Run: `node yousenwebview/tests/test_first_run_native_journey.js && node yousenwebview/tests/test_register_flow.js`

Expected: PASS。

---

### Task 5: 在学习首页加入原生入口与 pending sync 恢复

**Files:**
- Modify: `yousenwebview/packageDeeptutor/pages/learn/learn.js`
- Modify: `yousenwebview/packageDeeptutor/pages/learn/learn.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/learn/learn.wxss`
- Create: `yousenwebview/tests/test_learn_first_run_entry.js`

**Interfaces:**
- Consumes: `firstRunEntry` storage helpers、`api.completeFirstRun()`
- Produces UI states: `firstRunState = new | resume | syncing | complete | hidden`
- Produces action: `openFirstRun()` and `_retryPendingFirstRun()`

- [ ] **Step 1: 写首页状态 RED 测试**

```javascript
assert.strictEqual(newUser.page.data.firstRunState, "new");
newUser.page.openFirstRun();
assert.strictEqual(newUser.calls.navigateTo[0].url, "/packageDeeptutor/pages/first-run/first-run");

await pending.page.onShow();
assert.strictEqual(pending.calls.completeFirstRun.length, 1);
assert.strictEqual(pending.calls.completeFirstRun[0].completion_id, "completion-1");
```

- [ ] **Step 2: 运行 RED**

Run: `node yousenwebview/tests/test_learn_first_run_entry.js`

Expected: FAIL because `firstRunState/openFirstRun` are absent.

- [ ] **Step 3: 加首页首次旅程卡状态**

`onShow()` 顺序固定：同步五 Tab → 读取当前 canonical user 的 checkpoint/pending/done cache → pending 时幂等重试 → 刷新首页 read models。首次卡只决定入口显示，不计算推荐。

```javascript
openFirstRun: function () {
  wx.navigateTo({ url: route.resolve("pages/first-run/first-run") });
}
```

- [ ] **Step 4: 用现有纸墨朱竹 token 渲染三态卡**

- `new`：标题“先做 4 道题，让鲁班认识你”，meta“约 3 分钟 · 完成后生成首份学习报告”。
- `resume`：标题“继续你的首次学习旅程”，显示当前进度。
- `syncing`：标题“报告已生成，正在保存学情”，按钮禁用但允许页面其他内容使用。

不得新增颜色体系、emoji 主图或与第 10 轮不同的圆角/阴影语言。

- [ ] **Step 5: 运行首页 contract 与既有学习页 contract**

Run:

```bash
node yousenwebview/tests/test_learn_first_run_entry.js
node yousenwebview/tests/test_workspace_shell_navigation_authority.js
node yousenwebview/tests/test_home_dashboard_learning_prompts.js
```

Expected: 全 PASS。

---

### Task 6: 一页一题、完整反馈、一次提交并回学习首页

**Files:**
- Modify: `yousenwebview/packageDeeptutor/pages/first-run/first-run.js`
- Modify: `yousenwebview/packageDeeptutor/pages/first-run/first-run.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/first-run/first-run.wxss`
- Modify: `yousenwebview/packageDeeptutor/pages/first-run/first-run.json`
- Modify: `yousenwebview/tests/test_first_run_native_journey.js`

**Interfaces:**
- Consumes: `api.completeFirstRun()`、script manifest metadata、checkpoint helpers
- Produces: local report states `idle | syncing | synced | pending | blocked`
- Exit target: `route.resolve("pages/learn/learn")`

- [ ] **Step 1: 扩展 RED 测试覆盖一页一题与一次提交**

```javascript
page._showQuestion(0);
assert.strictEqual(page.data.act, "question");
assert.strictEqual(page.data.qIndex, 0);
assert.strictEqual(page.data.q.questionId, "first_run.v1:qigu_gebu");
assert.strictEqual(page.data.nextQuestion, undefined);

page._buildReport();
await flushPromises();
assert.strictEqual(calls.completeFirstRun.length, 1);
assert.deepStrictEqual(Object.keys(calls.completeFirstRun[0]).sort(), [
  "answers", "completed_at", "completion_id", "declared_preferences", "script_version"
]);
assert.strictEqual(calls.reLaunch[0].url, "/packageDeeptutor/pages/learn/learn");
```

- [ ] **Step 2: 运行 RED**

Run: `node yousenwebview/tests/test_first_run_native_journey.js`

Expected: FAIL on payload/route/sync state assertions.

- [ ] **Step 3: 修复顶部安全区与五模块视觉**

- `onLoad()` 读取 `statusBarHeight`，设置 `navHeight=statusBarHeight+48`。
- 自定义顶栏左=关闭/稍后继续，中=“首次学习旅程”，右=`{{qIndex + 1}} / {{qTotal}}`。
- 删除右上角绿点与泛化 `.status` 类；所有新类前缀 `fr-`，避免 companion/状态样式碰撞。

- [ ] **Step 4: 锁定题间不可滚动**

- 问题 act 使用固定内容区，不渲染任何其他题。
- feedback act 只渲染当前 `fb`，允许 `scroll-view scroll-y`。
- 下一题仅由 `onFeedbackNext()` → interlude → `_showQuestion(i+1)` 进入。
- 切换 act 后将当前 scroll-view 复位，不依赖整页向下滚。

- [ ] **Step 5: 本地 checkpoint 与完成 payload**

每次题间/侧写选择后写 checkpoint；报告完成构造稳定 `completion_id`，同一次 pending retry 不得换 ID：

```javascript
var payload = {
  completion_id: this.completionId,
  script_version: data.SCRIPT_VERSION,
  completed_at: new Date().toISOString(),
  answers: this.results.map(function (item) {
    return {
      question_id: item.questionId,
      selected_key: item.picked,
      duration_ms: item.durationMs,
    };
  }),
  declared_preferences: this._declaredPreferences(),
};
```

- [ ] **Step 6: 报告显示与同步状态分离**

`_buildReport()` 先显示完整报告，再调用一次 `_syncCompletion(payload)`。成功：清 checkpoint/pending、写 UI DONE cache、CTA 回学习首页。网络失败：保存 pending payload，显示“报告已生成，学情待同步”，返回学习首页后由 `learn.onShow()` 重试。409 unsigned/version：显示明确 blocked，不写 DONE，不伪成功。

- [ ] **Step 7: 删除旧出口与正式 rx**

- `onSkip()` 只保存 checkpoint 并返回学习首页。
- `onReportGo()` 和 `onFinale()` 都回学习首页。
- 删除 `missN -> rx` 正式推荐；报告只展示服务端 `home_projection.today_focus`，未同步时展示“同步后生成今日任务”。
- 订阅授权独立于完成写回，拒绝/失败不改变 synced 状态。

- [ ] **Step 8: 运行前端 contract**

Run:

```bash
node yousenwebview/tests/test_first_run_native_journey.js
node yousenwebview/tests/test_learn_first_run_entry.js
node yousenwebview/tests/test_register_flow.js
node yousenwebview/tests/test_workspace_shell_navigation_authority.js
```

Expected: 全 PASS。

---

### Task 7: 全链路验证、真实微信 QA 与内容人门

**Files:**
- Modify: `docs/plan/鲁班移动端提分闭环/implementation-notes.md`
- Modify: `docs/plan/INDEX.md`

**Interfaces:**
- Consumes all previous tasks.
- Produces evidence bundle; does not alter runtime authority.

- [ ] **Step 1: 后端聚焦回归**

Run:

```bash
pytest -q tests/services/first_run/test_manifest.py tests/services/first_run/test_writeback.py tests/api/test_mobile_first_run.py tests/services/learner_state/test_service.py tests/services/learner_state/test_training_intent.py tests/services/learner_state/test_home_next_step_projection.py tests/services/member_console/test_home_dashboard_learning_projection.py
```

Expected: 全 PASS。

- [ ] **Step 2: 前端聚焦回归**

Run:

```bash
node yousenwebview/tests/test_first_run_native_journey.js
node yousenwebview/tests/test_learn_first_run_entry.js
node yousenwebview/tests/test_register_flow.js
node yousenwebview/tests/test_workspace_shell_navigation_authority.js
node yousenwebview/tests/test_home_dashboard_learning_prompts.js
```

Expected: 全 PASS。

- [ ] **Step 3: contract/schema/mirror gate**

Run:

```bash
python scripts/check_contract_guard.py $(git diff --name-only origin/luban/seethrough-visuals-on-main...HEAD)
cmp contracts/index.yaml deeptutor/contracts/index.yaml
git diff --check
```

Expected: `contract-guard: passed`、`cmp` exit 0、无 whitespace error。

- [ ] **Step 4: 内容签发 stop condition**

逐题核对 manifest 的 `content_sha256/review_status/review_refs`。第 4 题 `first_run.v1:zhuangpeishi_laji` 必须引用 2025 案例（一）问题 3 的逐字 source，并获得两条独立教研 verdict 后才能从 `pending_dual_teacher_verdict` 改为 `signed`。agent 不生成或代签 verdict。

Expected before human gate: `test_unsigned_question_blocks_server_scoring` PASS，整体状态 `implemented_but_release_blocked`。

Expected after human gate: 改为 signed 后新增 `test_all_four_signed_manifest_allows_scoring` PASS，才允许进入真实写回 QA。

- [ ] **Step 5: 微信开发者工具真实入口**

Run:

```bash
WX_DEVTOOLS_CLI=/Applications/wechatwebdevtools.app/Contents/MacOS/cli
$WX_DEVTOOLS_CLI islogin
$WX_DEVTOOLS_CLI open --project /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-first-run-current-five-module/yousenwebview --lang zh
$WX_DEVTOOLS_CLI auto --project /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-first-run-current-five-module/yousenwebview --auto-port 9422
```

自动化或人工脚本必须真实执行：注册/登录 eval runner → 学习首页首次卡 → 四题逐页 → 当前题反馈 → 完整报告 → 完成写回 → 回学习首页 → 五 Tab 恢复 → 首页 next step 更新。

证据必须记录：

```text
devtools_project_root=.../yousenwebview
target_subpackage=packageDeeptutor
target_page=packageDeeptutor/pages/first-run/first-run
entry_flow=register -> learn -> first-run -> report -> writeback -> learn
auth_state=logged_in|qa_token|auth_blocked
auth_mode=real_wechat|local_dev_wechat|manual_token|none
```

- [ ] **Step 6: 视觉对照 QA**

以 owner 已批准的 companion 最终稿和五模块第 10 轮学习页为并排参考，使用同一 viewport 对照：安全区、顶栏、字号、卡片圆角、纸墨朱竹色、题内滚动、报告密度、底部 CTA。截图本身不算 PASS，必须同时操作主路径控件。

- [ ] **Step 7: 更新活账本与索引状态**

只记录实测事实：实现文件、测试数字、内容签发状态、真实微信四元证据、偏离与 remaining blockers。未过第 4 题人门或 true-entry 时，INDEX 状态不得写 `Complete/Production-ready`。

---

## Self-review

### Spec coverage

- 学习首页入口：Task 5。
- 答题时隐藏五 Tab、完成恢复：Task 5/6/7。
- 一页一题与当前题完整反馈：Task 6。
- 原版核心内容最大保留：Task 4/6。
- 报告完成一次性幂等写回：Task 2/3/6。
- Learner State 连续与第二天首页：Task 2/5/7。
- 单一 authority：Task 1/2/3。
- 弱网/重试/冲突：Task 2/5/6。
- 第 4 题签发门：Task 1/7。
- 真微信验收：Task 7。

### Placeholder scan

本文没有把未知实现写成 TODO/TBD。`<computed-manifest-sha256>` 明确是 Task 1 由代码机械生成的派生值，不是人工待填字段；人类 verdict 是显式外部门与 stop condition，agent 不得伪造。

### Type consistency

- 前端 payload 字段与 `FirstRunCompleteRequest` 一致。
- `completion_id/script_version/answers/declared_preferences/completed_at` 从 Task 3 贯穿 Task 4-6。
- `question_id` 从唯一 manifest 贯穿前端镜像、API 与 learner event。
- `training_intent_id` 只由 `build_learning_training_intent()` 生成，首页只读消费。
