---
name: luban-diagram-microlesson
description: Use this whenever you author, render, redesign, or review a 鲁班 diagram micro-lesson card under artifacts/luban_case_family_assets/diagram_microlesson/ (F16 起鼓割补 / N01 网络计划 / D01 采分点诊断 / C01 对照, or any new 图解卡 / 解释型动效卡). Trigger it for: adding a new template_type or card JSON, changing a render_*.py renderer, fixing "页面太长要狂滚 / 下一步藏太深 / 一屏太多重点" mobile UX, anything about 单一权威边界 (renderer 不判分 / candidate 不冒充签发 / 学生端别露 source_ref/P编号/schema/renderer/candidate), and before claiming a card is done. Also use it whenever the work needs WeChat 小程序 web-view 承载/沙盒 or zero-dependency Chrome screenshot/DOM 断言 — see the reference files.
---

# 鲁班图解微课卡 (diagram_microlesson)

把"母题图解卡 / 解释型动效卡"做成 **窄 schema + 确定性 renderer + 一屏一重点的翻页卡**，
让忙碌备考成人 60 秒看懂"错在哪、为什么这么修、怎么写才得分、下一题怎么验证"。

**唯一目录**：`artifacts/luban_case_family_assets/diagram_microlesson/`。不新建第二套目录 / 第二个 schema_version。

## 0. 先读这些(权威在文件里，别凭记忆)

- `SCHEMA.md` —— schema 单一权威：template_type 注册表、共同 spine、互斥 body、学生端安全规则、authority 规则。**改字段先改这里再写 JSON 再写 renderer**(register-before-use)。
- `validate_schema_drafts.py` —— 轻量校验器，自动发现所有卡，守 spine/body/authority/学生安全。**每轮必跑**。
- `docs/plan/鲁班移动端提分闭环/2026-06-17-luban-explainer-motion-template-engine-v0-principles.md` —— 五条红线 + 模板类型 + 三阶段量产闸。
- `explainer_template_v0_schema_spine_review.md` / `mobile_ux_redesign_acceptance.md` —— 收口与 UX 决策记录。
- 平台细节看本 skill 的 `references/wechat-webview-sandbox.md` 和 `references/zero-dep-cdp-harness.md`。

## 1. 单一权威边界(最容易踩，最不能破)

renderer 是 thin wrapper，知识/判分是 fat skill 的上游 authority。逐条守：

1. **renderer 不做知识判断、不判分、不补采分点、不改分值、不推断官方答案。** 关键线路 / 时差 / diagnosis verdict / 采分点全部来自 JSON 或 build 期确定性计算，前端只展示。
2. **确定性计算器是 build 期独立校验器/编译器，不是前端、不是 official scoring authority。** 例：N01 的 `compute_cpm()` 在 build 期校验 JSON 的 `expected`(关键线路/时差)自洽并派生 ES/EF 供展示；日后可抽成独立编译器，仍不得让前端现场判断。
3. **candidate 诚实标注，绝不冒充签发。** 教学草拟用 `authority.status=candidate_teaching_prototype` / `provenance.kind`；候选 `official_score_allowed` 不得为 true；不编造真题来源(写 `candidate_teaching_example`)。
4. **教学拆解点不冒充已签发采分点。** `exam_binding.kind` 区分 `signed_candidate` vs `teaching_step`；候选采分点仅来自既有 P 系列 + source_ref，本层不新增采分点或规范数值。
5. **学生端不露内部词。** UI 文案禁止出现 `source_ref / P10/P11 / schema / renderer / candidate / 母题包 / 本系统`。客户端 data 载荷剥离 `source_refs / score_point_id`；raw source_ref / artifact id 只进 HTML 注释。检查方法见 §5。

## 2. 制作流程(schema-first)

1. **先填 schema JSON**，不直接手写成品 HTML。新 template_type 先在 `SCHEMA.md` 登记字段。
2. **body 互斥（只能其一，共 5 类）**：`steps[]`(流程/剖面) | `question_data.{activities,dependencies,expected}`(network) | `diagnosis[]`(判分诊断) | `contrast_items[]`(对照) | `decision.judgment_points`(判断分支)。`scoring_points/common_errors/practice` 是可共用 spine。新增 body 类型必须先在 SCHEMA.md 的 template_type 注册表 + 互斥 body 表登记，再写校验器/renderer（register-before-use）——以 `validate_schema_drafts.py` 的 `detect_body()` / template 分派为实现真相，二者必须与 SCHEMA.md 对齐。
3. **写窄确定性 renderer**：一个 template_type 一个窄 renderer(`render_card.py` / `render_network_card.py` / …)，**并列不互相重构，不抽通用大框架**——等第 3 个 rendered proof 或学员验证通过再考虑抽公共层。
4. **跑校验器 + 渲染 + 验收**(§5)。
5. 文案像老师讲(§4)。

## 3. 移动端 UX：一屏一个重点的翻页 deck

产品定调：**宁可多几页，也不要长滚动；每屏 ≤3 个重点，最好 1 个。** 十几二十屏没关系，反而显得内容丰富。

- **翻页 deck**：每步独占一屏(聚焦图 + 步骤标题 + 老师讲一句 + ✍这样写才得分)，"为什么/你常漏"折在"＋"里；错因 / 复测 / 收束各自成屏。整页高度应≈一屏(实测 F16 由 2958px → 930px)。
- **底部操作条 `position:fixed` 常驻**(上一步 ｜ 进度 ｜ 下一步)，永远在拇指边——解决"下一步藏太深"。body 留底部 padding 防遮挡。
- **硬约束（全模板）**：无外链 / 无 CDN / 无 web 字体(用系统字体栈 `-apple-system,...,"PingFang SC"`) / 无运行时 TTS 合成 / 无前端 LLM / 无 RAG / renderer 不判分；CSS·JS·SVG 全内联；390px 宽 `document.documentElement.scrollWidth===390`(无横向滚动)；触摸区 ≥44px。
- **音频不是全局禁**：F16/N01 这类是全内联无音频；但 `contrast` 模板(`render_contrast_card.py`)引入了**预录音频 `<audio>`+timing**(读预存文件、非 TTS、非现场合成)——这是该模板的取舍。别把"无音频"当全局铁律；新模板若要音频，须在 SCHEMA 显式登记 + 说明音频随产物的承载方式(预录文件 vs data-URI 内联)，并复核它对"无外链"的影响。
- 为避免大段 JS 在 Python f-string 里花括号转义出错，把交互逻辑抽成独立 `_JS = r"""..."""` 原始字符串(单括号普通 JS)，f-string 里只 `<script>{_JS}</script>`。
- 暴露断言钩子供 DOM 验收：`document.documentElement.dataset.activeLayer / narrMode / activeError / practiceResult / screen`；稳定 id `#prevBtn #nextBtn #progressBar #practiceFeedback`；类 `.step-layer[data-layer] .error-card[data-jump] .option`。

## 4. 文案质量

像老师拿着图讲，不像规范条文搬运。点出真实错因(泛泛"处理一下"为什么不够、直接重铺为什么错、少附加层为什么不稳、不检验为什么闭环没完成)。区分"候选采分点"和"教学理解步骤"。不要堆术语。

## 5. 验收(声明"完成"前必跑)

```bash
DIR=artifacts/luban_case_family_assets/diagram_microlesson
python3 -m json.tool $DIR/<card>.json >/dev/null            # JSON 合法
python3 -m py_compile $DIR/render_*.py                       # renderer 可编译
python3 $DIR/render_<x>_card.py $DIR/<card>.json $DIR/<card>.rendered.html
rg -n "https?://|cdn|@import|<img|script src|link rel|\.mp3|\.wav|<audio" $DIR/<card>.rendered.html   # 应空
python3 $DIR/validate_schema_drafts.py                       # spine/body/authority/学生安全 全绿
```

DOM / 视觉断言用 **零依赖 CDP**(见 `references/zero-dep-cdp-harness.md`)：通用项每模板都查——`scrollWidth===390`(无横滚)、触摸区 ≥44px、底部条 `position:fixed`、学生端无内部词。**模板专属钩子各不相同，别拿 F16 的套全部**：F16 deck 有 `dataset.activeLayer/narrMode/screen` + 翻页/错因跳转/复测；N01 是网络图节点/边 + 关键线路高亮；contrast 是揭示 + `<audio>` timing；decision 是判断点分支走到 `reached_outcome`。先读对应 `render_<x>_card.py` 暴露了哪些钩子，再写断言；`render_*_card.py` 命名也按模板而非只有一个。

学生端泄漏扫描(排除 HTML 注释/JS 注释)：
```bash
awk '/<!--/{c=1} !c; /-->/{c=0}' $DIR/<card>.rendered.html | grep -vE '^\s*//' \
 | grep -nE "source_ref|P10|P11|schema|renderer|candidate|母题包|本系统" || echo "(clean)"
```

Web/截图工作前先跑内存守则；`agent-owned-next-guard.sh --check` 单独跑(和 pgrep/ps 放同一条命令会自匹配假阳性，见 references)。

## 6. 量产闸(没过不铺)

- 体验类卡(F16)：未过 3-5 人学员验证前不铺更多。
- network 类(N01)：未绑真题 source_ref 前不铺更多。
- 判分解释类(D01)：未拿签发 source_ref + 真实学生答卷 + 人审/gold 前不做生产 renderer。
- 生成式视频不进入知识核心表达层。
