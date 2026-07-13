# 鲁班智考 · 安全事故等级判定与上报 — Claude Code 接手包

这是从 Claude Design 导出的半成品。**讲解页和练习页已完成**（动画、问追AI、全屏、移动视口、TTS 播放器都已内置）。
你（Claude Code）要做的是把"浏览器临时朗读"换成**真·阿里云 longanhuan_v3 / longlaotie_v3 音色 mp3**，跑通验证 gate，再落盘到 finished。

---

## 一、包里有什么

| 文件 | 说明 |
|---|---|
| `安全事故等级判定与上报_讲解.dc.html` | 讲解页（6 主讲 beat + 4 QA），**已内置 TTS 播放器** |
| `安全事故等级判定与上报_练习.dc.html` | 练习页（6 题，含图示/采分句解析/结果页/问追AI） |
| `安全事故等级判定与上报_动画学习卡_离线版.html` | 讲解页的单文件自包含离线版（11MB，双击即开） |
| `安全事故等级判定与上报_lesson.json` | source_card / visual_archetype_decision / domain_visual_plan / storyboard / student_qa / **animation_ir.v0** |
| `tts_manifest.json` | 逐行配音清单（text / role / voice / scene / 时间窗 / est_sec） |
| `模板_讲解.dc.html` `模板_练习.dc.html` | 空白母版骨架（做下一个考点用，已含 TTS） |
| `design-system.md` | 设计系统规范（色彩/字体/组件/动画原则/红线/生产流程） |
| `support.js` | DC 运行时（**勿改**，两份 .dc.html 依赖它） |

---

## 二、TTS：页面已经在等 mp3（这是关键）

讲解页的播放器逻辑（`speakBeat()`）行为：
**播每个 beat 时，先尝试加载 `audio/<beatId>.mp3`；加载失败才退回浏览器朗读。**
所以你只要把真音色 mp3 按下面文件名丢进讲解页同级的 `audio/` 目录，**零改代码**即升级成真人音色。

### 页面期望的文件名（务必照此命名）
beatId 见 `lesson.json` / 下表。每个 beat 一个 mp3：

| 文件 | 内容 | 音色 |
|---|---|---|
| `audio/b0.mp3` | 主讲 beat0 旁白 | longanhuan_v3 |
| `audio/b1.mp3` | 主讲 beat1 旁白 | longanhuan_v3 |
| `audio/b2.mp3` | 主讲 beat2 旁白 | longanhuan_v3 |
| `audio/b3.mp3` | 主讲 beat3 旁白 | longanhuan_v3 |
| `audio/b4.mp3` | 主讲 beat4 旁白 | longanhuan_v3 |
| `audio/b5.mp3` | 主讲 beat5 旁白 | longanhuan_v3 |
| `audio/q0.mp3` | QA1：**学生问(longlaotie_v3) + 老师答(longanhuan_v3) 拼接成一条** | 双音色 |
| `audio/q1.mp3` | QA2：学生问 + 老师答 拼接 | 双音色 |
| `audio/q2.mp3` | QA3：学生问 + 老师答 拼接 | 双音色 |
| `audio/q3.mp3` | QA4：学生问 + 老师答 拼接 | 双音色 |

> `tts_manifest.json` 里是**按行**拆开的（`narr_b0` / `qa1_q` / `qa1_a` …），方便你单条合成。
> 合成后：主讲行 `narr_bN.mp3` → 重命名为 `bN.mp3`；QA 的 `qaN_q` + `qaN_a` 两条**拼接**为 `q(N-1).mp3`（q0 对应 qa1）。
> 练习页若也要配音，同样放 `audio/` 并按需扩展（当前练习页未接 TTS 播放器，可选）。

### 合成步骤
1. `.env` 放阿里云 TTS 密钥（你本机已有）。
2. 跑你的 `build_aliyun_lesson_narration.mjs --print` 先核对文本无误。
3. 用 manifest 的 text + voice 逐行合成 → 按上表命名落到 `audio/`。
4. **回填真实时长**：合成回来的 `actual_sec` 写回 timing；据此对齐 `animation_ir` 各 scene 的 `hold`，并把讲解页逻辑里的 `DUR` 与 `beats[][1..2]` 时间窗调到与音频同步（当前是估算值 DUR=198）。

---

## 三、验证 gate（按你的工具链跑）

- 源 workflow gate：`validate_lesson_source_workflow`（或同级）
- `build_aliyun_lesson_narration.mjs --print`
- `validate_animation_ir_contract.mjs`
- `render_animation_ir_preview.py` → `validate_animation_ir_preview.mjs`
- `render_animation_ir_practice.py`
- 390px 手机宽度截图
- practice 真实点击冒烟：能选择、反馈、下一题、完成结果页
- finished 目录里 HTML / practice / mp3 相对路径可访问
- 8800 本地服务 URL 可打开

## 四、过 gate 后落盘
复制全部产物到：
`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/finished/S07_safety_accident_grade_report/`

## 五、红线（继承自 design-system.md）
不做纯文字框/流程框/判断框 · 不把 6+1 当标签 · 安全合同管理类不退回文字 · 不只整页淡入淡出 · 不拿粗稿当成品 · **不用 emoji 表情** · 没过 gate/没截图/没冒烟不进 finished · 预览阶段不出 MP4。

## 六、已知质量风险（交接前如实记录）
- 等级阈值端点（恰 30 死 / 恰 1000 万等）属源 MD 🔴 待裁决项，判分为候选教学示范（`official_score_allowed=false`），给分档位未固化。
- 簇 B/C 上报+调查程序在源数据里是"真题侧·待补规范锚"，请用最新规范复核。
- 6+1 认知结构是依据源 MD"计算判定链+程序链"自行冻结，需用你的视觉原型盘点表复核。
- DUR/beat 时间窗为估算，**必须**用合成后的真实音频时长重新对齐。
