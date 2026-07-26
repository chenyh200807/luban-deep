# 佑森已付费学员邀请码体验：launch-ready vertical slice

状态：Implemented locally; not deployed

## 目标与边界

佑森已付费学员使用邀请码兑换一次 14 天临时体验。体验资格与内部 AI 成本由
`ExperienceInviteAuthority` 独立治理，不改会员、钱包、积分、付费套餐或 learner state。

- 免费与付费视频规则继续由既有会员目录 authority 决定。
- 邀请码仅在没有有效付费会员时，通过既有 `teaching_video_limit` gate 临时投影
  30 个精选核心视频。
- AI turn 开始前由 Postgres RPC 原子预留 0.2 CNY headroom（已结算约 0.8 CNY
  时停止新请求），终态按真实 Langfuse cost、明确估算或保守估算结算；每天内部
  硬上限 1 CNY。失败 turn 已产生模型 usage 也必须结算，只有零 usage 的早期失败才释放。
- 学员端不显示金额、预算、次数、邀请码使用量或成本 provenance，只显示体验状态、
  到期日和到期/日上限后的非金额引导。
- 管理端只提供现有 BI RBAC 保护下的生成与列表 API；单次可原子生成 1–100 个码，
  并分别配置兑换上限、有效期与渠道标签。明文邀请码仅创建响应返回一次，持久化只存
  SHA-256 hash 与短前缀。
- `DEEPTUTOR_EXPERIENCE_INVITE_ENABLED` 默认关闭；必须先成功执行 migration，再由发布流程
  打开。开启后 authority 不可达时，零余额体验入口 fail closed；有效付费钱包不受影响。

## 单一 authority

`experience_invites`、`experience_access`、`experience_turn_costs` 与 transactional
RPC 是唯一持久化事实；Python service 是唯一业务 adapter。钱包、`MemberUsageMeter`
和客户端本地状态均不得参与邀请码体验决策。

视频播放、停留、seek、checkpoint、退出和回看继续复用
`microlesson_playback -> product_behavior_events`，不新增视频统计表。

## 验证边界

本地证据为 E2：隔离临时 Postgres + PostgREST 已执行 migration，并以 `qa_eval_`
身份走通批量生成、兑换、30 视频 entitlement、预留/结算、到期，以及双并发同 turn
只有一个 reservation；anon/auth/service-role RLS/RPC 也已实测。另有服务/API contract
tests、mobile router regression、JS syntax、contract/schema/resource guards。未执行
生产 migration、未部署、未上传微信包，因此不能声称生产或真实微信入口已经生效。
