# 鲁班深母题样板用户验证与外部研究综合

- **日期**: 2026-06-18
- **状态**: `Research synthesis / Proposed`
- **从属**: 鲁班移动端提分闭环、深母题数据标准、解释型动效模板引擎 v0。
- **触发问题**: F16 防水、J01 危大专家论证、N01 网络计划三个样板已做出，但主观感觉“马马虎虎”，不确定是否击中学员痛点、是否会被喜欢、是否会带来复访。
- **方法**: 4 个专家视角并行外部查证与综合:学习科学、考试提分产品/用户研究、动画/白板/工程图解教学、AI 多专家生产线/质量门。
- **边界**: 本文不授权量产、不替代 `case_family` schema、不替代 F16 留存实验、不把 AI 多数同意当 truth。

---

## 一、总判断

现有三个样板“不够满意”的根因大概率不是动画精致度不足，而是还没有足够尖锐地回答三个用户问题:

```text
我为什么丢这几分?
我怎么写才得分?
明天换个场景我还会不会错?
```

外部研究和专家意见一致指向: **动画/白板只是入口，真正驱动成人考试备考效果的是检索练习、间隔复测、错因反馈、变式迁移和可写成采分句的输出。**

因此，F16/J01/N01 下一轮不要继续“做得更像课”，而要改成:

```text
错因驱动的 5-8 beat 考点卡
-> 先让学生判断/写/选
-> 再给白板解释
-> 给采分句
-> 立刻小练
-> D1/D7 换皮复测
```

---

## 二、外部研究结论

### 2.1 学习科学

证据最强的是:

- **Retrieval practice / practice testing**: 小测、回忆、短答本身促进长期保持。
- **Distributed / spaced practice**: 同一考点必须隔天、隔周回收，而不是当天看完即结束。
- **Worked example + faded practice**: 先给完整示范，再逐步挖空，让学生补关键判断、采分句、计算步骤。
- **Elaborated feedback**: 反馈必须指出缺哪个采分点、为什么错、下一题练什么。
- **Variant transfer testing**: 换表皮验证迁移，防止只背原题。

对鲁班的含义: **“讲懂卡”不能作为闭环终点。闭环终点必须是换皮复测和可观察的采分句输出。**

参考:

- Dunlosky et al. 2013, effective learning techniques: https://pubmed.ncbi.nlm.nih.gov/26173288/
- IES / WWC Practice Guide, Organizing Instruction and Study: https://ies.ed.gov/ncee/wwc/practiceguide/1
- Roediger & Karpicke, test-enhanced learning: https://pubmed.ncbi.nlm.nih.gov/16507066/
- Cepeda et al. 2006, distributed practice meta-analysis: https://pubmed.ncbi.nlm.nih.gov/16719566/
- Feedback meta-analysis: https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.03087/full

### 2.2 动画 / 白板 / 图解

动画有效的条件很窄: 它必须让学生看清时间顺序、空间层次、因果变化、错误点、决策阈值、关键路径。否则它只是漂亮皮肤。

鲁班应采用的是**考试采分点驱动的白板模板库**:

- 流程 / 工序模板
- 构造 / 空间模板
- 判断 / 分支模板
- 网络 / 图结构计算模板
- 正误对比模板
- worked example + faded practice 模板
- 诊断模板

红线:

- 不做长自动播放动画。
- 不做装饰性 3D/BIM 旋转。
- 不做无反馈交互。
- 不让 AI 生成图中的专业事实成为 authority。
- 不用动画教纯记忆数字。

参考:

- Mayer & Moreno, cognitive load in multimedia learning: https://www.uky.edu/~gmswan3/544/9_ways_to_reduce_CL.pdf
- Berney & Betrancourt animation meta-analysis: https://tecfa.unige.ch/perso/sandra/pdf/Earli2016_berney_betrancourt_FINAL.pdf
- Tversky et al., animation can it facilitate: https://digitalcommons.bryant.edu/apwork/1/
- Atkinson et al., worked examples: https://assess.ucr.edu/sites/default/files/2019-02/atkinsonderryrenklwortham_2000.pdf
- Multimedia learning text: https://www.jsu.edu/online/faculty/MULTIMEDIA%20LEARNING%20by%20Richard%20E.%20Mayer.pdf

### 2.3 用户验证

不要问“喜不喜欢”。要看:

1. 学员是否更快知道自己为什么丢分。
2. 是否能写出采分句。
3. 是否愿意明天回来做复测。
4. 是否在没人解释的情况下完成“做题 -> 错因 -> 复测 -> 明日任务”。

最小验证:

- **8-10 人痛点访谈**: 只问过去行为，不问愿望。
- **5 人任务型可用性测试**: 先找主要理解/使用问题。
- **5 天 concierge 留存实验**: 每天 2-3 道题 + 选错诊断 + source/采分点定位 + 明日复测开环 + 自信度 1-5。
- **真实使用后 PMF 小问卷**: 只问完成 3 次以上任务的人。

参考:

- NN/g 5-user testing: https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/
- NN/g usability testing 101: https://www.nngroup.com/articles/usability-testing-101/
- NN/g task scenarios: https://www.nngroup.com/articles/task-scenarios-usability-testing/
- Adult online learning challenges: https://openpraxis.org/articles/10.5944/openpraxis.11.1.929
- Sean Ellis PMF survey: https://medium.com/growthhackers/using-product-market-fit-to-drive-sustainable-growth-58e9124ee8db

### 2.4 AI 多专家生产线

多模型 / 多 agent 能显著提高发现错误、补盲点、反例搜索的概率，但**多数 AI 同意不能当真相**。

正确流水线:

```text
Authority first
-> RAG-grounded generation
-> 多模型候选池
-> 角色化审校
-> atomic fact verification
-> adversarial review
-> HOLD / revise / candidate release
-> 灰度真实用户验证
```

必须的质量门:

- 证据门: 无 approved source 即 HOLD。
- 检索门: context relevance / recall / sufficiency 不足即 HOLD。
- 事实门: atomic fact 逐条验证。
- 题目门: 题干唯一可解或 rubric 可覆盖多解。
- 教学门: 必须匹配认知负荷和常见误区。
- Rubric 门: 评分维度可观察、可复核、可解释。
- Judge 偏差门: 盲审、位置互换、长度归一、隐藏模型来源。
- 对抗门: 加入花哨但错误、简短但正确、伪引用、题干陷阱。

参考:

- LLM-as-a-Judge survey: https://arxiv.org/html/2411.15594v6
- Position bias: https://arxiv.org/abs/2406.07791
- Self-preference bias: https://openreview.net/forum?id=Ns8zGZ0lmM
- Multiagent debate: https://arxiv.org/abs/2305.14325
- RAG: https://arxiv.org/abs/2005.11401
- RAGAS: https://arxiv.org/abs/2309.15217
- FActScore: https://arxiv.org/abs/2305.14251
- SAFE / long-form factuality: https://arxiv.org/abs/2403.18802

---

## 三、F16 / J01 / N01 下一轮怎么改

### 3.1 F16 防水

**定位**: 留存薄切片，不是案例深母题旗舰。

下一轮目标:

- 验证忙碌成人是否愿意每天回来。
- 验证图解是否帮助他们说出“为什么错”和“怎么写得分”。

样板应改成:

```text
错法先行: 直接补铺 / 未割开排气 / 基层未处理
-> 白板揭示: 鼓包内部水汽/基层/卷材层次
-> 正确流程: 割开 -> 排气干燥 -> 清理基层 -> 处理剂 -> 附加层 -> 重铺搭接 -> 蓄水/淋水
-> 采分句: 写出处理顺序 + 关键控制点
-> 小练: 排序题 + 找错题 + 采分句补空
-> D1/D7 换皮: 地下室/屋面/节点换场景
```

通过标准:

- 学生能排对步骤。
- 能指出错误做法为什么不得分。
- 能写出至少 2-3 个采分句。
- D1 回来做复测。

### 3.2 J01 危大专家论证

**定位**: 判断链 / 阈值 / 边界档样板。

下一轮目标:

- 验证学生是否能区分“危大”和“超过一定规模危大”。
- 验证是否能写出判据，而不只是结论。

样板应改成:

```text
先给边界题: 3m / 3.5m / 5m / 5.5m
-> 让学生先判断: 非危大 / 危大编方案 / 超规模需论证
-> 白板画两级判断树
-> 揭示常错: 危大=一定论证、只写结论不写阈值、组织主体混乱
-> 采分句: 先判危大范围,再判是否超规模,最后下结论
-> 小练: 4 个边界档
-> D1 换工程类型复测
```

通过标准:

- V2/V4 这种边界题正确率提升。
- 高自信错下降。
- 学生能复述“两级判据链”。
- 能写出“结论 + 阈值依据”的采分表达。

### 3.3 N01 网络计划

**定位**: 硬能力样板，不建议作为第一批广谱留存入口。

下一轮目标:

- 验证结构化图解是否真的帮助学生完成关键线路/时差/工期调整。
- 验证 anti-over-credit: 看大意对但步骤缺失不得满分。

样板应改成 faded worked example:

```text
完整示范: 读图 -> 正推 -> 逆推 -> 总时差 -> 标关键路径 -> 结论
-> 挖空一步: 学生补正推/逆推
-> 再挖空: 学生补总时差
-> 独立变题: 改一个持续时间或逻辑关系
-> 诊断: 错路径 / 错时差 / 错工期 / 错索赔联动
-> 采分句: 写关键线路、总工期、调整影响、理由
```

通过标准:

- 学生能独立重算，而不是背原图。
- 变题后关键路径正确。
- 能写出步骤分表达。
- 对“答案对但过程缺失”的评分边界更清楚。

---

## 四、样板是否击中痛点的判定表

| 判断项 | 通过信号 | 失败信号 |
|---|---|---|
| 错因命中 | 学生能说“我丢的是哪一分” | 只说“我不会/我粗心” |
| 得分导向 | 学生能写出采分句 | 只会复述知识点 |
| 图解价值 | 学生能指出图比文字多解决了什么 | 觉得好看但说不出帮助 |
| 复测拉力 | Day 2 主动/半主动回来 | 当天看完就结束 |
| 迁移 | 换皮题还能对 | 原题对、变题错 |
| 信心校准 | confident-wrong 下降 | 越学越自信但仍错 |
| 信任 | source/ref 增强信任 | 质疑 AI 胡讲或不看证据 |

---

## 五、推荐执行顺序

本周不要同时改三个方向到很深。建议:

1. **押 F16 做 5 天 concierge 留存实验**。
2. **押 J01 做 5 人任务测试**，验证判断树和边界档是否有“啊哈”。
3. **N01 暂停作为第一入口**，只做专项硬能力测试，除非访谈显示网络计划是当前 cohort 的第一痛点。

具体安排:

| 天 | 动作 | 产物 |
|---|---|---|
| Day 0 | 8-10 人访谈脚本 + 5 人任务测试脚本 | 痛点假设与分层 |
| Day 1 | F16 Day1 卡: 错法先行 + 小练 + 自信度 | 首次完成率 / 耗时 / 失分原因复述 |
| Day 2 | F16 D1 换皮复测 | D1 回访与迁移 |
| Day 3 | J01 5 人任务测试 | 边界档理解 / 采分句输出 |
| Day 4 | F16 Day3 / Day4 留存继续 | 同错因复发率 |
| Day 5 | PMF 小问卷 + 访谈回收 | 是否主动要下一张 / 是否愿推荐 |
| Day 7 | 延迟复测 | D7 保持 |

---

## 六、红线

- 不以“喜欢动画”作为成功。
- 不以看完率、停留时长、点赞作为主指标。
- 不把多数 AI 同意当 truth。
- 不把 F16 误包装成案例判分旗舰。
- 不让 N01 的复杂图解拖慢第一批留存验证。
- 不在 D1/D7 留存和迁移没证明前量产 20-30 张卡。

---

## 七、最终建议

当前三个样板都值得保留，但下一轮要从“内容展示”转成“可验证得分动作”。

最短路径:

```text
F16 验证回访
J01 验证判断链痛点
N01 验证硬能力和 anti-over-credit
```

如果三者都只提升“觉得好看”而不提升采分句输出、换皮迁移和 D1/D7 回访，就判定为花哨失败；如果 F16 能拉回访、J01 能制造边界档啊哈、N01 能提升独立重算能力，再进入第二轮资产签发与小程序真实入口验证。

---

## 八、落地对齐:母题 journey ↔ v1.3 每日留存闭环 + 考点路线图(2026-06-18 补)

> 本节补充依据:用 2026-06-17 **完整邀测数据(70 报名 / 4 深度反馈)** 再跑 4 专家(学员之声 / 知识点结构 / 学习科学路径 / 产品留存),结论与 `canonical PRD v1.3` **独立收敛、一字不差**(留存闭环为主菜、案例批改为深度层、痛点=记不住/薄弱章节/案例不会写)。即:学习路径方向无需重定,v1.3 仍是 authority;本节只补两件 v1.3 与前几轮 journey 工作之间没写清的衔接。

### 8.1 真结论:不是"单点单卡 vs 综合考点"二选一

四专家 + 知识结构实证收敛:
- 学习单元 = **考点层(~55-60 高频,P0 ~20)**,不是 taxonomy 叶逐点(1976 太碎、复刻题库、强化挫败),也不是整章。
- 案例题(218 道、单题 20-30 分=分值主体)是**踩点制综合命题**(均值 2.69 采分点/题、跨判断+计算多类型)——结构上就要求"综合考点"承载。
- 选择题(337 道)才适合单点 MCQ 轻练。
- **前台不卖"知识点通关",按盲点驱动**(对齐 v1.3 §83)。

### 8.2 journey 必须拆开对齐 v1.3 的"2 分钟碎片留存",别整段强推

前几轮做的 `render_archetype_journey`(讲懂动画→闯关→看穿,一镜到底,~2-3 分钟)**偏重**,不等于 v1.3 的"每日 2 分钟 MCQ 轻练"。对齐方案:

| journey 段 | 对齐 v1.3 留存闭环的角色 | 日常是否默认出现 |
|---|---|---|
| 闯关(母题变题 MCQ) | = v1.3「2 分钟知识点/母题 MCQ 轻练」 | ✅ 日常主体 |
| 看穿(真懂/背过 + 采分点/教材章节定位) | = v1.3「盲点诊断 → 错选项→采分点/章节定位 → 明天复测什么」 | ✅ 日常主体 |
| 讲懂动画(PPT+SVG,~1-2 分钟) | = 深度护城河层入门,**盲点触发的"看不懂?点开讲透"下钻** | ❌ 不每次强推,按需 |

即:**日常留存 = 闯关 + 看穿(碎片、低门槛、补盲点而非被挑错);讲懂动画降级为按需下钻**——和学习科学专家"A 单卡降级为闭环内下钻"同构。这样 journey 既是 v1.3 留存闭环的母题单元实现,又把"深度"留到养成习惯后。

### 8.3 考点路线图(母题铺设定序,登记指针)

排序权威 = `docs/原始数据/数据盘点/2026-06-17-图解微课考点地图.md`(~55-60 考点,真题频次×采分密度排序,P0~20)。P0 头部:危大论证 ✅J01(stem 第1,80命中/11年)、施工缝 ✅C01、网络计划 ✅N01、防水起鼓 ✅F16,待铺:脚手架/模板支架、起重吊装、进度款计量、基坑支护、混凝土养护、检验批验收、质量通病、模板拆除。母题**按此序铺**,每个都落进 v1.3 留存闭环,不全量拆教材。

### 8.4 优先级与红线(对齐 v1.3 硬约束)

- **先止血再铺量**:补"做题→判分→给答案→正向反馈"闭环(对应 `mcq_grading` 路由缺口/"答题必有解析"铁律)——4 专家两个独立点名"只考不给答案、负反馈打击信心"是流失第一杀手,优先级高于再造母题。
- MCQ 必须 `case_family`/`scoring_point`/`knowledge_node` 锚定,错选项映射 canonical `mistake_tag` + 教材章节定位,写同一份 `learning_evidence`,复测走既有 `revalidation_queue`(v1.3 §41);不建第二套题库/记忆/推荐 authority。
- 看穿文案先捧→就差一步→我相信你,绝不毒舌(补盲点而非挑错)。
- 样本小(4 反馈/70 报名)= 信号非定论,但与 v1.3 同批数据 + 四专家独立收敛,方向可信;量产仍 gated on retention(F16 留存实验)。
