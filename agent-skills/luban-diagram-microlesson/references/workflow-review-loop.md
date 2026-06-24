# workflow-review-loop.md · 评审包与回炉合同

> 用途:把"机器门绿了但人眼还是觉得乱/挤/没动画/不舒服"这类问题,固定收敛到 OpenMAIC-style workflow,而不是每张卡临时补 CSS。
> 边界:本文件不重判母题事实。事实仍由 master/card/variants/scoring/source 负责;这里只管评审证据、表现层反馈和回炉路径。

## 1. 一等事实

60 张卡量产时,每张卡都必须能回答同一个问题:

```text
母题事实被冻结后,表现层是否通过结构化 IR/action、确定性 renderer、真实视口 gate 和评审回炉,稳定地产出可学习、可练习、可复审的学习卡?
```

唯一 authority 分层:

| 事实 | 唯一 authority |
|---|---|
| 考点、题目、采分点、错因 | 母题数据 master/card/variants/scoring/source |
| 动画分镜、镜头、reveal、退出 | `animation_ir.v0` 或 lesson `animation_action[]` |
| 像素、布局、图元、播放器 | deterministic renderer / learning stage shell |
| 合格与否 | gate 输出 + screenshot wall + judge/human review packet |

## 2. Review Packet

每轮 P3/P4/P5 必须产出或更新一个 review packet。当前可用脚本:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/build_workflow_review_packet.mjs \
  --card-id <topic> \
  --ir artifacts/luban_case_family_assets/diagram_microlesson/<topic>.animation_ir.v0.json \
  --gate validate_animation_ir_preview=PASS:0 \
  --gate validate_challenge_theater_practice=PASS:0 \
  --screenshot visual=artifacts/luban_case_family_assets/diagram_microlesson/<topic>.visual_review/<topic>.visual_review_manifest.json \
  --screenshot remotion=artifacts/luban_case_family_assets/diagram_microlesson/<topic>.remotion_review/manifest.json \
  --out artifacts/luban_case_family_assets/diagram_microlesson/<topic>.workflow_review_packet.json
```

packet 可以先写 JSON,后续再接自动 judge 和截图墙 UI。最小字段如下:

```json
{
  "card_id": "F16_qigu",
  "round": 2,
  "stage": "P4_review",
  "machine_gates": [
    {
      "name": "validate_animation_ir_contract",
      "status": "PASS",
      "warn": 0,
      "report_path": "P40_A02.gate_reports/validate_animation_ir_contract.txt",
      "report_exists": true,
      "report_sha256": "..."
    },
    {
      "name": "validate_animation_ir_preview",
      "status": "PASS",
      "warn": 0,
      "report_path": "P40_A02.gate_reports/validate_animation_ir_preview.txt",
      "report_exists": true,
      "report_sha256": "..."
    }
  ],
  "screenshots": [
    {"viewport": "390x844", "path": "...390.png", "looked": true, "issue": ""},
    {"viewport": "844x390", "path": "...844.png", "looked": true, "issue": ""},
    {"viewport": "user_feedback", "path": "...1432.png", "looked": true, "issue": "right panel text clipped"}
  ],
  "judge": {
    "verdict": "FAIL",
    "visual_archetype_decision": {
      "primary_archetype": "section_or_spatial_reveal",
      "visual_primitive": "roof_section",
      "motion_grammar": "layer_explode",
      "pure_text_allowed": false,
      "why_not_text": "学生需要看见卷材、基层、病灶和修补闭环"
    },
    "panel": [
      {"slot": "codex_gpt5_5", "status": "PASS|FAIL|BLOCKED", "note": "主审:实现和 gate 对齐"},
      {"slot": "claude_opus_or_cli", "status": "PASS|FAIL|BLOCKED", "note": "辅助审:用 opus4.8;不可用时用 claude -p 读取输出"},
      {"slot": "deepseek_v4_pro", "status": "PASS|FAIL|BLOCKED", "note": "待接入 judge slot;未接入不得伪造已评"},
      {"slot": "qwen3_7_max", "status": "PASS|FAIL|BLOCKED", "note": "待接入 judge slot;未接入不得伪造已评"}
    ],
    "issues": [
      {
        "axis": "practice_readability",
        "anti_pattern": "题图文字挤压",
        "beat_or_question": "q1",
        "severity": "HIGH",
        "fix": "use pill nodes and add SVG label fit gate"
      }
    ]
  },
  "root_cause_triage": [
    {
      "symptom": "流程节点文字挤压",
      "shared_failure_shape": "dormant authority",
      "one_authority": "validate_challenge_theater_practice + renderer primitive contract",
      "broken_contract": "gate checked page overflow but not SVG label fit",
      "fix_layer": "renderer|gate|skill",
      "new_gate_or_antipattern": "svg_step_labels_fit + 题图文字挤压"
    }
  ],
  "revision_scope": {
    "allowed": ["animation_ir.v0表现字段", "renderer primitive", "gate", "skill anti-pattern"],
    "forbidden": ["改母题事实", "改采分点", "只调单卡 CSS 后宣布治本"]
  }
}
```

## 3. 修复层级裁决

看到问题先按下表归因,不要直接调样式:

| 现象 | 默认 fix_layer | 必须补的证据 |
|---|---|---|
| 没有动画示意/图画类教学解释 | P0 visual_archetype_decision + IR + renderer | 6+1 原型选择、对应 primitive、motion grammar、截图中主视觉为图示动作 |
| 安全/合同/管理卡退化成纯文字 | skill + P0 gate + judge | 证明它为何不能用判断树/资金链/site plan/失稳链;通常证明不了就必须改图示 |
| 字挤、字裁、节点塞不下 | renderer + gate | 新图元规则 + label/text gate |
| 全屏/横屏比例错 | learning-stage shell + runtime gate | 对应真实视口截图 |
| 像翻页、没动作 | IR/actions + renderer | 每 scene 至少一个 action 可见变化 |
| 音画不同步 | timing + narration + preview/remotion gate | sync_keyword 和关键帧 |
| 题目无图或选项不像采分句 | practice generator + mother data binding | variants/source/scoring 追溯 |
| 题面泄答案、选项是 key point 标签、解析读不懂 | practice generator + practice interaction gate + anti-pattern | 母题 R3/R4/采分点派生题;答前无正确高亮;错项专属反馈 |
| 题干本身读不懂,但结果页/AI 入口很完整 | practice_blueprint + judge | 先修 scene_gap/学生答案/标准动作/错项诱因,结果页不能替代题目质量 |
| 手机打不开 `127.0.0.1` 链接 | preview handoff | LAN IP URL + 端口监听证据,换 Wi-Fi 后重新取 IP |
| 同一套四图/图标/流程贯穿多数页面 | P0.5 storyboard + IR visual_library + judge | `scene_visual_brief[]` 证明每幕来自当前旁白/考试动作;截图墙证明对象组合或对象状态变化,不是只换标题标签 |
| 旁白用 A02/P40/IR/source_card 等内部编号解释题意 | lesson/source workflow + narration gate + skill | opening 和主讲用学生能懂的真实考试任务展开;内部 id 只留制作追溯,不得进入老师/学生音频 |
| 人眼发现但机器绿 | gate + anti-pattern | 先补 gate/anti-pattern,再修页面 |
| 图元只在一侧 renderer 可用 | contract gate + renderer | HTML/Remotion primitive coverage 双绿 |
| 有图元但仍围绕文字讲 | IR contract + renderer composition | `dominant_visual_teaching_scene_count` 达标;主讲 scene 的非文字 domain diagram node 面积达到 `min_visual_dominance_ratio` |
| Remotion still 仍像文字卡、大空白或图文断裂 | renderer + IR + Remotion quality gate | `capture_remotion_ir_review_stills.mjs` manifest、`quality_gate.required=true/pass=true/flags=[]`、关键 scene still |
| 批量 manifest 覆盖已晋级样板 | batch generator + promotion authority | `validate_workflow_promotions.mjs` PASS、`promotion_authority`、`preserved_by_batch=true` |
| 只影响一张卡的极小视觉瑕疵 | card CSS 可例外 | 写明为什么不是 shared shell/renderer/gate 问题 |

## 4. Judge Prompt 骨架

LLM judge 只评表现和学习体验,不重写事实。输出必须是结构化反馈:

```text
你是鲁班动画学习卡评审。只基于给定 IR、HTML gate 输出、截图和母题摘要评审。
不要改考点事实、采分点、错因或答案。只判断表现层是否帮助学生拿分。

必查:
1. 是否有 `visual_archetype_decision`;primary archetype 是否按认知结构而不是文件名选择
2. 主讲画面是不是图示动作在解释知识;纯文字只允许(七)数值/记忆类,且必须说明理由
3. hook/main_exam_action 是否一线贯穿
4. 每个 beat 是否有可见 action,不是整页翻片
5. 镜头是否筛注意力:focus 放大/高亮/暗化/退出是否服务当前句
6. 字幕/coach 是否跟画面同步,不遮挡
7. practice 是否独立、每题有图、选项可转化为采分表达
8. practice 题干是否像真实考场任务,不是内部标签;错项解析是否讲清“为什么会选、为什么扣分、正确动作怎么补”
9. 结果页是否分析学员表现、给出补练/问鲁班入口,但没有掩盖题目本身不可读
10. 手机预览是否给 LAN URL 而不是 localhost
11. 后置 qa[] 是否至少三问三答;学生声纹为 longlaotie_v3 时,问题是否像真实东北男孩轻口语追问,而不是书面提纲或方言段子
12. 截图墙是否存在拥挤、裁切、小片化、控制条遮挡
13. 发现问题时应归因到 IR、renderer、gate、skill 还是 card-css
14. 每个主讲 scene 的主图是否由当前旁白句/`exam_task`/`answer_move` 推导;是否出现同一套图超过 2 幕只换标题标签
15. 学生端旁白是否说清真实考试任务;是否把 `A02/P40/F16/source_card/IR/scene/primitive/pack` 当成解释

返回 JSON:
{
  "verdict": "PASS|FAIL",
  "issues": [
    {
      "axis": "narrative|motion|layout|practice|sync|student_safe",
      "anti_pattern": "...",
      "beat_or_question": "...",
      "severity": "CRITICAL|HIGH|MED|LOW",
      "fix_layer": "IR|renderer|gate|skill|card-css",
      "fix": "..."
    }
  ]
}
```

## 5. 回炉规则

- 回炉只改 P1 表现层或 P2/P3 renderer/gate。P0 母题事实冻结,不得在修视觉时顺手改题、改答案、改采分点。
- `fix_layer=card-css` 默认有罪推定。除非 review packet 写清楚为什么不是 shared failure,否则返工到 renderer/gate。
- 同一 anti-pattern 第二次出现,必须升级 gate 或 skill;第三次出现,必须停下来重审 workflow,不能继续批量生产。
- 人眼截图墙发现的问题,优先补机器门;补不了的标 `needs_human_review`,不要伪装成全自动 PASS。
- 四模型评审是 panel 槽位,不是口头背书。当前环境能调用哪个模型就写哪个为 `PASS/FAIL`;DeepSeek/Qwen 等未接入时必须写 `BLOCKED: tool unavailable`,不能把未运行的模型写成已参与。

## 6. Done

一轮可以合入 workflow improvement,必须同时满足:

- 相关 gate 已跑,并记录 PASS/WARN/report path/sha256;`workflow_candidate/student_ready` 的 `machine_gates[]` 不得为空。
- 用户反馈视口或等价视口已进截图墙。
- `workflow_candidate/student_ready` 必须有 Remotion still review manifest,且质量门 `quality_gate.required=true/pass=true/flags=[]`。
- `build_workflow_review_packet.mjs` 已生成 review packet;若存在 issue,packet 必须写明 root-cause triage。
- `scene_visual_brief[]` 已覆盖每个主讲 scene,且每条声明 source sentence、domain objects、visual action、state change、exit 和为什么不是复用模板。
- 若把单卡写入批量 manifest 的 `promoted`,必须跑 `validate_workflow_promotions.mjs`,证明 `promotion_authority` 与 packet/IR/Remotion still 一致且 `preserved_by_batch=true`。
- 若修了视觉问题,至少新增一个 gate、anti-pattern、renderer primitive 合同或 skill 红线。
- 没有把母题事实、采分点、错因 authority 混进表现层回炉。
