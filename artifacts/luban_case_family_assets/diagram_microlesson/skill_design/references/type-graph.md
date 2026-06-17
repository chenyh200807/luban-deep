# type-graph · ③ 计算/图结构原型

- **何时选**:考点本质是"可计算的图/网络/时间约束",答案能从结构化数据推出。
- **代表考点**:双代号网络计划、关键线路、总时差/自由时差、流水节拍/步距、工期优化。
- **展现形式**:图高亮 / 可推演(节点+边,自动算+高亮)。
- **语义色**(引用 style-guide):`--critical` 红=关键线路;普通节点中性;时差用 `--partial` 琥珀标。
- **交互**:拖节点 / 试算 / 高亮关键线路 / 工期优化前后对比。
- **祖师爷参照**:**算法可视化线**——VisuAlgo(**演示"算法过程"而非只给答案**:逐步算最早/最迟/时差→高亮关键线)、3Blue1Brown/Manim(图)、D3 DAG、CPM/PERT 工具。核心招:**步进展示计算过程**,不是直接甩结果。
- **schema body**:`question_data{activities, dependencies, expected{critical_path, project_duration, float}}`;`compute_cpm` 只是 **build 期自洽校验器**,非 scoring authority。
- **验收点(原型专属)**:计算规则不可误植;`expected` 前端只读(不前端重算);关键线路/时差可复算校验通过。
- **现状**:✅ 已有 `../N01_network_keypath.json` + `../render_network_card.py`(用独立窄渲染器,暂不与 process 型合并)。authority 待绑真题 source_ref(现为 candidate)。
