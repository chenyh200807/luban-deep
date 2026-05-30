# 计费上线 Runbook（B1 校正 + flag 翻 ON）

> 状态：**已 dry-run 验证，待指挥官上线当天授权执行**
> 适用 HEAD：`37492c46`（B1/H3/H4/H9/H10 已全部合入 main）
> 作者验证日期：2026-05-30（dry-run，未做任何 live 写入/翻 flag）

## 0. 背景与目标

- B1 计费止血（PR#79）已合入，但**挂在 `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` 开关后，默认 OFF**（`wallet/service.py:28 is_billing_enforcement_enabled() → _env_flag(..., default=False)`）。当前**休眠 = 钱包零变动、零 ledger 写、零拦截**（内测免费）。
- 历史污染：B1 修复前的旧扣费只插 ledger 不减余额，导致生产 **86/977 钱包 `balance_micros` > Σ(delta_micros)**（净偏差约 **+8928 点**）。指挥官已定：**豁免追扣，只把余额校正到 Σdelta 真值**（修腐败，不向用户追钱）。
- 上线当天顺序：**①校正余额到 Σdelta 干净基线 → ②翻 flag ON（从干净基线开始真扣费）**。

## 1. 凭证与边界纪律（每步通用）

- 生产 DB：service-role pooler，连接串在 `FastAPI20251222/.env` 的 `DB_URL=`（host=`aws-1-ap-southeast-1.pooler.supabase.com:6543`）。**凭证绝不打印明文**；每次先 host 校验是目标库才动手。
- 阿里云写边界（AGENTS §3.7）：远端只允许写 `/root/deeptutor` 内（`.env` 在此，合规）。
- 派生连接串的标准片段（每个 psql 步骤前执行，**不回显 $CONN**）：

```bash
ENVFILE=/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env
DB_URL=$(grep -E '^DB_URL=' "$ENVFILE" | head -1 | sed -E 's/^DB_URL=//' | tr -d '"')
case "$DB_URL" in *sslmode=*) CONN="$DB_URL";; *\?*) CONN="${DB_URL}&sslmode=require";; *) CONN="${DB_URL}?sslmode=require";; esac
HOST=$(printf '%s' "$DB_URL" | sed -E 's#^[a-z]+://##; s#^[^@]*@##; s#[:/?].*##')
[ "$HOST" = "aws-1-ap-southeast-1.pooler.supabase.com" ] || { echo "host 非目标库,中止"; exit 2; }
```

---

## 2. 上线当天执行顺序（总览）

| 步 | 动作 | 谁授权 | 验证 | 回滚 |
|---|---|---|---|---|
| S0 | 上线决策门 | 指挥官 | — | 不执行后续 |
| S1 | 余额校正 **dry-run** + 审 diff | 工程→指挥官审 | diff 行数=86 | 无（只读）|
| S2 | 余额校正 **execute**（唯一 live 写）| 指挥官明确授权 | updated_rows 数 | 见 §6 |
| S3 | 校正后 audit 归零 | 工程 | ledger_sum_diff_count=**0** | 见 §6 |
| S4 | 翻 flag ON + 重建容器 | 指挥官明确授权 | /readyz 200 | §5 翻回 OFF |
| S5 | 真机 smoke | 工程 | 余额真递减 | §5 翻回 OFF |

> **S1/S3/审计命令、rebuild dry-run 已在 2026-05-30 验证通过**（见 §3、§7）。当天 S1/S3 只需重跑确认，**S2 才第一次加 `--execute` 写库**。

---

## 3. S1 — 余额校正 dry-run + 审 diff（已验证，只读）

校正基准 = `Σ(delta_micros)`（开户额是首条 `grant` ledger，migration `20260419000600`，故 Σdelta=真值）。**禁止用** `rebuild` 的旧 `balance_after_micros` 基准（已被 PR#81 修为 Σdelta；旧基准会固化错误）。

```bash
# 1) rebuild dry-run（不写库，仅产出 SQL 预览，确认基准=Σdelta）
SUPABASE_DB_URL="$CONN" python3 scripts/rebuild_wallet_balance_from_ledger.py --output-dir artifacts/billing_golive
#   期望: status=dry_run，sql_preview 含 sum(delta_micros)

# 2) 逐户 from→to diff（只读 SELECT，存档供指挥官审）
psql "$CONN" -At -F$'\t' -c "
with ls as (select user_id, sum(delta_micros) exp from public.wallet_ledger group by user_id)
select w.user_id, w.balance_micros, coalesce(ls.exp,0) as corrected_to,
       w.balance_micros-coalesce(ls.exp,0) as drift
from public.wallets w left join ls on ls.user_id=w.user_id
where w.balance_micros <> coalesce(ls.exp,0)
order by abs(w.balance_micros-coalesce(ls.exp,0)) desc;" > artifacts/billing_golive/balance_correction_diff.tsv
```

**审核口径**（指挥官）：`artifacts/billing_golive/balance_correction_diff.tsv`（逐户 `user_id / 当前余额 / 校正到 / 偏差`，**因 repo 为 PUBLIC，该明细只存本地 gitignore 的 artifacts/，不入库**）。
**2026-05-30 dry-run 结果**：受影响 **86** 钱包，净偏差 **+8928.00 点**（绝大多数是 B1 少扣导致余额偏高 → 校正后下调）。

---

## 4. S2 — 余额校正 execute（⚠️ 唯一 live 余额写入，仅当天指挥官授权后）

```bash
# 仅在指挥官明确授权、且 S1 diff 已审通过后执行：
SUPABASE_DB_URL="$CONN" python3 scripts/rebuild_wallet_balance_from_ledger.py --execute --output-dir artifacts/billing_golive
#   该命令把每个钱包 balance_micros 原子重算为 Σ(delta_micros)；frozen 从最新 after-image 重建。
#   产出 status=ok + updated_rows 清单（应 ≈ 86 行）。
```

> 注：本步是事务内 UPDATE；建议先在 Supabase 控制台确认有 PITR/快照可回退（钱包表无部署期备份，见 §6）。

## 5. S3 — 校正后 audit 归零验证（已验证命令，当天重跑）

```bash
SUPABASE_DB_URL="$CONN" python3 scripts/audit_wallet_projection_consistency.py --execute --output-dir artifacts/billing_golive --limit 200
#   读 result.ledger_sum_diff_count（可信 Σdelta 校验）
```

**验收**：`ledger_sum_diff_count == 0`（校正前 = 86）。若非 0，**不要翻 flag**，回到 §6 排查。
（`balance_after_diff_count` 是 legacy 列校验，可能非 0，不作为放行依据。）

---

## 6. S4 — 翻 flag ON（⚠️ 真扣费开始，仅当天指挥官授权后）

flag 由进程 `os.getenv(DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED)` 读取；容器经 `docker-compose env_file: .env`（`docker-compose.yml:41`）在**启动时**注入 env，故改 `.env` 后**必须 force-recreate 容器**（`docker restart` 不重载 env_file）。

```bash
# 在阿里云远端（写边界 /root/deeptutor 内）：
ssh Aliyun-ECS-2 'cd /root/deeptutor && \
  grep -q "^DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=" .env \
    && sed -i "s/^DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=.*/DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=true/" .env \
    || echo "DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=true" >> .env'
# 重建容器以重载 .env（仅 recreate，不动代码）：
ssh Aliyun-ECS-2 'cd /root/deeptutor && docker compose -f docker-compose.yml up -d --no-deps --force-recreate deeptutor'
# 验证就绪：
curl -s -o /dev/null -w "%{http_code}\n" https://test2.yousenjiaoyu.com/readyz   # 期望 200
```

> 也可用 `bash scripts/server_fast_reload_aliyun.sh`（同样 `up -d --force-recreate`，但附带 build/验收，更重）；env-only 翻转用上面的纯 recreate 更快。

**回滚（任一异常立即执行）**：把 `.env` 的该行改回 `=false`（或删除），再次 `up -d --force-recreate deeptutor`，回到休眠 OFF（钱包零变动）。

## 7. S5 — 翻 flag 后真机 smoke（已文档化命令，当天人工核验）

1. 微信小程序发起一次正常聊天 turn（账户余额充足）。
2. 校验扣费正确：

```bash
# 取该测试用户的 user_id（UUID），代入 :UID
psql "$CONN" -At -c "select balance_micros from public.wallets where user_id=':UID'::uuid;"   # turn 前
# —— 发一次聊天 ——
psql "$CONN" -At -c "select balance_micros from public.wallets where user_id=':UID'::uuid;"   # turn 后：应已递减
psql "$CONN" -At -F$'\t' -c "select delta_micros, balance_after_micros from public.wallet_ledger where user_id=':UID'::uuid order by id desc limit 1;"
#   验收: balance_micros 真递减；最新 ledger 后像 balance_after = (turn前余额 + delta)（不再是扣费前快照）。
```

3. 余额不足场景（可选）：把测试用户余额调到接近 0，发聊天 → 期望 `/api/v1/chat/start-turn` 返回 `429 billing_quota_exceeded`（H3 硬余额门），**答案不交付、不写扣费 ledger**。
4. 任一项不符 → 立即执行 §6 回滚（翻 flag OFF）。

---

## 8. 已 dry-run 验证 / 当天才首次 live 的分界

| 已 2026-05-30 验证（只读/dry-run，当天只需重跑确认） | 当天才**首次** live 执行（需指挥官授权）|
|---|---|
| S1 rebuild dry-run（status=dry_run）| **S2** rebuild `--execute`（唯一 live 余额写）|
| S1 逐户 diff SELECT（86 行已存档）| **S4** edit `.env` + force-recreate（翻 flag ON）|
| S3 audit 命令（当前 ledger_sum_diff_count=86）| **S5** 真机扣费 smoke |

## 9. 残留风险

- 钱包表无部署期自动备份（依赖 Supabase 平台 PITR）——S2 前确认 PITR 可回退。
- 校正后若有用户在 S2 与 S4 之间发生新扣费，会被 flag OFF 拦成 no-op（不影响余额一致性，因为 OFF 不写）；建议 S2→S4 连续执行、窗口尽量短。
