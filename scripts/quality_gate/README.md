# scripts/quality_gate — 持续质量飞轮 accuracy_gate

P0 一键准确性回归门 + 可调度封装 + 本地 launchd 定时。
判定逻辑单一权威在 `accuracy_gate.py`;其余都是薄封装,不重复实现任何判据。

| 文件 | 作用 |
|---|---|
| `accuracy_gate.py` | 六维确定性探针编排 + 三方 SHA 前置门 + 封板判据/退出码(**单一权威**) |
| `scheduled_run.py` | 可调度薄封装:SHA 门前置 + WEAK-GO 报告 + `metrics/accuracy.jsonl` 趋势 + `LOG.md` 记账 |
| `run_local_scheduled.sh` | launchd wrapper:自包含 PATH/pyenv/HOME + source `.env` + 注入 QA env + 跑 `scheduled_run.py` + 落 `cron.log` |
| `probes/` | 六维探针(daowu/huizhi/leak_boundary/sev_regression/forward_liveness/content_truth)+ `_probe_common.py` |

## 手动跑一次

```bash
cd <repo>
set -a; source .env; set +a
export DEEPTUTOR_QA_USERNAME="$WECHAT_QA_USERNAME" DEEPTUTOR_QA_PASSWORD="$WECHAT_QA_PASSWORD"
export DEEPTUTOR_QA_BASE_URL="https://test2.yousenjiaoyu.com"   # 别用 .env 里的 dev 127.0.0.1
python scripts/quality_gate/scheduled_run.py --runs 3
```

## 退出码口径(透传,单一权威)

| exit | 含义 |
|---|---|
| 0 | WEAK-GO(结构判定,**待人盖封板**) |
| 2 | SKIP(三方 SHA 不齐,未花钱 —— 门在正确工作) |
| 3 | BLOCK(某维复现,需人工核 evidence 治本) |
| 4 | INCONCLUSIVE(登录失败/全降级,非内容失败) |

---

# 自动跑 —— 按需触发(默认)/ 每日定时(可选)

**默认按需**:不挂每日定时,只在需要时一条命令触发整条 loop —— wrapper 自包含
(source `.env` + 注入 QA env + SHA 门 + 跑六维 + 落 WEAK-GO 报告 + append metrics/LOG):

```bash
cd <repo> && bash scripts/quality_gate/run_local_scheduled.sh
```

**封板 GO 永远人在环** —— 自动只到 WEAK-GO/BLOCK 报告,不自动盖 GO / 不 ship / 不改代码。

> 每日定时(launchd,可选):想让它每天 02:00 off-peak 自动跑,再 `launchctl load` plist
> (见下)。默认**不 load**,所以不会每天跑。

## 为什么是本地 launchd 而不是 GitHub Actions cron

SHA 门要 `ssh Aliyun-ECS-2` 读 host `.env` 与 container env 做三方对齐校验。
不想把生产 SSH 私钥放进 CI secrets,所以调度器留在本机(有 `~/.ssh/aliyun_ecs_2`
+ `Aliyun-ECS-2` 别名 + `~/.deeptutor_eval_key` billing bypass)。
`.github/workflows/accuracy-gate-scheduled.yml` 的 `cron` 段仍故意注释,`workflow_dispatch`
可手动触发。将来 CI 具备安全私钥注入后可切回(见文末)。

## 组件

- `scripts/quality_gate/run_local_scheduled.sh` — wrapper
- `~/Library/LaunchAgents/com.deeptutor.accuracy-gate.plist` — launchd 定义(每日 02:00,非 KeepAlive,跑完即退)

日志与产物:

- `artifacts/quality_gate/scheduled/cron.log` — 每次开始/结束/退出码明细(wrapper 写,append)
- `artifacts/quality_gate/scheduled/launchd.{out,err}.log` — launchd 层 stdout/stderr
- `artifacts/quality_gate/scheduled/<ts>/report.md` — 每次 WEAK-GO 报告 + 六维矩阵
- `domains/quality-flywheel/metrics/accuracy.jsonl` — 确定性时序(append-only)
- `domains/quality-flywheel/LOG.md` — shared brain 活动流

## 装 / 停 / 手动触发

```bash
PLIST="$HOME/Library/LaunchAgents/com.deeptutor.accuracy-gate.plist"

launchctl load "$PLIST"                                  # 装(登录常驻注册,按日历定点跑)
launchctl list | grep com.deeptutor.accuracy-gate       # 确认已注册
launchctl start com.deeptutor.accuracy-gate             # 手动立即触发一次(验证用)
launchctl unload "$PLIST"                                # 停(注销定时,不删文件)
```

## 红线(自动化绝不放大假绿)

1. 自动只到 **WEAK-GO 报告** + append metrics/LOG + 落日志;**封板 GO = 人读报告点头**。
2. **绝不**自动 ship 生产 / 绝不自动改代码 / 绝不 `git add`(wrapper 纯读 + append 产物)。
3. SHA 门不齐自动 skip(exit 2),**绝不在错 SHA 上跑 eval**。
4. BLOCK 只记日志/弹窗,不自动修 —— 治本设计人在环。
5. 幂等 + 不常驻:定点触发,跑完即退,无后台进程树。

## 将来切回 GitHub Actions

前提:CI 能安全注入生产 SSH 私钥(OIDC / 自托管 runner / 受控 secret)。届时:

1. 在 repo secrets 配 5 个:`WECHAT_QA_USERNAME` / `WECHAT_QA_PASSWORD` /
   `DEEPSEEK_API_KEY` / `BIGMODEL_API_KEY` / `DEEPTUTOR_EVAL_BYPASS_KEY`(+ SSH key)。
2. 取消 `.github/workflows/accuracy-gate-scheduled.yml` 里 `cron` 段注释。
3. `launchctl unload "$PLIST"` 停本地定时,避免两边重复跑。
