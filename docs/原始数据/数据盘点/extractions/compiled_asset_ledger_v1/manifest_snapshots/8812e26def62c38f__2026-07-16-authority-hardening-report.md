# DeepTutor Docs-Code Authority Hardening — 2026-07-16

## 结论

本轮不是逐条补文案，而是收敛同一个主病：**终态投影越权自决**。manifest、HTTP wrapper、citation assembler、INDEX、scanner 曾各自把局部元数据升级为业务事实。修复后，下游只读 canonical authority；唯一无法由代码制造的缺口是 first-run 第二位真实教研 verdict，因此保持 fail-closed。

## Authority / 工作区证据

- automation cwd：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- repo authority：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- dirty 主仓：保留原样，未 reset/stash/checkout/overwrite
- candidate worktree：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor-docs-code-authority-hardening-20260716`
- candidate branch：`codex/docs-code-authority-hardening-20260716`
- base：`origin/main@93fe95895c7c407d7c57107b3e6e3f023ab266c1`
- CodeGraph：目录存在，但候选工作树无可用索引；按规则降级到定点 `rg`/文件读取。

## 差距与修复状态

| 事实 | 原差距 | 修复 | 状态 |
|---|---|---|---|
| first-run 内容签发 | agent delegate 被计作第二真人，manifest 写 `signed`，默认测试反而要求 blocked | manifest 恢复 pending、清空 refs、删除伪 signoff；同步 mini-program `script_version`；历史错误签发标 Superseded | Implemented / release 仍 blocked |
| 引用展示 | `contracts/rag.md` 要 structured-only，assembler/quality 却强制正文 marker | 删除 inline insertion；正文 marker 一律 fail；claim ref、连续编号校验；WeChat 复用既有独立区，Web 只读 result bundle 新增独立 refs 区 | Implemented / production gate pending |
| 会员套餐 | mobile 直接读私有 defaults，绕过持久化 catalog/alias authority | `MemberConsoleService` 暴露公共 resolver；mobile thin wrapper 只调用 public catalog/resolver；双 contract 镜像登记 authority | Implemented |
| env inventory | 从 artifacts 跑 `--all` 扫描 0 文件假绿，且漏 `.sh` | git discovery 固定 repo root、纳入 shell；7 个 release 值分类为 transient IPC，`RELEASE_KEEP` 为外部 config；root/artifacts 都扫描 443 refs | Implemented |
| WeChat 证据面 | harness PASS 可被误读为真微信 closure | eval gate/result/Markdown 透传 `evidence_surface=wechat_harness_shadow`；INDEX 标 `real_wechat_package` pending | Implemented |
| 路径与计划发现性 | active contract 链接和 M35 env fallback 指向旧 Documents 根；近期 6 个承重文档未挂 INDEX | authority 链接改相对路径；删除旧仓 `.env` 静默 fallback；6 个文档按 Historical/Implemented evidence 挂现有主线 | Implemented |

## 验证证据

- 首轮 RED：first-run `2 failed, 5 passed`；显式 env shell 扫描报 8 个未登记 release 变量，而 artifacts `--all` 错误 PASS。
- 修复后核心：`136 passed`（citation、first-run、env、eval）。
- billing/M35 定向：`6 passed`；catalog alias/runtime authority 另有 `7 passed`。
- mini-program：`PASS test_first_run_native_journey.js`。
- Web：citation projection Node tests 2/2；ESLint 与 `tsc --noEmit` 通过；未启动 Next/browser。
- env：repo root 与 artifacts cwd 均 `env_refs=443 feature_flags=19`。
- guards：contract guard、registry meta、双 contract `cmp`、shell syntax、旧 active path scan 均通过。
- process hygiene：无 AI-agent-owned Next dev process tree。

## 建议状态

- first-run manifest：`Implemented (fail-closed)`；内容签发：`Draft / blocked_pending_human_verdict`。
- citation structured-only backend/Web projection：`Implemented`；production enablement：`Proposed`，需真人 citation audit、真 WeChat、线上观测。
- 旧 inline citation 章节与 2026-07-12 delegate signoff：`Superseded/Historical`。
- billing/env/evidence surface/active links：`Implemented`。

## 高风险需确认

1. 两位真实、独立教研必须对四题相同 content hash 明确 approve；agent、delegate、测试 fixture 均无签发权。
2. citation flag 上生产前仍需 50-answer 人审、真 WeChat DevTools/真机回归、Langfuse/ClickHouse 采样；本地绿灯不是 production truth。
3. env `.sh` 扫描目前是静态止血，不是完整 shell 语义解析器；后续若新增复杂间接展开，应加专门解析或把 IPC 改成结构化 argv/stdin，但不应在本次发布脚本修复中冒险扩行为面。

## 下一步 Codex prompt

> 在 latest origin/main 的干净候选工作树执行 first-run 真人签发 promotion：先核两位真实独立教研对四题同一 content SHA 的逐题 approve 证据；没有证据立即停止。证据齐全后只修改 canonical manifest attestation、派生 script_version、review packet/INDEX 状态，并跑 first-run server rescore、zero-write-on-unsigned、native journey、真 WeChat DevTools 回归。不得用 agent/delegate 代签，不得把 harness 或本地测试写成 release truth。

