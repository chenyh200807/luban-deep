# narration-spec.md · 图解微课旁白派生总纲

> **旁白 = 卡内容的"朗读版",从 schema 结构化字段派生,卡是唯一源。**
> 不手写、不新增知识、不改判据。每张卡按本总纲自动生成"每块一段"的旁白;改卡 → 旁白自动同步;新卡 → 自动有旁白。

## 为什么要总纲(单一权威)

手写旁白会制造**双份 truth**:卡内容一份、旁白一份镜像,两者会漂移(改了采分点/对照,旁白对不上),且每张卡都要手写、不可量产。总纲把"内容→旁白"收成**一条派生规则**:旁白只是把卡上已有的字段按固定句式读出来。

## 派生结构:按固定教学顺序遍历内容块

一张卡的旁白 = 顺序遍历下列内容块,**每块派生一段**,每段绑一个 `anchor`(播放到该段时高亮/reveal 对应块):

```
开场(why) → 主体块(按原型:对照/工序/诊断,逐项一段)→ 采分关键(scoring)→ 暖收尾(wrap)
```

## 块类型 → 句式模板(字段插值,固定连接词)

| 内容块 | anchor | 触发字段 | 句式模板 |
|---|---|---|---|
| 开场 | `why` | `scenario.caption` > `why_lose_points` > `student_goal` | `{caption}。我们一个一个看。` |
| ⑤对照轴(逐项) | `item:<id>` | `axis`+`wrong.loss_display`+`right.scoring_expression` | `{先看/再看}{axis}。常见丢分是{loss_display};记住要写:{scoring_expression}。` |
| ①工序步(逐项) | `step:<id>` | `action`+`scoring_expression` | `{第N步},{action}。要写到:{scoring_expression}。` |
| ⑥诊断点(逐项) | `dx:<spid>` | `status`+`gap` | `这一点{命中/部分/没给分}。{gap}。` |
| 采分关键 | `scoring` | `scoring_points[].keywords`(去重) | `这道题的采分关键就这几组词:{kw1、kw2…}。写到了就稳。` |
| 暖收尾 | `wrap` | `memory_hook`(+固定暖收束) | `把这两组采分词记牢,这类题就稳了。记住:{memory_hook}。` |

**序数连接词**:对照/工序多项时,第一项用"先看/第一步",其余用"再看/第二步…"。

## 精简取向(默认)

旁白默认**精简**:对照轴只读「点错(`loss_display`)+ 采分表达(`scoring_expression`)」,**不读完整 `wrong.text`/`right.text` 长句**;收尾只读 `memory_hook`。完整错法/正确做法/暖纠正**已在卡上视觉呈现**——听觉精简、视觉完整、互补,把一张卡的旁白压到约 1 分钟内。若要详尽版(读全),在派生器对照轴/收尾分支换回完整字段即可。

## 铁律

1. **只朗读卡上已有内容**,不新增知识、不改判据(旁白措辞=字段值,模板只加连接词)。
2. **student-safe**:旁白只用 `rendering_contract.student_safe_fields` 里的字段;绝不读 `source_ref`/`error_code`/采分点 id/`kind`/`candidate` 等内部词(总纲只引用白名单字段,天然安全)。
3. **暖**:收尾用 `warm_correction` 的肯定语气,不毒舌(见 [[wow-see-through-must-be-warm-not-harsh]])。
4. **旁白不进 schema 手写**:`narration.segments[].text` 由派生器生成,schema 只配 `narration.voice_hint`(配音音色)。这保证单一源、可量产、永不漂移。
5. **HTML 字段先去标签**:`why_lose_points_html`/`warm_correction_html` 朗读前剥 `<b>` 等标签。

## 实现

`build_card_narration.mjs::deriveNarration(schema)` 按本总纲从字段拼 `segments[]`(text+anchor)→ 逐句配音 → `mp3` + `timing.json`。渲染器只读 `timing`(已含派生 text),不参与派生。

> 总纲(本文)是 **fat skill**(规则单一源),`deriveNarration` 是 **thin wrapper**(执行规则)。换原型只在表里加一行块类型,不改派生器骨架。
