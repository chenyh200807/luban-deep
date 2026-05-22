# Rubric Coverage Baseline

Generated: 2026-05-22
Source: Supabase host `aws-1-ap-southeast-1.pooler.supabase.com:6543`, table `public.questions_bank`.
Audit is read-only; no writes performed.

## Top-level totals

| Metric | Value |
| --- | --- |
| Total questions_bank rows | 4638 |
| Rows with non-empty grading_rubric | 0 (0.0%) |
| Rows with source_type=REAL_EXAM | 1050 (22.6%) |

## Coverage by question_type

| question_type | n | grading_rubric | grading_keywords nonempty | structured_rules nonempty | analysis nonempty | correct_answer nonempty | node_code present | cited_standard_codes present |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_study | 1961 | 0 (0.0%) | 960 (49.0%) | 661 (33.7%) | 1332 (67.9%) | 1950 (99.4%) | 1916 (97.7%) | 13 (0.7%) |
| single_choice | 1674 | 0 (0.0%) | 166 (9.9%) | 166 (9.9%) | 1670 (99.8%) | 1674 (100.0%) | 1634 (97.6%) | 6 (0.4%) |
| multi_choice | 978 | 0 (0.0%) | 74 (7.6%) | 75 (7.7%) | 978 (100.0%) | 978 (100.0%) | 958 (98.0%) | 2 (0.2%) |
| calculation | 15 | 0 (0.0%) | 15 (100.0%) | 0 (0.0%) | 15 (100.0%) | 15 (100.0%) | 15 (100.0%) | 0 (0.0%) |
| judgment | 7 | 0 (0.0%) | 7 (100.0%) | 0 (0.0%) | 7 (100.0%) | 7 (100.0%) | 7 (100.0%) | 0 (0.0%) |
| diagram_interpretation | 1 | 0 (0.0%) | 1 (100.0%) | 0 (0.0%) | 1 (100.0%) | 1 (100.0%) | 1 (100.0%) | 0 (0.0%) |
| fill_in_blank | 1 | 0 (0.0%) | 1 (100.0%) | 0 (0.0%) | 1 (100.0%) | 1 (100.0%) | 1 (100.0%) | 0 (0.0%) |
| recall | 1 | 0 (0.0%) | 1 (100.0%) | 0 (0.0%) | 1 (100.0%) | 1 (100.0%) | 1 (100.0%) | 1 (100.0%) |

## Map-eligibility on case_study items

Map-eligible = normalized projection yields >= 2 distinct scoring points.
Today we use the union of `structured_rules` >= 2 entries OR `grading_keywords` >= 2 entries.

| Metric | Value |
| --- | --- |
| case_study total | 1961 |
| structured_rules >= 2 | 14 (0.7%) |
| grading_keywords >= 2 | 955 (48.7%) |
| **map_eligible (union)** | **955 (48.7%)** |
| both signals (intersect) | 14 (0.7%) |

### Map-eligibility by exam_year (case_study)

| exam_year | n | map_eligible | share |
| --- | --- | --- | --- |
| 2025 | 311 | 258 | 83.0% |
| 2024 | 17 | 6 | 35.3% |
| 2023 | 60 | 22 | 36.7% |
| 2022 | 23 | 8 | 34.8% |
| 2021 | 49 | 0 | 0.0% |
| 2020 | 52 | 0 | 0.0% |
| 2019 | 41 | 0 | 0.0% |
| 2018 | 48 | 0 | 0.0% |
| 2017 | 25 | 0 | 0.0% |
| 2016 | 23 | 0 | 0.0% |
| 2015 | 22 | 0 | 0.0% |
| <null> | 1290 | 661 | 51.2% |

### Map-eligibility by node_code prefix (top 20, case_study)

| node_code prefix | n | map_eligible | share |
| --- | --- | --- | --- |
| 1A43600 | 152 | 84 | 55.3% |
| 1A43300 | 119 | 39 | 32.8% |
| 1A43400 | 113 | 55 | 48.7% |
| 1A41302 | 102 | 92 | 90.2% |
| 1A41201 | 97 | 65 | 67.0% |
| 1A43200 | 89 | 35 | 39.3% |
| 1A41101 | 85 | 75 | 88.2% |
| 1A41304 | 83 | 37 | 44.6% |
| 1A41300 | 65 | 33 | 50.8% |
| 1A42200 | 55 | 52 | 94.5% |
| 1A41303 | 52 | 31 | 59.6% |
| 1A41305 | 50 | 35 | 70.0% |
| 1A41306 | 45 | 44 | 97.8% |
| 1A43700 | 36 | 36 | 100.0% |
| 1A43500 | 29 | 25 | 86.2% |
| 1A43102 | 28 | 0 | 0.0% |
| 1A43800 | 26 | 26 | 100.0% |
| 1A43503 | 24 | 0 | 0.0% |
| 1A43201 | 23 | 15 | 65.2% |
| 1A42203 | 23 | 18 | 78.3% |

## structured_rules.type distribution

These rule types inform the ability_dimension mapping in the normalization spec.

| rule type | count |
| --- | --- |
| <null> | 382 |
| threshold_check | 224 |
| forbidden_check | 145 |
| sequence_check | 73 |
| Mandatory | 64 |
| membership_check | 29 |
| forbidden | 24 |
| numeric_check | 16 |
| comparison_check | 10 |
| condition_check | 9 |
| Recommended | 9 |
| formula_check | 9 |
| list_check | 7 |
| classification_check | 7 |
| multi_condition_check | 6 |

## Adjacent tables

| Table | Rows | Distinct keys |
| --- | --- | --- |
| public.rubrics | 1 | 1 distinct questions |
| public.question_intelligence | 43 | 43 compile_status=success |
| public.knowledge_question_links | 709 | 432 distinct questions linked |

## Authoring backlog — top 30 case_study items needing rubric

Priority: REAL_EXAM 2017-2021 first (node_code present; rubric authoring only), then 2015-2016 classification/content recovery, then high error_rate.

| id | node_code | exam_year | source_type | error_rate | stem preview |
| --- | --- | --- | --- | --- | --- |
| 8911 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000㎡。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工组 |
| 8927 | 1A411000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】（根据上下文推断）某项目正在实施建筑节能工程，涉及围护结构和保温材料的选用。 【问题】围护结构子分部工程包括哪些？墙体保温材料进场需复验哪些性能指 |
| 8903 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |
| 8910 | 1A431000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000㎡。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工组 |
| 8922 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000m²。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工 |
| 8926 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】（根据上下文推断）某项目正在进行地基、钢筋、混凝土和节能构造的质量检测。 【问题】各类检测参数和抽检频次条件有哪些？ |
| 8901 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |
| 8908 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发）要求，在项目 |
| 9447 | 1A436000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某住宅工程由7栋单体组成，地下2层，地上10~13层，总建筑面积1.5万m²。施工总承包单位中标后成立项目经理部组织施工。 项目总工程师编制了《临 |
| 8905 | 1A431000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发）要求，在项目 |
| 8912 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000㎡。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工组 |
| 8921 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000m²。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工 |
| 8923 | 1A436000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】（根据上下文推断）某建筑工地正在进行临时用电系统安装，涉及配电箱布置、电缆敷设及施工验收等环节。 【问题】临时用电安全规范中有哪些关键要求？ |
| 8925 | 1A434000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】（根据上下文推断）某建筑正在进行拆除作业，涉及脚手架和连墙件的拆除。 【问题】拆除作业的安全规范有哪些？ |
| 9442 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000m²。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工 |
| 9445 | 1A432000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某新建住宅楼工程，建筑面积 25000m²，装配式钢筋混凝土结构。建设单位编制了招标工程量清单等招标文件，其中部分条款内容为：本工程实行施工总承包模 |
| 9391 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发）要求，在项目 |
| 8902 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |
| 9441 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000m²。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工 |
| 9446 | 1A436000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某住宅工程由7栋单体组成，地下2层，地上10~13层，总建筑面积1.5万m²。施工总承包单位中标后成立项目经理部组织施工。 项目总工程师编制了《临 |
| 9416 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目，地上15~18层，地下2层，钢筋混凝土剪力墙结构，总建筑面积57000㎡。施工单位中标后成立项目经理部组织施工。 项目经理部计划施工组 |
| 8900 | 1A431000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |
| 9443 | 1A433000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】 某施工单位承建一高档住宅楼工程。钢筋混凝土剪力墙结构，地下2层，地上26层，建筑面积36000㎡。 施工单位项目部根据该工程特点，编制了施工期变 |
| 8907 | 1A413000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发）要求，在项目 |
| 8919 | 1A436000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某住宅工程由7栋单体组成，地下2层，地上10~13层，总建筑面积1.5万m²。施工总承包单位中标后成立项目经理部组织施工。 项目总工程师编制了《临 |
| 8920 | 1A436000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某住宅工程由7栋单体组成，地下2层，地上10~13层，总建筑面积1.5万m²。施工总承包单位中标后成立项目经理部组织施工。 项目总工程师编制了《临 |
| 9366 | 1A431000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |
| 8906 | 1A412000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发）要求，在项目 |
| 8924 | 1A435000 | 2021 | REAL_EXAM | 0.000 | 【背景资料】（根据上下文推断）某项目在施工过程中面临绿色施工和突发公共卫生事件双重挑战，需落实相关管理措施。 【问题】绿色施工和疫情应对的关键措施有哪些？ |
| 17271 | 1A431000 | 2021 | REAL_EXAM | 0.000 | 某工程项目经理部为贯彻落实《住房和城乡建设部等部门关于加快培育新时代建筑产业工人队伍的指导意见》（住建部等12部委2020年12月印发），要求在项目劳动用工管理 |

## Normalization preview — 13 high-signal case items

These items already have >= 3 keywords AND >= 2 structured rules; they are the
available high-signal candidates for the教研 sign-off review described in Phase -1.A.1.
A second preview must cover keyword-only items because they dominate the current map-eligible set.

| id | node_code | grading_keywords | structured_rules | stem preview |
| --- | --- | --- | --- | --- |
| 7845 | 1A421000 | 5 | 8 | 根据《城市道路管理条例》，下列关于城市道路占用的说法正确的是？ |
| 7846 | 1A421000 | 8 | 6 | 根据《建设工程文件归档规范》，下列关于工程档案的说法错误的是？ |
| 7867 | 1A422000 | 6 | 6 | 下列关于建筑声环境设计的说法中，错误的是？ |
| 7872 | 1A422000 | 8 | 3 | 关于屋面工程的施工要求，下列说法错误的是？ |
| 7874 | 1A422000 | 5 | 2 | 下列建筑中属于I类民用建筑工程的是？ |
| 7884 | 1A422000 | 10 | 5 | 关于民用建筑室内环境污染物检测，下列说法错误的是？ |
| 7885 | 1A422000 | 5 | 3 | 关于地基基础设计工作年限，下列说法正确的是？ |
| 7887 | 1A422000 | 5 | 3 | 下列哪类建筑物必须在施工和使用期间进行沉降观测？ |
| 7889 | 1A422000 | 6 | 4 | 筏形基础的混凝土强度等级最低应为多少？ |
| 7894 | 1A422000 | 5 | 9 | 关于强夯地基施工后的质量检测间隔时间，下列说法正确的是？ |
| 7903 | 1A422000 | 8 | 5 | 关于真空井点的构造要求，下列说法正确的是？ |
| 8189 | 1A431000 | 4 | 5 | 下列关于施工组织设计审批的说法，正确的是？ |
| 8198 | 1A431011 | 4 | 10 | 关于施工现场临时仓库布置的说法，正确的是？ |

## Phase -1.A gate readout

- Measured map_eligible_coverage on case_study: **48.7%**
- Promotion gate (>= 70%): **FAIL — promote scoring_point_map UI only with rubric_pending empty state**
- LLM grounding discipline: not measured in this report; see Phase -1.A.3 grader_disagreement audit.

---
Generated by `scripts/rubric_coverage_report.py` (read-only).
