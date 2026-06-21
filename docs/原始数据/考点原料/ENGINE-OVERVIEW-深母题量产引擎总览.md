# 深母题量产引擎 · 总览与交接（2026-06-20）

> 本文档是整条"深母题考点 pack 量产引擎"的单一索引：流水线、工具、SOP、产物、关键结论、遗留。给未来接手用。
> 定位：本引擎是**内容生产侧**（造考点说明书），不是导航/运行时辅导。pack 默认 `candidate_teaching_prototype`。

## 0. 一句话

把数据资产（教材/真题/规范的编译产物）**用 AI 天团（Opus/Codex-GPT5.5/DeepSeek-v4-pro/Qwen-max）分工协作对抗**，自动炼成"大师级考点 pack"（R1-R8 + 跨章聚拢 + 原理因果 + 动画分镜），每个 pack 自动过门控+质检+修复，候选级零手动。

## 1. 量产流水线（端到端，全自动）

```
① 挖矿(确定性)        → _<ID>_compiled_source.json (从RichLeaf v3.2按考点关键词筛+去重)
② 真题取证(确定性)    → _<ID>_exam_evidence.json   (从真考卷抽官方答案/解析/分值)
③ 4谱系生产          → pack.md  (A聚拢原理→DeepSeek / B出题人→Opus / C采分边界→Codex / D误区动画→Qwen / Opus汇编)
④ 两道确定性闸        → verify_pack.py(结构) + verify_exam_anchors.py(真题题号)
⑤ 4源异源jury        → jury_audit.py (Codex+DeepSeek+Qwen各独立语义审 + DeepSeek合成收敛)
⑥ autofix自动修复    → autofix.py(v1记录) / autofix_v2.py(自动应用高可信手术编辑) → 复跑两闸
                     candidate就绪
（R7 active 升级见 SOP-R7-active；R7构造后接 signed scoring artifact → 进官方判分级）
```

## 2. 工具清单（全在 docs/原始数据/考点原料/）

| 工具 | 作用 | 关键 |
|---|---|---|
| `extract_exam_evidence.py <ID> "<kw>"` | 确定性抽真题官方答案/解析/分值 | ground truth 源 |
| `produce_lens.py <ID> <model> <lens>` | 单镜头分派给指定谱系生产 | deepseek/qwen API + codex exec；Opus无key走Workflow |
| `verify_pack.py <pack>` | 闸1机器闸:point_id真在源料/error_code真在注册表/三色 | 已修:CJK点id、M35/砂浆等级非错因码排除 |
| `verify_exam_anchors.py <pack> [kw]` | 闸2真题核验:题号真存在+主题相关 | 已修:题号单/多选重名穷举；**遗留:关键词固定默认反复漏判,真修法见§5** |
| `jury_audit.py <pack>` | 4源异源团语义审+合成收敛JSON(sidecar) | codex走exec同步非rescue后台 |
| `autofix.py <pack> <jury.json>` | v1:jury发现自动写§9审计记录+复跑闸 | append-only安全 |
| `autofix_v2.py <pack> <jury.json>` | v2:高可信(≥2源)自动转手术编辑应用+复跑闸 | DeepSeek reviser出{old,new}唯一定位才改 |

工作流脚本(session临时,可scriptPath复用): 生产=`produce-4lineage`/`deep-pack-compile-parametric`; 质检=in jury_audit.

## 3. SOP/设计文档

- `SOP-深母题pack生产-v2.md` — 生产+质检主SOP(含4源异源团Layer-2、收敛规则、别prime陪审团)
- `SOP-R7-active-AI天团构造.md` — R7升active六阶精工流程(取证锁真→3模型独立构造→确定性闸→红队→自洽校准→异源终审)
- `README.md` — 考点pack实例化L0-L7、三色铁律、不立第二authority
- `2026-06-20-考点pack编译方法与Q02评估.md` — 方法+Q02评估

## 4. 已产 pack（6 个，两闸全绿）

| pack | 域/型 | 备注 |
|---|---|---|
| Q02 大体积温控 | 混凝土/计算 | 首个;已Codex异源复验+autofix_v2自动改7条 |
| S01 脚手架验收 | 安全/判断 | v2 Codex入环;真题取证修编造 |
| A01 检验批验收 | 质量/程序 | 4源jury+autofix闭环样板 |
| Q03 质量通病 | 质量/找错 | 单模型版 + **4谱系版(_v4model,验证更优)** |
| S02 起重吊装 | 安全/判断 | 汇编fallback抓危大两层门槛 |
| (Q03_v4model) | — | 4谱系生产标杆:point_id 2.5×、生产期跨谱系互catch |

## 5. 关键结论/教训（贯穿全程，未来别再踩）

1. **AI共识≠ground truth，连自己写的脚本也≠**。每个验证者(Opus/Codex/DeepSeek/Qwen/确定性脚本)都在真实数据上暴露过bug。鲁棒=多层+持续硬化+冲突回真源(真考卷/教材/error_codes.py)裁定。
2. **验证分工**:结构化事实(题号/point_id/error_code存在)→确定性代码穷举；语义判断(逻辑/真伪/主题)→LLM异源裁判。别让LLM查事实(抽样+猜会错),别让代码判语义。
3. **别prime陪审团**:prompt点名疑似问题=制造假收敛。中立prompt才独立。收敛是稀有红利非主指标,广度(N源并集)才是价值;count=1=单源真catch回真源核非丢弃。
4. **异源>同源**:Codex(GPT5.5)抓出Opus同源对抗放过的编造真题(50m/S01假EXAM id)。但异源judge也会错(Codex题号读错8个被确定性脚本纠);终裁回真考卷文件。
5. **4谱系生产>单脑**:Q03实测point_id 2.5×、🟢更多🔵🔴更少、生产期跨谱系互catch(DeepSeek锚错被Codex补Opus裁)。值每pack多~$0.4。
6. **R7 active不靠人类**:判分标准是真考卷correct_answer/analysis/score(现成ground truth),AI团锚它构造+对抗=超人类一致性,不是发明标准。
7. **codex机制**:codex exec --sandbox read-only 同步可靠;codex-rescue后台agent反复卡死/断线,别用。
8. **干净worktree/分支纪律、register-before-use、authority单一**(判分归signed artifact/错因归ERROR_CODE_REGISTRY/学情归LearnerStateService)——pack永不拥有,只引用。

## 6. 成本（实测）
生产 ~50-85万 token/pack(4谱系略高) + jury/autofix ~$0.5 API/pack。60个 ≈ ~3000万token + ~$30 API。计算型~20个需另建"挖真题例题"源料管线。

## 7. 遗留（按优先级）
1. **闸2按考点取词**(A):固定默认词反复漏判跨域真题(脚手架/起重/砌体4次),真修=从源料/config取per考点关键词。
2. **R7 active六阶跑通**(B):SOP已设计,r7_construct.py待建,首试Q02 2019案例(计算型,可走确定性复算最硬保证)。
3. **autofix v3**:自动改后再jury兜底防引新错。
4. **计算型考点源料管线**:网络/索赔/计价编译库覆盖弱,需挖真题例题。
5. **候选级量产**:~40事实/判断型考点全自动跑。
