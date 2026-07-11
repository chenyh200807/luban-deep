# 首次体验四题 · 双教研签发包

> 状态：`Ready for human review / 未签发`
> 日期：2026-07-11
> 目标：让两位独立教研对同一份题目内容和同一 content hash 作出可追溯 verdict；本文件不代替人工签字。
> Canonical manifest：`deeptutor/services/first_run/script_manifest.v1.json`
> Manifest 文件 SHA-256：`5616896560d981fd54d3d84ac00130413cf5cdf8da3a95a63495734cc8126529`
> Script version：`first_run_script.v1@5022d02db1f3316ef7515e60140ba3f16128fde0dd8c0ebd86a9ff540a8ceffd`

## 1. 签发规则

1. 教研 A、教研 B 必须是两个不同的真实 reviewer identity，分别核对来源、题干、正确项、干扰项和解释边界。
2. 两人必须签同一 `question_id + content_sha256`；任一文案、选项或正确项修改都会生成新 hash，旧 verdict 全部失效。
3. 单题只有两人均为 `approve` 才可把 manifest 中该题改为 `review_status: signed`，并写入两个可追溯 `review_refs`。
4. 四题全部 signed 后，才可把 manifest 顶层 `release_status` 改为 `signed`。缺一题时，`POST /api/v1/first-run/complete` 必须继续返回 `409 first_run_content_not_signed`。
5. 人工签发只确认内容可作为低置信首次诊断证据；不授权 mastery、正式考试分数或长期人格推断。

建议的 `review_ref` 格式：

```text
teacher_review:<reviewer_id>:<YYYY-MM-DD>:<question_id>:<content_sha256>
```

## 2. 题目一：屋面卷材起鼓

- `question_id`：`first_run.v1:qigu_gebu`
- `content_sha256`：`2f040012810b901343d2dcd5399df6fc675fa0d89aa706cd5cfd6ede95ea0b3d`
- 题干：屋面卷材防水层局部起鼓，割开鼓泡放气、烘烤旧卷材槎口后，旧卷材下一步怎么处理？
- 选项：A 分层剥开，除去旧胶结料；B 整体揭开，换新的；C 用铲刀把鼓泡处铲除干净；D 不用动，直接铺新卷材盖住。
- 拟定正确项：`A`
- 主证据：`docs/原始数据/考点原料/_F04_exam_evidence.json:139-140`；参考答案明确含“烘烤旧卷材槎口，并分层剥开，除去旧胶结材料”。
- 主证据文件 SHA-256：`725de61aa9505fe5a41328cc7bbb4250a190728a994a1e652ef643c3796ebef4`
- 审查重点：题干把“清除旧胶结料”放在 A 项内，与参考工序一致；确认“旧卷材下一步”不会让考生误解为“重新粘贴新卷材”。

| 字段 | 教研 A | 教研 B |
|---|---|---|
| reviewer_id |  |  |
| reviewed_at |  |  |
| verdict（approve/revise/reject） |  |  |
| source_match |  |  |
| answer_match |  |  |
| distractor_quality |  |  |
| wording_risk |  |  |
| note |  |  |
| review_ref / signature |  |  |

## 3. 题目二：项目质量计划组织编制

- `question_id`：`first_run.v1:zhiliang_jihua`
- `content_sha256`：`a154b56b92fdcfa70a92141369be2d0306a3d7f7f183899cb4b29869f61283e5`
- 题干：项目部要编制项目质量计划，谁来组织编制才对？
- 选项：A 项目经理；B 项目技术负责人；C 企业质量管理部门；D 总监理工程师。
- 拟定正确项：`A`
- 主证据一：`docs/原始数据/考点原料/_F04_exam_evidence.json:139-140`；答案为“施工总承包单位项目负责人或项目经理组织编制”。
- 主证据二：同文件 `:219-220`；答案明确为“应由项目经理组织编写”。
- 主证据文件 SHA-256：`725de61aa9505fe5a41328cc7bbb4250a190728a994a1e652ef643c3796ebef4`
- 审查重点：一份来源允许“项目负责人或项目经理”，另一份明确“项目经理”。当前选择题只提供“项目经理”，两位 reviewer 必须确认这不会形成术语歧义，并确认题干问的是“组织编制”而非“审核/批准”。

| 字段 | 教研 A | 教研 B |
|---|---|---|
| reviewer_id |  |  |
| reviewed_at |  |  |
| verdict（approve/revise/reject） |  |  |
| source_match |  |  |
| answer_match |  |  |
| distractor_quality |  |  |
| wording_risk |  |  |
| note |  |  |
| review_ref / signature |  |  |

## 4. 题目三：填充墙最后三皮砖

- `question_id`：`first_run.v1:tianchongqiang_fangbie`
- `content_sha256`：`da852e636f301b9eb851f5e6a33e9c460902ae90f0bd97d66718e14a17ceb186`
- 题干：框架填充墙快砌到梁底，最后几皮砖怎么砌才不裂？
- 选项：A 等下部墙砌完 14 天后，再补砌顶紧；B 当天一口气砌到顶；C 隔一天就补上；D 留着缝不管，抹灰盖住。
- 拟定正确项：`A`
- 主证据一：`docs/原始数据/数据盘点/extractions/2024_jianzhu_case_rubric.jsonl:30`；“最后 3 皮砖应在下部墙砌完 14d 后砌筑”。
- 主证据二：`docs/原始数据/考点原料/_F04_exam_evidence.json:219-221`；除 14d 外，还要求“由中间开始向两边斜砌”。
- 源文件 SHA-256：`78da6c0a9fc9e31ba89e4a9586486626b81f95d58ab3c069cacbddabbd219caf`、`725de61aa9505fe5a41328cc7bbb4250a190728a994a1e652ef643c3796ebef4`
- 审查重点：当前题干使用“最后几皮”而非“最后 3 皮”，A 项只考 14d 时点、未写“中间向两边斜砌”。需明确 verdict：这是有意只测一个采分点，还是应收窄题干/补全表述。

| 字段 | 教研 A | 教研 B |
|---|---|---|
| reviewer_id |  |  |
| reviewed_at |  |  |
| verdict（approve/revise/reject） |  |  |
| source_match |  |  |
| answer_match |  |  |
| distractor_quality |  |  |
| wording_risk |  |  |
| note |  |  |
| review_ref / signature |  |  |

## 5. 题目四：装配式建筑垃圾 200t

- `question_id`：`first_run.v1:zhuangpeishi_laji`
- `content_sha256`：`20709b4196b6bdd2393902c5b52aaaa3bacc16e545da7ecc70d41a5bf7b1582f`
- 题干：新建装配式项目把建筑垃圾产生量写成每万平方米不大于 300t，这个数对吗？
- 选项：A 不对，装配式应不大于 200t；B 对，300t 就是标准；C 不对，应不大于 400t；D 没有硬指标，分类处理就行。
- 拟定正确项：`A`
- 主证据一：`docs/原始数据/考点原料/题库快照/FINAL_CLEANED_EXAM_V2025.json:3394,3931-3932`；原题写 300t，正确答案为不大于 200t，且不包括工程渣土、工程泥浆。
- 主证据二：`docs/原始数据/数据盘点/extractions/2025_jianzhu_case_rubric.jsonl:8`；同一采分点逐字锚。
- 源文件 SHA-256：`78f708cc883cddcf1f7547d2347d34bd387b64ed02e6d12cc052195d2a05987a`、`9551006d0029a9bcd643dc9ca601d49ba54561e269060d825d0b4799065a259c`
- 审查重点：题干明确只问“这个数”，所以 A 项只改 300t→200t；完整原答案还包含“不包括工程渣土、工程泥浆”。两位 reviewer 必须确认这种裁切不会让用户误以为 A 是该案例的完整采分答案。

| 字段 | 教研 A | 教研 B |
|---|---|---|
| reviewer_id |  |  |
| reviewed_at |  |  |
| verdict（approve/revise/reject） |  |  |
| source_match |  |  |
| answer_match |  |  |
| distractor_quality |  |  |
| wording_risk |  |  |
| note |  |  |
| review_ref / signature |  |  |

## 6. 签发后的机械操作清单

- [ ] 四题各有两个不同 reviewer 的 `approve` 与 `review_ref`。
- [ ] 每个 verdict 的 content hash 与本包一致；若不一致，先改题并重新生成本包，禁止沿用旧签字。
- [ ] 更新 manifest 单题 `review_status/review_refs`，再把顶层 `release_status` 改为 `signed`。
- [ ] 重新生成或同步 `script-data.js` 镜像，并运行前后端 hash 一致性测试。
- [ ] 运行 first-run manifest/writeback/API、前端旅程、contract/schema/mirror gates。
- [ ] 用隔离 eval runner 在真实 `yousenwebview` 项目根完成一次签发后写回，证明 200、幂等 replay、学情续接和旧摸底弹窗抑制。
- [ ] 以上只形成内容 release candidate；owner 已授权代码 commit、review、push、PR merge main，部署及把 manifest 改为 signed 仍需单独授权。
