# F16 屋面卷材防水起鼓割补 - OpenMAIC 输入包

> 用途：把 DeepTutor/鲁班的母题数据基础喂给 OpenMAIC，生成互动白板课/动画讲解/测验。  
> 输入原则：事实层来自母题数据和 runtime supply；OpenMAIC 只负责表现编排，不改事实、不新增采分 authority。

## 0. 直接使用方式

把本文件整体作为 OpenMAIC 的 topic/document 输入。要求 OpenMAIC 生成时遵守：

1. 先讲为什么学：这是屋面卷材防水质量通病题，学生常丢分在“只写修补防水层”，没有写出病因处理和防水闭环。
2. 先白板讲解，再互动练习：前半段用屋面剖面逐步 reveal；后半段用错因判断和变式题检测。
3. 画面类型：`process_step_reveal` 为主，辅以 `wrong_vs_correct_contrast`。
4. 不得把本资料说成官方阅卷；只能说“培训机构教研估分/教学示意”。
5. 不要直接照抄旧 HTML 视觉；旧 HTML 只能参考，不是事实源。

## 1. 核心本体

- `topic_id`: `roof_membrane_bulge_repair`
- `card_id`: `F16_qigu`
- `master_id`: `M_roof_bulge_repair`
- `taxonomy_ref`: `1A434000`
- `title`: 屋面卷材防水 · 起鼓割补
- `exam_point`: 屋面卷材防水起鼓怎么修补（割补工序）
- `authority_boundary`: 培训机构教研估分，非官方阅卷；图形是教学示意，不是规范详图。

## 2. 一句话母题不变量

修补结构恒定：

> 治病因：沿鼓泡割开放气 -> 排气干燥 -> 清理基层/处理剂  
> 恢复防水闭合：嵌填找平 -> 增铺附加层盖过病害边缘 -> 新卷材搭接封严  
> 检验闭环：蓄水/淋水检验确认不渗漏

换皮只换病害部位、材料、病象；“先治因 -> 再恢复防水 -> 再检验”的闭环不变。

## 3. 出题人意图

考的不是背八个动作，而是有没有把“治病因 -> 恢复防水闭合 -> 检验”写完整。最容易漏：

- 基层处理
- 附加层盖过边缘
- 搭接封严
- 蓄水/淋水检验

## 4. 学习目标

学生能把“起鼓割补”从一句泛泛的修补，拆成可得分的施工闭环：

1. 识别起鼓
2. 割开排气
3. 干燥清理
4. 基层处理
5. 嵌填修补
6. 增铺附加层
7. 重铺封严
8. 检验闭环

## 5. 场景解释

卷材与基层之间夹气或夹水，受热膨胀形成鼓泡。修补的核心不是“盖一层新卷材”，而是先释放病因，再恢复层间连续防水。

建议画面：

- 剖面：基层、找平层、防水卷材、鼓泡
- 动画：鼓泡隆起 -> 切开 -> 气/水汽排出 -> 干燥清理 -> 附加层覆盖 -> 新卷材搭接封严 -> 蓄水检验
- 强调：每一步出现时只突出当前动作，其他区域降亮。

## 6. 工序步骤与采分表达

| 步 | step_id | 屏幕标签 | 讲解重点 | 采分表达 |
|---|---|---|---|---|
| 1 | `identify_bulge` | 识别起鼓 | 先识别起鼓，不要直接写“加强维修” | 检查并确认卷材防水层起鼓部位，分析为基层潮湿、气体未排尽或粘结不牢等原因造成。 |
| 2 | `cut_bulge` | 割开鼓泡 | 沿鼓泡割开，先释放内部气体 | 沿起鼓部位割开，使鼓泡内部气体或水汽排出。 |
| 3 | `vent_dry` | 排气干燥 | 排气、干燥，这是很多人漏掉的关键 | 排尽气体和水汽，使基层及卷材下表面充分干燥。 |
| 4 | `clean_prime` | 基层处理 | 清理基层，再补刷基层处理剂 | 清除旧胶结料和杂物，清理、干燥基层，必要时补刷基层处理剂。 |
| 5 | `fill_repair` | 嵌填修补 | 基层缺陷先补平 | 对切开后暴露的凹陷、裂缝或缺陷进行嵌填、修补、找平处理。 |
| 6 | `reinforcement_layer` | 附加层 | 附加层要盖过病害边缘 | 在修补部位增铺附加层，附加层应覆盖并超出原起鼓或切割边缘一定范围。 |
| 7 | `new_membrane_seal` | 新卷材封严 | 新卷材要搭接、压实、封边 | 喷灯烘烤软化后分层剥开旧卷材，铺贴新卷材并压实，与原防水层搭接牢固，边缘和搭接缝应封严。 |
| 8 | `water_test` | 检验闭环 | 最后做蓄水或淋水检验 | 修补完成后进行蓄水或淋水试验，检查确认无渗漏后方可验收。 |

## 7. 候选采分点

> 注意：这是候选采分点引用，不是官方阅卷 authority。

- `P10`
  - 分值候选：`0.75`
  - 关键词：放气、擦干、清除旧胶结料
  - 对应步骤：`cut_bulge`、`vent_dry`、`clean_prime`
- `P11`
  - 分值候选：`0.75`
  - 关键词：喷灯烘烤、分层剥开、重贴新卷材
  - 对应步骤：`new_membrane_seal`

## 8. 学生常见错误

| 错误 id | 错误表达 | 为什么丢分 | 应跳回步骤 |
|---|---|---|---|
| `weak_repair` | 修补防水层，加强处理。 | 表达过泛，缺少病因处理和具体工序。 | `cut_bulge` |
| `direct_cover` | 在鼓泡处直接加铺一层新卷材。 | 程序顺序错误，漏排气、干燥、基层处理和新旧搭接闭合。 | `vent_dry` |
| `missing_reinforcement` | 割开晾干后重新铺贴。 | 漏附加层和搭接封严，方向对但不够采分。 | `reinforcement_layer` |
| `no_test` | 重贴卷材后结束。 | 缺少蓄水或淋水检验，工程闭环不完整。 | `water_test` |

## 9. 记忆钩子

> 先放气干燥，再附加封严，最后试水闭环。

## 10. 建议旁白骨架

开场：

> 这题不是背八个动作，是看你有没有把起鼓修补的闭环写完整：先治病因，再恢复防水，最后检验不渗漏。

逐步讲：

1. 先认病：卷材下面的气和水汽顶起来，形成鼓泡。
2. 沿鼓泡割开，先放气；不放气就盖新卷材，还会再鼓。
3. 排尽气和水汽，让基层和卷材底面干燥。
4. 清除旧胶结料和杂物，必要时补刷基层处理剂。
5. 基层有凹陷、裂缝，要先嵌填修补找平。
6. 增铺附加层，盖过病害边缘，包住薄弱区。
7. 铺新卷材并压实，与原防水层搭接，边缘和搭接缝封严。
8. 最后蓄水或淋水检验，确认不渗漏才验收。

收束：

> 你只要记住一条线：治病因、恢复闭合、检验闭环。题干换成卫生间、地下室、局部空鼓，也按这条线迁移。

## 11. 互动题

### 题 1：漏点判断

学生答案：“将鼓泡处割开，排气擦干后直接铺贴新卷材并压实。”这份答案最可能漏掉哪类关键表达？

- A. 漏写起鼓病害识别
- B. 漏写基层处理、附加层和搭接封严闭合
- C. 漏写施工单位责任
- D. 漏写卷材品牌和型号

正确答案：B  
反馈：它有割开、排气、干燥，但直接铺新卷材，少了基层处理、附加层覆盖和搭接封严。

### 题 2：程序判断

现场图省事，在鼓泡处直接加铺一层新卷材盖住。这样做对吗？

- A. 对，省时又快
- B. 不对：没放气干燥处理基层，底下气和水汽会再把它顶鼓
- C. 不对，应把整片屋面卷材全部铲除重做

正确答案：B

### 题 3：迁移判断

换个场景：卫生间地面防水层局部空鼓、有渗漏。核心修补思路应是？

- A. 直接在地面重铺地砖盖住
- B. 同样：割开放气 -> 干燥处理基层 -> 附加层 -> 新防水层搭接封严 -> 闭水试验
- C. 只在表面再刷一层防水涂料

正确答案：B

### 题 4：闭环判断

起鼓割补，做完“放气、干燥、基层处理、附加层、新卷材搭接封严”，就可以收工了吗？

- A. 可以，防水层已经恢复
- B. 还差一步：做蓄水或淋水检验，确认不渗漏才验收
- C. 还要在上面再加铺一整层卷材

正确答案：B

## 12. 可引用的上游数据文件

核心输入：

- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.json`
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/M_roof_bulge_repair.master.json`

可选输入：

- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.lesson.json`
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.lesson.timing.json`
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/F16/F16_deep_moat_questions_draft.md`

上游事实支撑：

- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/topic_waterproof.json`
  - 重点节点：`1A434000-B017` 屋面卷材起鼓；`1A434000-B018` 屋面工程施工过程检查与检验；`1A413050-R07` 卷材防水层施工。
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/runtime_supply/v_lecture_answer_skill_pack_all8/shards/waterproof-energy-decoration.json`
  - 重点：防水工程分值、屋面防水构造、卷材防水施工、验收与易错提醒。

只作视觉参考，不作事实源：

- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/F16/F16_qigu_svg_diagram_experiment.html`
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/F16/F16_roof_blister_repair_whiteboard_v2.html`
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.rendered.html`

## 13. 给 OpenMAIC 的生成指令

请基于上面的母题事实，生成一个中文互动课堂。目标不是泛泛讲防水，而是让一建建筑实务学生掌握“屋面卷材起鼓割补”的考试得分闭环。

输出要求：

1. 第一幕必须先抓痛点：为什么这题容易丢分、阅卷看什么、学生常写错什么。
2. 第二幕用白板剖面动画展示起鼓病因和割补流程，逐步 reveal，每步有一句采分表达。
3. 第三幕展示错误做法 vs 正确做法，尤其强调“直接覆盖新卷材”的问题。
4. 第四幕做 4 道互动题，难度递进：漏点判断 -> 顺序判断 -> 场景迁移 -> 检验闭环。
5. 最后一幕输出一句考试答案模板：

> 检查确认起鼓部位，沿鼓泡割开放气，排尽气体和水汽并干燥基层，清除旧胶结料、处理基层，必要时嵌填找平，增铺附加层并覆盖起鼓边缘，重铺新卷材与原防水层搭接压实、封严，最后进行蓄水或淋水试验确认无渗漏。

视觉要求：

- 手机优先，16:9 横屏和 9:16 竖屏都能看。
- 少文字，大图解，关键动词逐个出现。
- 每次只强调一个焦点：放气、干燥、附加层、封严、试水。
- 不要做成普通 PPT 翻页，要有“病因出现 -> 动作介入 -> 防水闭合恢复”的连续感。
