# 待教研复核 — primary_taxonomy_ref（机械取值，provisional）

> 来源：`scripts/compile_luban_pack_taxonomy_registry.py` 从 60-slot 注册表机械取 refs 首项。
> **全部条目 provisional**：只用于 taxonomy_code→pack 反查消歧，不充判分 authority。
> 教研确认某 pack 主锚后，请在注册表 md 调整该行 refs 首项并重跑编译脚本。

## 1. primary_taxonomy_ref 全量（60 slot）

| Slot | Pack | primary_taxonomy_ref（机械首项） | 对齐状态 | 教研复核 |
|---:|---|---|---|---|
| 1 | J01 | `1A431030-E01` | direct | 待复核 |
| 2 | S01 | `1A436032` | composite | 待复核 |
| 3 | S02 | `1A436000-B006` | direct | 待复核 |
| 4 | C02 | `1A432000-C17` | direct | 待复核 |
| 5 | B02 | `1A413022` | composite | 待复核 |
| 6 | Q01 | `1A413040-R28` | direct | 待复核 |
| 7 | A01 | `1A434020-B018` | direct | 待复核 |
| 8 | N01 | `1A433000-B041` | direct | 待复核 |
| 9 | K01 | `1A432000-B001` | composite | 待复核 |
| 10 | Q03 | `1A434030` | coarse_review | 待复核 |
| 11 | C04 | `1A413040-R25` | direct | 待复核 |
| 12 | Q02 | `1A413074` | direct | 待复核 |
| 13 | C01 | `1A413040-R20` | direct | 待复核 |
| 14 | C05 | `1A413040-R44` | direct | 待复核 |
| 15 | C06 | `1A413081` | coarse_review | 待复核 |
| 16 | C07 | `1A413043` | direct | 待复核 |
| 17 | S05 | `1A431050` | direct | 待复核 |
| 18 | S06 | `1A436035` | direct | 待复核 |
| 19 | S07 | `1A436000-B023` | coarse_review | 待复核 |
| 20 | N02 | `1A433000-B042` | direct | 待复核 |
| 21 | D11 | `1A434030-E01` | direct | 待复核 |
| 22 | D12 | `1A413064` | composite | 待复核 |
| 23 | D13 | `1A413134` | direct | 待复核 |
| 24 | D14 | `1A413062` | composite | 待复核 |
| 25 | G01 | `1A413037` | direct | 待复核 |
| 26 | G02 | `1A413039` | direct | 待复核 |
| 27 | G03 | `1A413032` | direct | 待复核 |
| 28 | G04 | `1A413048` | direct | 待复核 |
| 29 | F16 | `1A434000` | composite | 待复核 |
| 30 | F02 | `1A413103` | direct | 待复核 |
| 31 | F03 | `1A413100` | composite | 待复核 |
| 32 | F04 | `1A413050-R07` | coarse_review | 待复核 |
| 33 | F05 | `1A434033` | direct | 待复核 |
| 34 | X01 | `1A431040` | direct | 待复核 |
| 35 | X02 | `1A431040` | composite | 待复核 |
| 36 | X03 | `1A437020` | composite | 待复核 |
| 37 | R01 | `1A437030` | composite | 待复核 |
| 38 | N03 | `1A433011` | direct | 待复核 |
| 39 | E05 | `1A435020-B010` | direct | 待复核 |
| 40 | A02 | `1A434020-B018` | composite | 待复核 |
| 41 | E01 | `1A432000-B037` | direct | 待复核 |
| 42 | E02 | `1A432000-C19` | direct | 待复核 |
| 43 | E03 | `1A432000-C08` | coarse_review | 待复核 |
| 44 | E04 | `1A432000-C29` | direct | 待复核 |
| 45 | K03 | `1A432000-C14` | coarse_review | 待复核 |
| 46 | K05 | `1A432000-B001` | composite | 待复核 |
| 47 | K06 | `1A432000-B004` | composite | 待复核 |
| 48 | R02/R03 | `1A411020-R16` | coarse_review | 待复核 |
| 49 | R04 | `1A413134` | composite | 待复核 |
| 50 | N04 | `1A433000-G02` | composite | 待复核 |
| 51 | G05 | `1A413034` | direct | 待复核 |
| 52 | K04 | `1A432000-C08` | direct | 待复核 |
| 53 | K02 | `1A432000-B004` | merged_child | 待复核 |
| 54 | R05 | `1A422026` | conditional_split | 待复核 |
| 55 | X05 | `1A413080` | conditional_split | 待复核 |
| 56 | F06 | `1A412031` | merged_child | 待复核 |
| 57 | D17 | `1A422000-B061` | merged_child | 待复核 |
| 58 | X04 | `1A437013` | merged_child | 待复核 |
| 59 | D15 | `1A413061-R10` | conditional_split | 待复核 |
| 60 | D16 | `1A413063` | conditional_split | 待复核 |

## 2. IR↔注册表漂移项（需教研裁决）

- 注册表登记但无 animation IR 的 slot：D14、D15、D16、D17、E01、E02、E03、E04、F06、G05、K02、K03、K04、K05、K06、N04、R02/R03、R04、R05、X04、X05
