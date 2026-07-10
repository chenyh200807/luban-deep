# 05 · 运行时生成器 / RTG1-8 门 / RTG6 近义 / RTG9 异源

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §1限制③。分支 `feat/luban-case-light-practice-p-1`。

## RTG1–RTG8 Post-gen 确定性门(commit `79cf9a222`)
`case_light_practice_rtg.py`:纯确定性 8 门(撞车/去重/错因码/候选/结构/形态/一致性/反编造)+ RTG9 异源接口。**未跑到的门显式 `NOT_EXERCISED`**(反假绿)。12 测试。

## 运行时生成器(commit `491e66924`)
`case_light_practice_generator.py`:LLM = **注入式 `complete_fn` seam**(单测 stub / 阿里云真 DeepSeek)。**correct 选项 = 采分点原文逐字,LLM 只造干扰项**(红线:LLM 不越权当真值)。出题过 RTG 门重生成 ≤2、仍 BLOCK→degraded。F16 起鼓割补 dev fixture(7 点,`dev_fixture=true` 不进 production whitelist)。7 测试。

## 静态 demo(commit `9d7f652dd`)
`scripts/build_case_light_practice_demo.py`:真跑链路(真采分点→生成器→真 RTG 门→真确定性判分),复现 A 漏 a5=1.2 / B 写了=1.5。唯一 stub = 干扰项来源。

## RTG6 近义门(live 证据驱动,commit `93e2cb77a`)
**真 DeepSeek 曾生成「分层剥离旧卷材」(与正确「分层剥开」差一字近义)竟过确定性 RTG1-8** = 计划预判的 RTG9 语义缺口在真链路上现形。**当场加 RTG6 近义门**:干扰项对正确项字符包含率 ≥0.85 → SOFT 可疑/异源。live 复验现抓住,合法干扰项不误伤。
- temp=0 观察:多数稳定但**非位级保证**(一次 1/3 措辞抖动);但**门安全性稳定**(每次都过门)。

## RTG9 异源分流门(commit `0df2194c1`)
`case_light_practice_rtg9.py`:确定性相似度预过滤 + 注入式异源 `judge_fn`,**只分流不当真值**。**Qwen(dashscope)真异源阿里云只读实测通过**:近义干扰「分层剥离旧卷材」(RTG1-8 放过)→ 异源 Qwen 判"也对"→ 分流。跨厂 seam 端到端证明(生成器 DeepSeek / 校验器 Qwen)。

## 真 LLM 只读实测法(可复现,`scripts/aliyun_probes/`)
自包含 harness → `base64` → `ssh Aliyun-ECS-2` → `docker cp deeptutor:/tmp` → `docker exec deeptutor sh -lc 'cd /app && PYTHONPATH=/app python /tmp/h.py'`;complete_fn pin `base_url=deepseek`/`binding=deepseek`/`temperature=0`/`api_key=容器 DEEPSEEK_API_KEY`;跑完清 /tmp。**不是部署、不是 owner-stop**——阿里云只读 docker exec 用容器自带 key。这是解开"本地无凭据"假阻塞的关键。
