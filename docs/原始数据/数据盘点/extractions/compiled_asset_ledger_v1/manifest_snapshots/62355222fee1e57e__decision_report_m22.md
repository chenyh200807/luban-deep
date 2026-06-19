# M22 Decision Report — RAG vs Luban v1 职责切分

## 裁决：WEAK-GO

## 安全不变量（全 0 才可发布）
{
  "false_positive_B": 0,
  "false_positive_C": 0,
  "bad_certified_B": 0,
  "bad_certified_C": 0,
  "source_mismatch_C": 0,
  "list_partial_auto": 0,
  "unsupported_positive": 0,
  "teacher_only_leak": 0,
  "source_laundering_auto": 0
}

## 规模
- grading 提交数：210；B 点级决策：550；C 点级决策：479
- 题型分布：{"教材知识": 160, "综合review": 120, "案例判断": 240, "索赔工期费用计算": 30}

## 四条线职责切分（核心产品结论）
- **A 旧 RAG**：保留为 **retrieval / source expansion / answer baseline**。它擅长自由文本作答与源检索，但**不是点级判分权威**，无 validator、hallucination 暴露。live 检索本轮 不可用（data/knowledge_bases 为空），降级为 retrieval baseline（已审计，未伪造）。
- **B M16 deterministic**：保留为 **安全地板 / 规则签名层**。点级 auto/review 二元、确定、零成本、低延迟；但只能二元，无 partial 细档与解释。
- **C M17/M19 runtime LLM v1**：接管 **点级细档判分 + evidence_span + 解释 + Learning Brain 证据**。在 partial/near_miss/hallucination 变体上给出 det 给不出的 partial/needs_review；validator 作安全地板保证 fp/source_mismatch=0。quality_axis=real_llm。
- **D M20.2 delta**：**future_delta candidate**。本轮唯一可测收益 = packet 压缩（token 省 19.5%、bytes 省 18.2%）；19 个评分改写仍是 work-order（runtime_effect=candidate_context_only），**未吸收进 runtime**；进入下一版 registry 需经独立编译里程碑（非 M22）。

## 何时必须 LLM / 何时 deterministic 足够
- 必须 LLM：部分正确、错因相近、诱导 hallucination 的样本——需要 partial 细档与 evidence 解释。
- deterministic 足够：完整正确作答、纯 numeric/list 全覆盖点——det 与 LLM auto 集合一致，且零成本零延迟。

## 红线
未 flip production default；未写远端/DB/canonical truth；未发 registry；M20.2 仅候选对照、未进 runtime；official_answer/model/council vote 未当 source。
