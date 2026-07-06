# 裁决签发 override 草案（9 包）—— 待 owner 人闸翻牌

> **这是草案，不是 live `_pack_manifest.overrides.json`。** 翻 `published` 是 owner 的人闸权，本文件只把机器核验数字备齐供批量拍板。
> 机器准入证据（隔离 worktree 实跑 2026-07-06）：`python3 docs/原始数据/考点原料/recheck_resolutions.py A02 B02 C05 C07 D12 G01 G02 G04 D14` → **REAL_EXIT=0**（9 包 verify_pack + verify_exam_anchors 双闸 + resolution 重放 + manifest 零漂移全绿）。
> 当前 manifest：`packs=41 green=28`，本 9 包 `published=false / jury_clean=true`（已裁未签，等 override）。
> 签发裁决人 = owner；机器准入 = 本 worktree 工程窗口。

## override 草案 JSON（供 owner 审后并入 live overrides）

```json
{
  "A02": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck_resolutions exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 9 + 案例锚 4 = 13，题号漂移/不符/缺失 0）；jury 高可信 4/未决 0（jury_clean）；🔴=25（多为 R7 评分边界候选，待真人裁决，本 pack 不充判分器）；含答题层。签发裁决人=owner。"},
  "B02": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 15 + 案例锚 1 = 16，零漂移）；jury 高可信 3/未决 0；🔴=15（R7 候选为主）；含答题层。签发裁决人=owner。"},
  "C05": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 11 + 案例锚 0 = 11，零漂移）；jury 高可信 6/未决 0；🔴=27（R7 候选 + 误锚已剔除）；含答题层。签发裁决人=owner。"},
  "C07": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 8 + 案例锚 2 = 10，零漂移）；jury 高可信 4/未决 0；🔴=17（R7 候选为主）；含答题层。签发裁决人=owner。"},
  "D12": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 11 + 案例锚 0 = 11，零漂移）；jury 高可信 4/未决 0；🔴=23（含 S1 石材选法真题未直命，保留 🔴 作变题备料）；含答题层。签发裁决人=owner。"},
  "G01": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 7 + 案例锚 0 = 7，零漂移）；jury 高可信 3/未决 0；🔴=18（R7 候选 + 支护设计参数越界归 B02）；含答题层。签发裁决人=owner。"},
  "G02": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 5 + 案例锚 1 = 6，零漂移）；jury 高可信 6/未决 0；🔴=23（R7 候选为主）；含答题层。签发裁决人=owner。"},
  "G04": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 4 + 案例锚 0 = 4，零漂移）；jury 高可信 4/未决 0；🔴=22（R7 候选 + 桩基/支护越界归 G03/B02）；含答题层。签发裁决人=owner。"},
  "D14": {"published": true, "note": "2026-07-06 裁决流水线机器准入：recheck exit 0（含本次新裁 row0=fixed）；verify_pack exit 0；verify_exam_anchors exit 0（单选/多选锚 12 + 案例锚 0 = 12，零漂移）；jury 高可信 1/未决 0；🔴=27。**D14 裁决**：三源 flag（DeepSeek/Qwen/Codex）『门窗采分簇误引入涂饰基层含水率/耐水腻子』为真——教材原文直读证实 kc:1A422000_043_0069:1（溶剂型涂料含水率≤8%）与 :2（找平层耐水腻子）系涂饰工程、非门窗本体，门窗真锚仅 :0（砌体禁射钉）；手术已剔除/降级并归类涂饰（R5.3/R6.3/R8误区12），补位核=DeepSeek-V4-Pro 盲测判两条均属涂饰工程（利益回避：Codex 系 flagger 不自裁）。**注意**：D14 为 composite teaching prototype，`has_answer_layer=false`（尚无答题层样板），owner 若签发需知晓此形态差异。签发裁决人=owner。"}
}
```

## owner 翻牌前提醒（你没问但必须说）

- **D14 与其余 8 包形态不同**：D14 是横跨吊顶/门窗/地面的 composite teaching prototype，`has_answer_layer=false`；其余 8 包均含答题层样板。若批量签发口径要求“含答题层”，D14 应单独判或先补答题层。
- **published 仍需 owner 亲翻**：本草案不动 live overrides，manifest 里 9 包仍 `published=false`；消费侧投影门只认 `published and jury_clean and signed`，未翻牌前不会进生产默认入口。
- **🔴 的性质**：各包 🔴 主体是 R7 评分边界候选（设计上“本 pack 不充判分器，待真人/专家裁决”）+ 真题侧锚但 compiled source 未收的诚实缺口，不是编造。抽检包（`2026-07-06-luban-adjudication-spotcheck.md`）已逐包列出最该看的几条。
