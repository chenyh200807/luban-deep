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
  --gate validate_animation_ir_preview=PASS:0 \
  --gate validate_challenge_theater_practice=PASS:0 \
  --screenshot 390x844=artifacts/luban_case_family_assets/diagram_microlesson/<topic>.390.png \
  --out artifacts/luban_case_family_assets/diagram_microlesson/<topic>.workflow_review_packet.json
```

packet 可以先写 JSON,后续再接自动 judge 和截图墙 UI。最小字段如下:

```json
{
  "card_id": "F16_qigu",
  "round": 2,
  "stage": "P4_review",
  "machine_gates": [
    {"name": "validate_animation_ir_contract", "status": "PASS", "warn": 0},
    {"name": "validate_animation_ir_preview", "status": "PASS", "warn": 0},
    {"name": "validate_challenge_theater_practice", "status": "PASS", "warn": 0}
  ],
  "screenshots": [
    {"viewport": "390x844", "path": "...390.png", "looked": true, "issue": ""},
    {"viewport": "844x390", "path": "...844.png", "looked": true, "issue": ""},
    {"viewport": "user_feedback", "path": "...1432.png", "looked": true, "issue": "right panel text clipped"}
  ],
  "judge": {
    "verdict": "FAIL",
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
| 字挤、字裁、节点塞不下 | renderer + gate | 新图元规则 + label/text gate |
| 全屏/横屏比例错 | learning-stage shell + runtime gate | 对应真实视口截图 |
| 像翻页、没动作 | IR/actions + renderer | 每 scene 至少一个 action 可见变化 |
| 音画不同步 | timing + narration + preview/remotion gate | sync_keyword 和关键帧 |
| 题目无图或选项不像采分句 | practice generator + mother data binding | variants/source/scoring 追溯 |
| 人眼发现但机器绿 | gate + anti-pattern | 先补 gate/anti-pattern,再修页面 |
| 图元只在一侧 renderer 可用 | contract gate + renderer | HTML/Remotion primitive coverage 双绿 |
| 只影响一张卡的极小视觉瑕疵 | card CSS 可例外 | 写明为什么不是 shared shell/renderer/gate 问题 |

## 4. Judge Prompt 骨架

LLM judge 只评表现和学习体验,不重写事实。输出必须是结构化反馈:

```text
你是鲁班动画学习卡评审。只基于给定 IR、HTML gate 输出、截图和母题摘要评审。
不要改考点事实、采分点、错因或答案。只判断表现层是否帮助学生拿分。

必查:
1. hook/main_exam_action 是否一线贯穿
2. 每个 beat 是否有可见 action,不是整页翻片
3. 镜头是否筛注意力:focus 放大/高亮/暗化/退出是否服务当前句
4. 字幕/coach 是否跟画面同步,不遮挡
5. practice 是否独立、每题有图、选项可转化为采分表达
6. 截图墙是否存在拥挤、裁切、小片化、控制条遮挡
7. 发现问题时应归因到 IR、renderer、gate、skill 还是 card-css

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

- 相关 gate 已跑,并记录 PASS/WARN。
- 用户反馈视口或等价视口已进截图墙。
- `build_workflow_review_packet.mjs` 已生成 review packet;若存在 issue,packet 必须写明 root-cause triage。
- 若修了视觉问题,至少新增一个 gate、anti-pattern、renderer primitive 合同或 skill 红线。
- 没有把母题事实、采分点、错因 authority 混进表现层回炉。
