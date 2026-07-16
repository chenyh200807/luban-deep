# 签发变体接入 practice 资格框架 — 设计 + S05 首切片（2026-07-16）

## Start Frame / Root-cause frame

- **One business fact**：每条变体回答一个问题——"这条变体验证的是哪个已签发事实（fact_id）"。
  fact 命名空间与 compiled MCQ 完全同一（`{pack小写}-fact-{语义slug}`，N01 已有先例），
  同一 fact 的 MCQ 与变体互认：D+1 首验用 MCQ，错后当场确认与 D+3 抽查用变体。
- **One authority**：变体的资格真值 = **bank 原位 per-item `decision` 块**（仿 per-Pack
  practice artifact v3 的原位演进），由 `practice_html._review_is_signed/_eligible`
  **同一谓词**裁决——同一资格门语义、同一双签结构（teaching+scoring）、同一 checks 集，
  不新建平行 authority。撤发 authority 仍是 `_variant_blocklist.json` 唯一一份：
  `revoked` 在投影时从 blocklist **派生**，绝不落盘第二份撤发状态。
- **现状**（盘点，2026-07-16）：18 个 bank 文件；17 signed（E05=candidate 不算），
  signed 共 1029 条，剔 extension 与 blocklist 后 active core = **979 条**，全部 sha
  锚定当前 manifest。**N01 有变体银行**（43 条，全 active core）——轻练对 N01 无 bank
  缺口；缺的是与全体 bank 相同的 decision 块（本设计的对象）。compiled MCQ 共 633 条，
  仅 N01 7 条已签（fact 命名先例来源）。上线后变体供给熄灭的根因 = compiled pack
  `禁回退 signed bank` 的裁决（read_model.build_retest_items）；本设计不推翻该裁决，
  而是给变体一条**按 fact 寻址**的新消费入口，不走 mode 回退。

## 1. 变体如何获得 fact_id / skeleton_id

- **fact_id（人签，机器候选）**：机器按 `(rule_group, correct_statement)` 聚类提案
  （S05 实测 15 个聚类干净落出 15 个事实候选），锚 = 变体 `anchor` 的 kc 部分，
  佐证 = 同 pack 签发考点卡的 `point_id` join 出的教材原文。
  - 方案 A（选定）：fact_id 是 decision 块字段，人在决策卡上签；机器只出候选。
  - 方案 B（否决）：`{pack}-fact-kc-{point_id}` 纯机械映射。否决理由：一个 kc 点承载
    多个事实（S05 `…0016:1` 同时挂送电/停电两序），MCQ 侧 fact 是人签语义 slug——
    机械映射会错并/错拆事实，且与 N01 已签 MCQ 命名断裂。
  - **命名空间对齐**：变体 decision 与 MCQ decision 写**同一个字符串**即互认；先签的
    一方（当前是 MCQ N01 / 变体 S05 候选）成为该 fact 的命名先例，候选文件里给出
    kc 锚 + 教材原文 + compiled MCQ 疑似同 fact 题号，供审核对齐。
- **skeleton_id（机械派生，人可改签）**：`{pack小写}-vskel-{rule_group小写}-{ok|bad}`。
  骨架是呈现多样性键、非真值断言，机械派生够用；`expected_ok` 进骨架使同 fact 的
  正/反面天然成两骨架（当场确认与 D+3 可换面出题）。
- **probe_role**：沿用现有枚举（不扩枚举=不动共享门）。变体只占
  `immediate_confirm`（错后当场确认）与 `d1_probe`（延时抽查探针，D+1/D+3 语义由
  排程层区分，不由 role 区分）；`anchor` 永远归 compiled MCQ（D+1 首验不动）。
  机器候选在每个 fact 内按 variant_id 排序交替分配双 role，保证双池非空。

## 2. 富化字段（temptation / loss_reason）放哪

- **bank 原位 decision 块**（选定）。manifest 不动（bank 本就不进 manifest，靠
  `source_pack_sha256` 锚定；不新增 pointer 表）。
- 富化文案是学员可见内容，必须被签名覆盖：`content_sha256` = 变体内容载荷
  （variant_id/rule_group/surface/params/expected_ok/correct_statement/anchor/extension）
  **+ temptation + loss_reason** 的 canonical sha；`review.reviewed_content_sha256`
  必须等于它——签后改文案即失效，fail-closed（与 MCQ 的 options 内含
  temptation/loss_reason 被 content_sha256 覆盖同构）。
- checks 五项名字不变（同一谓词），变体语境语义映射：`longest_option_checked` ≡
  长度/风格 tell 检查（audit_variant_style_tells 口径）、`diagnosis_verified` ≡
  temptation/loss_reason 教研核验；映射写进审核包 instructions。

## 3. 消费路径

- **轻练（错后当场确认）**：输入 = 刚错的 compiled MCQ item 的 fact_id（633 MCQ 签发
  后逐题携带）。从该 fact 的 eligible 变体中取 `probe_role=immediate_confirm`、
  骨架 ≠ 刚错题骨架者，(user, fact, attempt) 确定性选取。
- **D+3 抽查**：输入 = due probe 的 fact（review_due/revalidation_queue 投影）。取
  `probe_role=d1_probe` 的 eligible 变体，骨架避开该用户 D+1 已见骨架。
- **supply kind：复用 `signed_variant`，不并入 compiled**（结论）。理由：
  ① `retest_selection._valid_supply` 与 writeback 已认这个 kind，零新 authority；
  ② 并入 compiled artifact = 签发内容第二份拷贝 + 双漂移面，且任何变体改动都要
  重签 practice artifact；③ "compiled pack 禁回退 signed bank" 针对 mode 面
  （forward/review 场次），fact 寻址的 probe 供给是另一条输入线，两者并存不矛盾——
  资格语义已经由同一谓词统一（同一杆枪，第二种弹药）。
  selection/writeback 沿用现签名链：digest = eligible 变体供给 canonical sha。
- 本切片**不接线** endpoint/selection；只交付资格投影与审核供给（见 §5 不做）。

## 4. 签发流程（复用现有流水线）

1. **审核包**：`publish_luban_preview_cards.py --write-practice-audit-packet
   --kind variant s05` → `成品/_practice_review_packets/s05.variant.review.json`
   （schema `luban_variant_review_packet.v1`，逐条 pending，human_gate
   machine_must_not_sign=true，含 checks 语义映射 instructions）。
2. **机器候选（绝不签名）**：`scripts/prefill_variant_decision_candidates.py S05` →
   `s05.variant.decision.candidates.json`（`machine_candidates_only: true`，同
   anchor candidates 惯例）：fact/skeleton/probe_role 提案 + temptation/loss_reason
   初稿 + 教材原文佐证 + MCQ 同 fact 疑似题号。确定性输出（无时间戳），可重跑比对。
3. **决策卡 + 异源对抗**：沿用变体 statement 对抗面板惯例（2026-07-11 验尸同款），
   对抗结论走 blocklist（撤）或候选修订（改）。
4. **verdict 转写**：审核包签妥后 bake 进 bank 原位 decision 块（identity 校验 =
   content_sha256 逐条比中，drift 即 fail），bank 状态回 candidate →
   `promote_variant_bank.py` 人闸重签（工具已有 --kind 表，校验语义不变）。
   **已知缺口（下一步，非本切片）**：bank builder 重建会丢原位 decision，需教
   builder 按 variant_id+content_sha256 保留合并（镜像 practice publisher 的
   `_load_practice_review_records` 模式）后 bake 步才能落地。

## 5. 明确不做

- 不动 D+1 首验（633 compiled MCQ 是唯一 anchor 供给）；不动 forward/review mode
  的"禁回退 signed bank"裁决；不新建表/store/endpoint；不改 `_PROBE_ROLES` 枚举、
  `_REQUIRED_REVIEW_CHECKS`、`retest_selection` 合法 kind 集；不代签任何 decision；
  不在本切片接 selection/writeback 线。

## 6. S05 首切片交付物

- `deeptutor/services/luban_lesson/variant_eligibility.py`：decision 块 schema 校验
  （fail-closed：缺块/形状错/sha 不符/blocklist 不可读 → 一律不 eligible）、治理投影
  （复用 practice_html `_eligible` 同一谓词 + read_model `_load_signed_bank` 同一签发
  闸，禁第二 loader）、按 fact 就绪度 summary（双 role 非空 + ≥2 骨架 → fact ready）、
  审核包 builder。
- 审核包生成器扩展 `--kind variant`（practice 语义不变，默认值不变）。
- S05 75 条富化候选文件（15 fact 聚类；X-distance 6 条 extension 如实标记不服务）。
- 测试先行：schema 校验/fail-closed/审核包/候选生成确定性，全部
  `DEEPTUTOR_ENV=local python -m pytest` 绿 + ruff 绿。
