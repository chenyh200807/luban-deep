# type-contrast · ⑤ 对比/正误原型

- **何时选**:考点本质是"对的做法 vs 错的做法"的辨别——案例题"指出不妥之处,并写正确做法"高度契合。
- **代表考点**:对/错做法、规范 vs 非规范表达、质量通病(蜂窝麻面/空鼓开裂/渗漏)、洞口临边防护。
- **展现形式**:左右正误对照(左=错误现场/写法,右=正确做法)。
- **语义色**(引用 style-guide 铁律):**绿=对 / 红=错**,永不互换;对应采分点用 `--partial` 琥珀标"差一口气"。
- **交互**:点查"为什么扣分" / 点正确做法看采分表达。
- **祖师爷参照**:**安全培训 do's & don'ts**(OSHA 式 permitted/restricted 信息图)+ eLearning 正误对照——**左右并排 + 红错绿对,利用大脑视觉处理快速区分对错**;成熟、低风险。
- **schema body**:`contrast_items[]`(每项 `id/axis` + `wrong{text,loss_display}` + `right{text,scoring_expression}` + `scoring_point_binding`(引用,不复制采分点)+ `role:candidate`)+ 脊柱。采分点单独在 `scoring_points[]` 定义一次(带 `kind` + 候选 source_ref 后缀);错因码 `error_code` 进 `common_errors[]` 的 **internal_only**,学生端只显 `loss_display` 汉语名。
- **验收点(原型专属)**:① 错例是**真误解非稻草人**(取自真实失分表达,不是夸张错法);② 每对错→对经 `scoring_point_binding` 映射到 `scoring_points[]`,**引用不复制**(reference-not-duplicate);③ student-safe:`loss_display` 汉语名上屏,`error_code`(E03/E06)/`scoring_point` id/`source_ref` 只进 internal_only;④ **暖度双评**——错例陈述客观不毒舌 + `warm_correction` 先肯定方向再给关键词,不打击新生。
- **现状**:✅ 草稿 `artifacts/luban_case_family_assets/diagram_microlesson/C01_construction_joint_contrast.schema_draft.json`(施工缝留置;`contrast_pair_reveal_draft`,无 contrast renderer,schema 先行同 D01)。是 panel 加固的参考实现。可与 ⑥诊断共用错因/采分点资产;动 renderer 前先硬化:template_type 分派 + body 互斥 + student-safe 白名单。
