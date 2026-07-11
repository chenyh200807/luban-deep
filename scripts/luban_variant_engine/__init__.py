"""鲁班变体池数据驱动引擎（2026-07-11 宏观审计工单②：18 个手写 builder 收敛为一）。

设计来源=收敛谱侦察（账本 2026-07-11）：18 个 builder 有 ~200 行逐字节同构样板，
真差异只有模块级规则数据 + 判定分支——即"规则进 spec(JSON)，引擎唯一"。

模块划分：
- spec.py        加载+校验 per-pack spec（含 threshold 取值域横跨阈值的健康检查）
- generators.py  8 判定原语的变体生成器（对偶在此层强制成对）
- predicates.py  命名谓词注册表（e05 挣值/n03 gcd 等命令式逃生舱）
- verdict.py     独立第二实现：从 params 重推 expected_ok（与生成器互证）
- gate.py        三门（verdict_mismatch / contested_leak / duplicate_surface）
- build.py       CLI：--pack X02 [--check]，payload 形状与旧 builder 逐字段兼容

迁移纪律：试点 X02→F16→G03；每站以"引擎产物 variants 与现有 signed bank
逐字段全等（或人核语义等价）"为过闸判据；旧 builder 在全量迁移完成前不删。
"""
